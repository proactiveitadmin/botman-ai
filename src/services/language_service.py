from __future__ import annotations

import boto3, re
from botocore.config import Config
from typing import Optional
from datetime import datetime

from ..common.config import settings
from ..common.logging import logger
from ..repos.conversations_repo import ConversationsRepo
from ..repos.tenants_repo import TenantsRepo
from ..domain.models import Message

from ..common.constants import (
    STATE_AWAITING_VERIFICATION,
    STATE_AWAITING_CHALLENGE,
)


class LanguageService:
    """
    Odpowiada za wykrywanie i utrzymywanie language_code dla rozmów.
    """

    def __init__(
        self,
        conv: ConversationsRepo | None = None,
        tenants: TenantsRepo | None = None,
    ) -> None:
        self.conv = conv or ConversationsRepo()
        self.tenants = tenants or TenantsRepo()
        # klient Comprehend trzymamy tutaj, żeby go nie tworzyć za każdym razem
        self._comprehend = boto3.client(
            "comprehend",
            # Detekcja języka jest na ścieżce krytycznej latency.
            # Preferujemy szybki fallback (tenant/rozmowa) zamiast długiego czekania.
            config=Config(read_timeout=1, connect_timeout=1, retries={"max_attempts": 1}),
        )

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def resolve_and_persist_language(self, msg: Message) -> str:
        """
        Ustala język konwersacji per numer:
        1) explicit msg.language_code (np. z WWW),
        2) wykryty język z treści (Comprehend),
        3) language_code z istniejącej rozmowy,
        4) language_code tenanta,
        5) global default.

        DLA ISTNIEJĄCEJ ROZMOWY:
        - nie nadpisuje state_machine_status ani last_intent.
        """
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        # 1) jeżeli kanał podał język – traktujemy jako źródło prawdy
        if getattr(msg, "language_code", None):
            lang = msg.language_code
            existing = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id)
            if existing:
                # aktualizujemy tylko language_code
                self.conv.upsert_conversation(
                    msg.tenant_id,
                    channel,
                    channel_user_id,
                    language_code=lang,
                )
            else:
                # nowa rozmowa – tworzymy rekord
                self.conv.upsert_conversation(
                    msg.tenant_id,
                    channel,
                    channel_user_id,
                    language_code=lang,
                )
            return lang

        # 2) pobierz istniejącą rozmowę (jeśli jest)
        existing = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id)
        existing_lang = existing.get("language_code") if existing else None
        existing_state = (existing or {}).get("state_machine_status")

        if existing_lang and existing_state in (STATE_AWAITING_VERIFICATION, STATE_AWAITING_CHALLENGE):
            if self._looks_like_verification_code(msg.body or ""):
                return existing_lang

        if existing_lang and (msg.body or "").strip().upper().startswith("KOD:"):
            if self._looks_like_verification_code(msg.body or ""):
                return existing_lang

        # Optymalizacja: Comprehend jest kosztowny (sieć) i nie może odpalać się
        # dla każdej wiadomości. Zasady:
        #    - dla istniejących rozmów trzymamy się już ustalonego language_code,
        #    - dla nowych rozmów preferujemy język tenanta (jeśli jest ustawiony),
        #    - Comprehend uruchamiamy tylko, gdy tenant ma language_code="auto"
        #      albo nie ma żadnego języka (fallback do global default).

        tenant = self.tenants.get(msg.tenant_id) or {}
        tenant_lang_raw = (tenant.get("language_code") or "").strip()
        tenant_lang = tenant_lang_raw or settings.get_default_language()

        # jeśli rozmowa już ma język – używamy go (bez kosztownej detekcji)
        if existing_lang:
            self.conv.upsert_conversation(
                tenant_id=msg.tenant_id,
                channel=msg.channel,
                channel_user_id=msg.channel_user_id,
                language_code=existing_lang,
            )
            return existing_lang

        detected = None
        if (tenant_lang_raw.lower() == "auto"):
            detected = self._detect_language(msg.body or "")

        # finalny wybór – preferujemy wykryty, ale nie jest wymagany
        lang = detected or tenant_lang
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=msg.channel,
            channel_user_id=msg.channel_user_id,
            language_code=lang,
        )        
        return lang

    # ------------------------------------------------------------------ #
    #  Detekcja języka (Amazon Comprehend)
    # ------------------------------------------------------------------ #

    def _detect_language(self, text: str) -> Optional[str]:
        """
        Neutralna detekcja języka z użyciem Amazon Comprehend.

        - loguje błędy,
        - działa dla dowolnego języka obsługiwanego przez Comprehend,
        - przy krótkich tekstach może zwrócić None.
        """
        t = (text or "").strip()
        if not t:
            logger.debug({"sender": "routing", "event": "lang_detect_empty_text"})
            return None

        # bardzo krótkie wiadomości ignorujemy
        if len(t) < 5:
            return None

        sample = t[:4000]  # limit Comprehend
        try:
            resp = self._comprehend.detect_dominant_language(Text=sample)
        except Exception as e:  # noqa: BLE001
            logger.error(
                {
                    "sender": "routing",
                    "error": "comprehend_detect_failed",
                    "details": str(e),
                    "text_preview": sample[:40],
                }
            )
            return None

        langs = resp.get("Languages") or []
        if not langs:
            logger.warning(
                {
                    "sender": "routing",
                    "event": "comprehend_no_languages",
                    "text_preview": sample[:40],
                }
            )
            return None

        top = max(langs, key=lambda x: x.get("Score", 0.0))
        code = top.get("LanguageCode")
        score = float(top.get("Score") or 0.0)

        logger.info(
            {
                "sender": "routing",
                "event": "comprehend_detect_result",
                "code": code,
                "score": score,
            }
        )

        # gdy Comprehend jest mało pewny – oddajemy decyzję flow’om
        if score < 0.5:
            return None

        return code or None
    
    def _looks_like_verification_code(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False

        tu = t.upper()
        if tu.startswith("KOD:"):
            code = tu.split("KOD:", 1)[1].strip()
            return bool(re.fullmatch(r"[A-Z0-9]{4,12}", code))

        if re.fullmatch(r"\d{4,8}", t):
            return True

        if re.fullmatch(r"[A-Za-z0-9]{4,12}", t) and re.search(r"\d", t):
            return True

        return False
