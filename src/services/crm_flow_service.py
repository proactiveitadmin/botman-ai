from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime
import time
import re
import hmac

from ..common.logging import logger
from ..common.utils import new_id, build_reply_action
from ..domain.models import Message, Action
from ..services.crm_service import CRMService
from .clients_factory import ClientsFactory
from ..services.template_service import TemplateService
from ..adapters.email_client import EmailClient
from ..common.security import otp_hash
from ..repos.conversations_repo import ConversationsRepo
from ..repos.members_index_repo import MembersIndexRepo

from ..common.constants import (
    STATE_AWAITING_VERIFICATION,
    STATE_AWAITING_CONFIRMATION,
    STATE_AWAITING_CHALLENGE,
    STATE_AWAITING_MESSAGE,
)


class CRMFlowService:
    """
    Odpowiada za logikę CRM:
    - weryfikacja (web / challenge),
    - kontrakt, saldo,
    - lista zajęć, wybór zajęć, potwierdzanie rezerwacji,
    - powiązanie WWW <-> WhatsApp.

    RoutingService tylko orkiestruje i woła metody tej klasy.
    """

    def __init__(
        self,
        crm: CRMService | None = None,
        _clients_factory: ClientsFactory | None = None,
        tpl: TemplateService | None = None,
        conv: ConversationsRepo | None = None,
        members_index: MembersIndexRepo | None = None,
    ) -> None:
        self._clients_factory = ClientsFactory()
        self.crm = crm or CRMService(clients_factory=self._clients_factory)
        self.tpl = tpl or TemplateService()
        self.conv = conv or ConversationsRepo()
        self.members_index = members_index or MembersIndexRepo()

        # cache słów typu TAK/NIE z templatek
        self._words_cache: dict[tuple[str, str, str], set[str]] = {}

    # ------------------------------------------------------------------ #
    #  Helpers ogólne (skopiowane z RoutingService)
    # ------------------------------------------------------------------ #

    def _reply(self, msg, lang, body, channel=None, channel_user_id=None):
        return build_reply_action(msg, lang, body, channel, channel_user_id)


    def _pending_key(self, phone: str) -> str:
        """
        Klucz pod którym trzymamy w DDB oczekującą rezerwację
        lub listę zajęć dla numeru telefonu.
        (kopiuj z RoutingService)
        """
        return f"pending#{phone}"

    def reserve_class_with_id_core(
        self,
        msg: Message,
        lang: str,
        class_id: str,
        member_id: str,
        class_meta: Optional[dict] = None,
    ) -> List[Action]:
        """
        Tworzy pending rezerwację i wysyła prośbę o potwierdzenie.
        class_meta – opcjonalnie: class_name, class_date, class_time.
        Jeśli class_meta nie jest podane, spróbujemy dociągnąć dane z CRM.
        """
        # 1) Jeśli nie mamy metadanych, dociągamy je z CRM (PerfectGym)
        if class_meta is None:
            details: dict = {}
            try:
                details = self.crm.get_class_by_id(
                    tenant_id=msg.tenant_id,
                    class_id=class_id,
                ) or {}
            except Exception:
                details = {}

            start = str(
                details.get("startDate") or details.get("startdate") or ""
            )
            class_date = start[:10] if len(start) >= 10 else None
            class_time = start[11:16] if len(start) >= 16 else None

            class_type = None
            class_type_raw = details.get("classType") or {}
            if isinstance(class_type_raw, dict):
                class_type = class_type_raw.get("name") or None

            class_meta = {
                "class_name": class_type,
                "class_date": class_date,
                "class_time": class_time,
            }

        idem = new_id("idem-")

        # 2) Zapis pending do DDB
        item = {
            "pk": self._pending_key(msg.from_phone),
            "sk": "pending",
            "class_id": class_id,
            "member_id": member_id,
            "idempotency_key": idem,
        }
        if class_meta:
            # spodziewane pola: class_name, class_date, class_time
            item.update(class_meta)

        self.conv.put(item)

        # 3) Ustaw stan na oczekiwanie potwierdzenia
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=msg.channel or "whatsapp",
            channel_user_id=msg.channel_user_id or msg.from_phone,
            last_intent="reserve_class",
            state_machine_status=STATE_AWAITING_CONFIRMATION,
            language_code=lang,
        )

        # 4) Pytanie o potwierdzenie – od razu używamy nazwy / daty / godziny
        context = {
            "class_id": class_id,
            "class_name": item.get("class_name") or class_id,
            "class_date": item.get("class_date"),
            "class_time": item.get("class_time"),
        }

        body = self.tpl.render_named(
            msg.tenant_id,
            "reserve_class_confirm",
            lang,
            context,
        )
        return [self._reply(msg, lang, body)]
        

    def _get_words_set(
        self,
        tenant_id: str,
        template_name: str,
        lang: str | None = None,
    ) -> set[str]:
        """
        Wczytuje listę słów (np. TAK / NIE) z Templates (per tenant + język),
        trzyma w cache.

        SKOPIUJ tu ciało obecnej metody `_get_words_set` z RoutingService
        1:1.
        """
        key = (tenant_id, template_name, lang or "")
        if key in self._words_cache:
            return self._words_cache[key]

        raw = self.tpl.render_named(tenant_id, template_name, lang, {})

        if not raw:
            words: set[str] = set()
            self._words_cache[key] = words
            return words

        parts = re.split(r"[\s,;]+", raw)
        words = {p.strip().lower() for p in parts if p.strip()}
        self._words_cache[key] = words
        return words

    # ------------------------------------------------------------------ #
    #  Weryfikacja / powiązanie WWW
    # ------------------------------------------------------------------ #

    def _generate_verification_code(self, length: int = 6) -> str:
        """
        Generuje prosty kod weryfikacyjny używany w flow WWW -> WhatsApp.

        SKOPIUJ ciało z `_generate_verification_code` z RoutingService.
        """
        import secrets
        import string

        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))
   
    def _whatsapp_wa_me_link(self, code: str) -> str:
        """Buduje link wa.me z predefiniowaną treścią zawierającą kod weryfikacyjny."""
        raw = settings.twilio_whatsapp_number  # np. "whatsapp:+48000000000"
        phone = raw.replace("whatsapp:", "") if raw else ""
        return f"https://wa.me/{phone}?text=KOD:{code}"

    def _render_first(
        self,
        tenant_id: str,
        lang: str,
        template_names: list[str],
        context: dict | None = None,
    ) -> str:
        """Renderuje pierwszą dostępną templatkę z listy; fallback na prosty tekst."""
        ctx = context or {}
        for name in template_names:
            try:
                body = self.tpl.render_named(tenant_id, name, lang, ctx)
            except Exception:
                body = None
            if body:
                return body
        # twardy fallback (nie powinien się zdarzyć, ale lepiej niż pustka)
        minutes = ctx.get("minutes")
        if minutes:
            return f"Weryfikacja jest tymczasowo zablokowana na {minutes} min. Czy chcesz połączyć się z obsługą lub założyć zgłoszenie?"
        return "Czy chcesz połączyć się z obsługą lub założyć zgłoszenie?"

    def _block_verification_15m_and_offer_options(
        self,
        msg: Message,
        conv: dict,
        lang: str,
    ) -> List[Action]:
        """Blokuje możliwość kolejnych prób weryfikacji na 15 minut i pyta o połączenie / task."""
        tenant_id = msg.tenant_id
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone
       
        now_ts = int(time.time())
        # Anti-bruteforce: globalna blokada weryfikacji (15 min po 3 błędach)
        blocked_until = int(conv.get("crm_verification_blocked_until") or 0)
        if blocked_until and now_ts < blocked_until:
            body = self._render_first(
                msg.tenant_id,
                lang,
                ["crm_challenge_blocked_connect_or_task", "crm_challenge_fail_connect_or_task", "crm_challenge_fail_handover"],
                {"minutes": max(int((blocked_until - now_ts + 59) // 60), 1)},
            )
            return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

        blocked_until = now_ts + 15 * 60

        self.conv.upsert_conversation(
            tenant_id=tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            crm_verification_blocked_until=blocked_until,
            state_machine_status=STATE_AWAITING_MESSAGE,
        )
        self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)

        body = self._render_first(
            tenant_id,
            lang,
            ["crm_challenge_fail_connect_or_task", "crm_challenge_blocked_connect_or_task", "crm_challenge_fail_handover"],
            {"minutes": 15},
        )
        return [self._reply(msg, lang, body)]

    def _restart_email_otp_verification(
        self,
        msg: Message,
        conv: dict,
        lang: str,
        reason: str,
    ) -> List[Action]:
        """Restartuje OTP (np. po wygaśnięciu lub rozjechaniu stanu) i wysyła nowy kod."""
        tenant_id = msg.tenant_id
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        # jeżeli jesteśmy zablokowani – nie wysyłamy ponownie
        now_ts = int(time.time())
        blocked_until = int(conv.get("crm_verification_blocked_until") or 0)
        if blocked_until and now_ts < blocked_until:
            body = self._render_first(
                tenant_id,
                lang,
                ["crm_challenge_blocked_connect_or_task", "crm_challenge_fail_connect_or_task", "crm_challenge_fail_handover"],
                {"minutes": max(int((blocked_until - now_ts + 59) // 60), 1)},
            )
            self.conv.upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
            )
            self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
            return [self._reply(msg, lang, body)]

        # email musi być znany (z poprzedniej próby) lub pobieramy z CRM
        email = (conv.get("crm_otp_email") or "").strip()
        if not email:
            try:
                members_resp = self.crm.get_member_by_phone(tenant_id, msg.from_phone)
                items = (members_resp or {}).get("value") or []
                if items:
                    email = (items[0].get("email") or "").strip()
            except Exception:
                email = ""

        if not email:
            body = self.tpl.render_named(tenant_id, "crm_challenge_missing_email", lang, {})
            # wychodzimy ze stanu challenge, żeby nie zapętlać kolejnych wiadomości
            self.conv.upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
            )
            self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
            return [self._reply(msg, lang, body)]

        # generujemy nowy OTP i wysyłamy email
        verification_code = self._generate_verification_code(length=6)
        expires_at = now_ts + 5 * 60
        otp_h = otp_hash(tenant_id, "crm_email_otp", verification_code)

        body_email = self.tpl.render_named(
            tenant_id,
            "crm_code_via_email",
            lang,
            {"verification_code": verification_code, "ttl_minutes": 5},
        )

        try:
            EmailClient().send_otp(
                tenant_id=tenant_id,
                to_email=email,
                subject="Verification code",
                body_text=body_email,
            )
        except Exception as e:
            logger.error({"sender": "crm_flow", "event": "send_otp_failed", "details": str(e)})
            # nie zostawiamy usera w awaiting_challenge
            self.conv.upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
            )
            self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
            body = self._render_first(
                tenant_id,
                lang,
                ["crm_challenge_send_failed", "crm_challenge_fail_connect_or_task", "crm_challenge_fail_handover"],
                {},
            )
            return [self._reply(msg, lang, body)]

        # zapisujemy nowy stan OTP
        self.conv.upsert_conversation(
            tenant_id=tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            crm_challenge_type="email_otp",
            crm_otp_hash=otp_h,
            crm_otp_expires_at=expires_at,
            crm_otp_attempts_left=3,
            crm_otp_last_sent_at=now_ts,
            crm_otp_email=email,
            state_machine_status=STATE_AWAITING_CHALLENGE,
        )

        # komunikat do usera – "ponawiamy"
        intro = self._render_first(
            tenant_id,
            lang,
            ["crm_challenge_restart_verification", "crm_challenge_retry"],
            {"attempts_left": 3},
        )
        ask = self.tpl.render_named(tenant_id, "crm_challenge_ask_email_code", lang, {"email": email})
        body = f"{intro}\n\n{ask}" if intro and ask else (ask or intro)
        return [self._reply(msg, lang, body)]
        
    def _reply_verification_blocked(
        self, msg: Message, lang: str, blocked_until_ts: int
    ) -> List[Action]:
        """Komunikat dla blokady weryfikacji (anty-atak / brute-force)."""
        now_ts = int(time.time())
        minutes = max(1, int((blocked_until_ts - now_ts) // 60))
        body = self.tpl.render_named(
            msg.tenant_id,
            "crm_verification_blocked",
            lang,
            {"minutes": minutes},
        )
        return [
            self._reply(
                msg,
                lang,
                body,
                channel=msg.channel,
                channel_user_id=msg.channel_user_id or msg.from_phone,
            )
        ]

    def _is_crm_verification_blocked(self, conv: dict) -> tuple[bool, int]:
        """Zwraca (is_blocked, blocked_until_ts)."""
        now_ts = int(time.time())
        blocked_until = int(conv.get("crm_verification_blocked_until") or 0)
        return (blocked_until > now_ts, blocked_until)

    def _block_crm_verification_and_offer_options(
        self,
        msg: Message,
        lang: str,
        *,
        reason: str = "too_many_attempts",
        cooldown_seconds: int = 30 * 60,
    ) -> List[Action]:
        """Po 3 nieudanych próbach: blokujemy i pytamy o połączenie / task (bez handover)."""
        now_ts = int(time.time())
        tenant_id = msg.tenant_id
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        self.conv.upsert_conversation(
            tenant_id=tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            crm_verification_blocked_until=now_ts + cooldown_seconds,
            crm_verification_block_reason=reason,
            state_machine_status=STATE_AWAITING_MESSAGE,
        )
        # Czyścimy stan challenge, żeby nie dało się dalej brute-force na tym samym kontekście
        self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)

        body = self.tpl.render_named(tenant_id, "crm_challenge_fail_options", lang, {})
        return [
            self._reply(
                msg,
                lang,
                body,
                channel=msg.channel,
                channel_user_id=msg.channel_user_id or msg.from_phone,
            )
        ]


    def ensure_crm_verification(
        self,
        msg: Message,
        conv: dict,
        lang: str,
        post_intent: str | None = None,
        post_slots: dict | None = None,
    ) -> Dict[str, Any]:
        """
        Sprawdza, czy użytkownik ma ważną strong-verification dla PerfectGym.
        Jeśli nie:
         - na WWW: flow z kodem i linkiem wa.me (awaiting_verification),
         - na WhatsApp: flow challenge (email OTP).

        Zwraca:
         - None, jeśli wszystko OK i można kontynuować operację PG,
         - listę akcji (reply), jeśli flow weryfikacji został zainicjowany/obsłużony
           i dalsze przetwarzanie należy wstrzymać.

        WAŻNE: nie utrzymujemy użytkownika w STATE_AWAITING_CHALLENGE, jeżeli OTP wygasło
        lub user został zablokowany – tak, aby mógł dalej korzystać z FAQ i innych flow.
        """
        now_ts = int(time.time())

        crm_level = conv.get("crm_verification_level") or "none"
        crm_until = int(conv.get("crm_verified_until") or 0)

        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        # 0) jeśli jest aktywna blokada weryfikacji – nie inicjujemy challenge (ochrona przed atakami)
        blocked_until = int(conv.get("crm_verification_blocked_until") or 0)
        if blocked_until and now_ts < blocked_until:
            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_challenge_fail_handover",
                lang,
                {},
            )
            # upewnij się, że nie tkwimy w awaiting_challenge (żeby FAQ działało)
            self.conv.upsert_conversation(
                tenant_id=msg.tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
                language_code=lang,
            )
            return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

        # 1) strong + nieprzeterminowane → OK
        if crm_level == "strong" and crm_until >= now_ts:
            return None

        # 2) Kanał WWW → flow: kod + WhatsApp
        if channel == "web":
            verification_code = self._generate_verification_code()
            wa_link = self._whatsapp_wa_me_link(verification_code)

            self.conv.upsert_conversation(
                tenant_id=msg.tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                verification_code=verification_code,
                crm_member_id=None,
                crm_verification_level="none",
                crm_verified_until=None,
                state_machine_status=STATE_AWAITING_VERIFICATION,
                crm_post_intent=post_intent,
                crm_post_slots=post_slots or {},
                language_code=lang,
            )

            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_web_verification_required",
                lang,
                {
                    "verification_code": verification_code,
                    "whatsapp_link": wa_link,
                },
            )

            return [
                self._reply(
                    msg,
                    lang,
                    body,
                    channel="web",
                    channel_user_id=channel_user_id,
                )
            ]

        # 3) Kanał WhatsApp → flow email OTP.
        # Uwaga: NIE ustawiamy STATE_AWAITING_CHALLENGE, dopóki nie mamy emaila
        # i dopóki wysyłka OTP faktycznie się powiedzie.
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            crm_post_intent=post_intent,
            crm_post_slots=post_slots or {},
            language_code=lang,
        )

        # 3.1) pobierz membera z PerfectGym (po telefonie) i jego email
        email: str | None = None
        try:
            members_resp = self.crm.get_member_by_phone(msg.tenant_id, msg.from_phone)
            items = (members_resp or {}).get("value") or []
            if items:
                email = (items[0].get("email") or "").strip()
        except Exception:
            email = None

        if not email:
            # Nie blokujemy bota w awaiting_challenge – user może wrócić do FAQ.
            self.conv.upsert_conversation(
                tenant_id=msg.tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
                language_code=lang,
            )
            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_challenge_missing_email",
                lang,
                {},
            )
            return [self._reply(msg, lang, body, channel="whatsapp", channel_user_id=channel_user_id)]

        # 3.2) ochrona przed spamem resend (min 60s) – bazujemy na aktualnym conv (z DDB jeśli trzeba)
        last_sent = int(conv.get("crm_otp_last_sent_at") or 0)
        if now_ts - last_sent < 60:
            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_challenge_email_code_already_sent",
                lang,
                {},
            )
            # pozostajemy w aktualnym stanie (nie wymuszamy challenge)
            return [self._reply(msg, lang, body, channel="whatsapp", channel_user_id=channel_user_id)]

        # 3.3) wygeneruj OTP i wyślij na email
        verification_code = self._generate_verification_code(length=6)
        expires_at = now_ts + 5 * 60
        otp_h = otp_hash(msg.tenant_id, "crm_email_otp", verification_code)

        body_email = self.tpl.render_named(
            msg.tenant_id,
            "crm_code_via_email",
            lang,
            {"verification_code": verification_code, "ttl_minutes": 5},
        )

        sent_ok = False
        try:
            sent_ok = bool(
                EmailClient().send_otp(
                    tenant_id=msg.tenant_id,
                    to_email=email,
                    subject="Verification code",
                    body_text=body_email,
                )
            )
        except Exception:
            sent_ok = False

        if not sent_ok:
            # Jeśli wysyłka nie wyszła, nie ustawiamy await_challenge – user nie powinien utknąć.
            self.conv.upsert_conversation(
                tenant_id=msg.tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
                language_code=lang,
            )
            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_challenge_fail_handover",
                lang,
                {},
            )
            return [self._reply(msg, lang, body, channel="whatsapp", channel_user_id=channel_user_id)]

        # 3.4) ustaw stan awaiting_challenge (email_otp)
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            crm_challenge_type="email_otp",
            crm_challenge_attempts=0,
            crm_otp_hash=otp_h,
            crm_otp_expires_at=expires_at,
            crm_otp_attempts_left=3,
            crm_otp_last_sent_at=now_ts,
            crm_otp_email=email,
            state_machine_status=STATE_AWAITING_CHALLENGE,
            crm_post_intent=post_intent,
            crm_post_slots=post_slots or {},
            language_code=lang,
        )

        body = self.tpl.render_named(
            msg.tenant_id,
            "crm_challenge_ask_email_code",
            lang,
            {"email": email},
        )

        return [self._reply(msg, lang, body, channel="whatsapp", channel_user_id=channel_user_id)]

    def handle_crm_challenge(
        self,
        msg: Message,
        conv: dict,
        lang: str,
    ) -> List[Action]:
        """
        Użytkownik jest w stanie awaiting_challenge – traktujemy wiadomość
        jako odpowiedź na challenge (OTP / DOB / inne).

        Poprawki:
        - "expired" nie zapętla bota: wychodzimy ze stanu challenge, user może używać FAQ.
        - po 3 błędnych próbach: ustawiamy blokadę 15 minut (crm_verification_blocked_until),
          wychodzimy ze stanu challenge i NIE robimy handover automatycznie.
        - utrwalamy language_code, żeby wpisanie kodu nie przestawiało języka na EN.
        """
        text = (msg.body or "").strip()
        tenant_id = msg.tenant_id
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        now_ts = int(time.time())
        challenge_type = conv.get("crm_challenge_type") or "dob"

        # globalna blokada (anti-attack) – nie pozwalamy na weryfikację, ale nie blokujemy bota
        blocked_until = int(conv.get("crm_verification_blocked_until") or 0)
        if blocked_until and now_ts < blocked_until:
            # upewnij się, że nie tkwimy w challenge
            self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
            self.conv.upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
                language_code=lang,
            )
            body = self.tpl.render_named(tenant_id, "crm_challenge_fail_handover", lang, {})
            return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

        # ------------------------------------------------------------------
        # Email OTP
        # ------------------------------------------------------------------
        if challenge_type == "email_otp":
            expires_at = int(conv.get("crm_otp_expires_at") or 0)
            attempts_left = int(conv.get("crm_otp_attempts_left") or 0)
            expected = (conv.get("crm_otp_hash") or "").strip()

            # brak oczekiwanego hasha = niespójny stan (nie "expired") – resetujemy challenge
            if not expected:
                self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
                self.conv.upsert_conversation(
                    tenant_id=tenant_id,
                    channel=channel,
                    channel_user_id=channel_user_id,
                    state_machine_status=STATE_AWAITING_MESSAGE,
                    language_code=lang,
                )
                body = self.tpl.render_named(tenant_id, "crm_challenge_expired", lang, {})
                return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

            if now_ts > expires_at:
                # nie zapętlamy: wychodzimy z challenge, user może pytać o FAQ
                self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
                self.conv.upsert_conversation(
                    tenant_id=tenant_id,
                    channel=channel,
                    channel_user_id=channel_user_id,
                    state_machine_status=STATE_AWAITING_MESSAGE,
                    language_code=lang,
                )
                body = self.tpl.render_named(tenant_id, "crm_challenge_expired", lang, {})
                return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

            if attempts_left <= 0:
                # stan niespójny – traktuj jak blokadę
                blocked_until = now_ts + 15 * 60
                self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
                self.conv.upsert_conversation(
                    tenant_id=tenant_id,
                    channel=channel,
                    channel_user_id=channel_user_id,
                    crm_verification_blocked_until=blocked_until,
                    state_machine_status=STATE_AWAITING_MESSAGE,
                    language_code=lang,
                )
                body = self.tpl.render_named(tenant_id, "crm_challenge_fail_handover", lang, {})
                return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

            # weryfikacja OTP
            given = otp_hash(tenant_id, "crm_email_otp", text)
            is_correct = hmac.compare_digest(expected, given)

            if not is_correct:
                attempts_left = max(attempts_left - 1, 0)
                self.conv.upsert_conversation(
                    tenant_id=tenant_id,
                    channel=channel,
                    channel_user_id=channel_user_id,
                    crm_otp_attempts_left=attempts_left,
                    language_code=lang,
                )

                if attempts_left <= 0:
                    # BLOKADA 15 min + wyjście z challenge (żeby nie blokować FAQ)
                    blocked_until = now_ts + 15 * 60
                    self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
                    self.conv.upsert_conversation(
                        tenant_id=tenant_id,
                        channel=channel,
                        channel_user_id=channel_user_id,
                        crm_verification_blocked_until=blocked_until,
                        state_machine_status=STATE_AWAITING_MESSAGE,
                        language_code=lang,
                    )
                    body = self.tpl.render_named(tenant_id, "crm_challenge_fail_handover", lang, {})
                    return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

                body = self.tpl.render_named(
                    tenant_id,
                    "crm_challenge_retry",
                    lang,
                    {"attempts_left": attempts_left},
                )
                return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

            # poprawny OTP → strong verification
            ttl = now_ts + 15 * 60

            post_intent = conv.get("crm_post_intent")
            post_slots = conv.get("crm_post_slots") or {}

            member_id: str | None = None
            try:
                members_resp = self.crm.get_member_by_phone(tenant_id, msg.from_phone)
                items = (members_resp or {}).get("value") or []
                if items:
                    member_id = str(items[0].get("id") or items[0].get("Id"))
            except Exception:
                member_id = None

            if not member_id and self.members_index:
                try:
                    member = self.members_index.get_member(tenant_id, msg.from_phone)
                    if member:
                        member_id = str(member.get("id") or member.get("member_id"))
                except Exception:
                    member_id = None

            self.conv.upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
                crm_member_id=member_id,
                crm_verification_level="strong",
                crm_verified_until=ttl,
                language_code=lang,
            )

            self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)

            success_body = self.tpl.render_named(tenant_id, "crm_challenge_success", lang, {})
            actions: List[Action] = [
                self._reply(msg, lang, success_body, channel=channel, channel_user_id=channel_user_id)
            ]

            # automatyczne dokończenie pierwotnej operacji PG
            if post_intent == "crm_member_balance":
                if member_id:
                    actions.extend(self.crm_member_balance_core(msg, lang, member_id))
                else:
                    body = self.tpl.render_named(tenant_id, "crm_member_not_linked", lang, {})
                    actions.append(self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id))

            elif post_intent == "crm_contract_status":
                if member_id:
                    actions.extend(self.crm_contract_status_core(msg, lang, member_id))
                else:
                    body = self.tpl.render_named(tenant_id, "crm_member_not_linked", lang, {})
                    actions.append(self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id))

            elif post_intent == "reserve_class":
                post_class_id = (post_slots or {}).get("class_id")
                if member_id and post_class_id:
                    actions.extend(self.reserve_class_with_id_core(msg, lang, post_class_id, member_id))
                else:
                    body = self.tpl.render_named(tenant_id, "crm_member_not_linked", lang, {})
                    actions.append(self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id))

            return actions

        # ------------------------------------------------------------------
        # Inne challenge (np. DOB) – weryfikacja przez CRM
        # ------------------------------------------------------------------
        attempts = int(conv.get("crm_challenge_attempts") or 0)
        is_correct = self.verify_challenge_answer(
            tenant_id=tenant_id,
            phone=msg.from_phone,
            challenge_type=challenge_type,
            answer=text,
        )

        if not is_correct:
            attempts += 1
            self.conv.upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                crm_challenge_attempts=attempts,
                language_code=lang,
            )

            if attempts >= 3:
                blocked_until = now_ts + 15 * 60
                self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
                self.conv.upsert_conversation(
                    tenant_id=tenant_id,
                    channel=channel,
                    channel_user_id=channel_user_id,
                    crm_verification_blocked_until=blocked_until,
                    state_machine_status=STATE_AWAITING_MESSAGE,
                    language_code=lang,
                )
                body = self.tpl.render_named(tenant_id, "crm_challenge_fail_handover", lang, {})
                return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

            body = self.tpl.render_named(
                tenant_id,
                "crm_challenge_retry",
                lang,
                {"attempts_left": 3 - attempts},
            )
            return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]

        # sukces DOB (lub innego challenge)
        ttl = now_ts + 15 * 60
        self.conv.upsert_conversation(
            tenant_id=tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            state_machine_status=STATE_AWAITING_MESSAGE,
            crm_verification_level="strong",
            crm_verified_until=ttl,
            language_code=lang,
        )
        self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)
        body = self.tpl.render_named(tenant_id, "crm_challenge_success", lang, {})
        return [self._reply(msg, lang, body, channel=channel, channel_user_id=channel_user_id)]
    
    def _finalize_crm_verification_success(
        self,
        msg: Message,
        conv: dict,
        lang: str,
    ) -> List[Action]:
        """Wspólna ścieżka po pozytywnej weryfikacji (OTP/DOB) + dokończenie post_intent."""
        tenant_id = msg.tenant_id
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        now_ts = int(time.time())
        ttl = now_ts + 15 * 60  # 15 minut ważności weryfikacji

        post_intent = conv.get("crm_post_intent")
        post_slots = conv.get("crm_post_slots") or {}

        # 1) spróbuj pobrać membera z PerfectGym po numerze telefonu
        member_id: str | None = None
        try:
            members_resp = self.crm.get_member_by_phone(tenant_id, msg.from_phone)
            items = (members_resp or {}).get("value") or []
            if items:
                member_id = str(items[0].get("id") or items[0].get("Id"))
        except Exception:
            member_id = None

        # 2) fallback na MembersIndex, jeśli PG nic nie zwróci
        if not member_id and self.members_index:
            try:
                member = self.members_index.get_member(tenant_id, msg.from_phone)
                if member:
                    member_id = str(member.get("id") or member.get("member_id"))
            except Exception:
                member_id = None

        # aktualizacja rozmowy – wychodzimy ze stanu challenge
        self.conv.upsert_conversation(
            tenant_id=tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            state_machine_status=STATE_AWAITING_MESSAGE,
            crm_member_id=member_id,
            crm_verification_level="strong",
            crm_verified_until=ttl,
            crm_verification_blocked_until=None,
        )
        self.clear_crm_challenge_state(tenant_id, channel, channel_user_id)

        success_body = self.tpl.render_named(
            tenant_id,
            "crm_challenge_success",
            lang,
            {},
        )

        actions: List[Action] = [
            self._reply(
                msg,
                lang,
                success_body,
                channel=msg.channel,
                channel_user_id=msg.channel_user_id,
            )
        ]

        # automatyczne dokończenie pierwotnej operacji PG
        if post_intent == "crm_member_balance":
            if member_id:
                actions.extend(self.crm_member_balance_core(msg, lang, member_id))
            else:
                body = self.tpl.render_named(tenant_id, "crm_member_not_linked", lang, {})
                actions.append(self._reply(msg, lang, body))

        elif post_intent == "crm_contract_status":
            if member_id:
                actions.extend(self.crm_contract_status_core(msg, lang, member_id))
            else:
                body = self.tpl.render_named(tenant_id, "crm_member_not_linked", lang, {})
                actions.append(self._reply(msg, lang, body))

        elif post_intent == "reserve_class":
            post_class_id = (post_slots or {}).get("class_id")
            if member_id and post_class_id:
                actions.extend(
                    self.reserve_class_with_id_core(
                        msg,
                        lang,
                        post_class_id,
                        member_id,
                    )
                )
            else:
                body = self.tpl.render_named(tenant_id, "crm_member_not_linked", lang, {})
                actions.append(self._reply(msg, lang, body))

        return actions

    def verify_challenge_answer(
        self,
        tenant_id: str,
        phone: str,
        challenge_type: str,
        answer: str,
    ) -> bool:
        """
        Weryfikacja odpowiedzi na challenge PG.

        Docelowo logika powinna siedzieć w CRMService (odpytywanie PerfectGym
        / wewnętrznego indeksu członków). Tutaj delegujemy do metody
        crm.verify_member_challenge.

        Zwraca True/False.
        """
        answer = (answer or "").strip()
        if not answer:
            return False

        try:
            return bool(
                self.crm.verify_member_challenge(
                    tenant_id=tenant_id,
                    phone=phone,
                    challenge_type=challenge_type,
                    answer=answer,
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                {
                    "sender": "routing",
                    "event": "crm_challenge_verify_failed",
                    "details": str(e),
                }
            )
            return False

    def clear_crm_challenge_state(
        self, tenant_id: str, channel: str, channel_user_id: str
    ) -> None:
        """
        """
        try:
            self.conv.clear_crm_challenge(tenant_id, channel, channel_user_id)
        except AttributeError:
            # fallback na wypadek gdyby repo jeszcze nie miało tej metody
            pass

    # ------------------------------------------------------------------ #
    #  Flows: saldo, kontrakt, zajęcia
    # ------------------------------------------------------------------ #

    def crm_member_balance_core(
        self, msg: Message, lang: str, member_id: str
    ) -> List[Action]:
        """
        """
        balance_resp = self.crm.get_member_balance(
            tenant_id=msg.tenant_id,
            member_id=member_id,
        )
        balance = balance_resp.get("balance", 0)

        body = self.tpl.render_named(
            msg.tenant_id,
            "crm_member_balance",
            lang,
            {"balance": balance},
        )
        return [self._reply(msg, lang, body)]

    def crm_contract_status_core(
        self, msg: Message, lang: str, member_id: str
    ) -> List[Action]:
        """
        Zwraca status kontraktu na podstawie member_id z PerfectGym.
        Zakładamy, że wcześniej przeszedł `ensure_crm_verification`
        i w rozmowie mamy poprawne crm_member_id.
        """
        if not member_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_member_not_linked",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        contracts_resp = self.crm.get_contracts_by_member_id(
            tenant_id=msg.tenant_id,
            member_id=member_id,
        )
        contracts = contracts_resp.get("value", []) or []

        if not contracts:
            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_contract_not_found",
                lang,
                {
                    "email": slots.get("email", ""),
                    "phone": slots.get("phone", ""),
                },
            )
            return [self._reply(msg, lang, body)]

        current = next(
            (c for c in contracts if c.get("status") == "Current"),
            contracts[0],
        )

        status = current.get("status") or "Unknown"
        start_date = (current.get("startDate") or "")[:10]
        end_date_raw = current.get("endDate")
        end_date = (end_date_raw or "")[:10] if end_date_raw else ""

        payment_plan = current.get("paymentPlan") or {}
        plan_name = payment_plan.get("name") or ""
        balance_resp = self.crm.get_member_balance(
            tenant_id=msg.tenant_id,
            member_id=int(member_id) if str(member_id).isdigit() else member_id,
        )
        current_balance = balance_resp.get("currentBalance")
        negative_raw = balance_resp.get("negativeBalanceSince")
        negative_since = negative_raw[:10] if negative_raw else ""


        context = {
            "plan_name": plan_name,
            "status": status,
            "start_date": start_date,
            "end_date": end_date or "",
            "current_balance": current_balance,
            "negative_balance_since": negative_since
        }

        body = self.tpl.render_named(
            msg.tenant_id,
            "crm_contract_details",
            lang,
            context,
        )

        return [self._reply(msg, lang, body)]

    def is_crm_member(self, tenant_id: str, phone: str) -> bool:
        mt = self.crm.get_member_type_by_phone(tenant_id, phone)
        return bool(mt) and mt.lower() == "member"
        
    def set_pending_marketing_consent_change(self, msg: Message, kind: str):
        self.conv.put(
            self._pending_key(msg.from_phone),
            "pending",
            {
                "kind": kind,  # "marketing_optout" | "marketing_optin"
                "created_at": int(time.time()),
                "member_id": member_id,
            },
        )


    def build_available_classes_response(
        self,
        msg: Message,
        lang: str,
        *,
        auto_confirm_single: bool = False,
        class_type_query: str | None = None,
        allow_selection: bool = True
    ) -> List[Action]:
        """
        Pobiera listę dostępnych zajęć z PG, buduje listę tekstową
        + zapisuje uproszczone dane w DDB (do późniejszego wyboru).
        """
        classes_resp = self.crm.get_available_classes(
            tenant_id=msg.tenant_id,
            top=10,
            class_type_query=class_type_query,
        )
        
        classes = classes_resp.get("value") or []
        
        if not allow_selection:
            auto_confirm_single = False
            
        if not classes:
            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_available_classes_empty",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]
            classes = classes_resp.get("value") or []

        # Jeśli jest dokładnie 1 pozycja, nie pokazujemy listy.
        # Od razu przechodzimy do standardowego flow rezerwacji (w tym weryfikacji PG).
        if auto_confirm_single and len(classes) == 1:
            c = classes[0] or {}
            start = str(c.get("startDate") or c.get("startdate") or "")
            date_str = start[:10] if len(start) >= 10 else "?"
            time_str = start[11:16] if len(start) >= 16 else "?"
            class_type = (c.get("classType") or {}).get("name") or "Class"

            # jeżeli wcześniej była zapisana lista, usuń ją, żeby nie mieszała w state machine
            try:
                self.conv.delete(self._pending_key(msg.from_phone), "classes")
            except Exception:
                pass

            selected = {
                "index": 1,
                "class_id": c.get("id"),
                "date": date_str,
                "time": time_str,
                "name": class_type,
                "start": start,
            }
            return self._start_reservation_from_selection(msg, lang, selected)
            
        lines: list[str] = []
        simplified: list[dict] = []

        for idx, c in enumerate(classes, start=1):
            start = str(c.get("startDate") or c.get("startdate") or "")
            date_str = start[:10] if len(start) >= 10 else "?"
            time_str = start[11:16] if len(start) >= 16 else "?"
            class_type = (c.get("classType") or {}).get("name") or "Class"

            attendees_count = c.get("attendeesCount") or 0
            attendees_limit = c.get("attendeesLimit")

            if attendees_limit is None:
                capacity_info = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_available_classes_capacity_no_limit",
                    lang,
                    {},
                )
            else:
                free = max(attendees_limit - attendees_count, 0)
                if free <= 0:
                    capacity_info = self.tpl.render_named(
                        msg.tenant_id,
                        "crm_available_classes_capacity_full",
                        lang,
                        {"limit": attendees_limit},
                    )
                else:
                    capacity_info = self.tpl.render_named(
                        msg.tenant_id,
                        "crm_available_classes_capacity_free",
                        lang,
                        {"free": free, "limit": attendees_limit},
                    )

            line = self.tpl.render_named(
                msg.tenant_id,
                "crm_available_classes_item",
                lang,
                {
                    "index": idx,
                    "date": date_str,
                    "time": time_str,
                    "name": class_type,
                    "capacity": capacity_info,
                },
            )
            lines.append(line)

            simplified.append(
                {
                    "index": idx,
                    "class_id": c.get("id"),
                    "date": date_str,
                    "time": time_str,
                    "name": class_type,
                    "start": start,
                }
            )

        body = self.tpl.render_named(
            msg.tenant_id,
            "crm_available_classes",
            lang,
            {"classes": "\n".join(lines)},
        )

        if allow_selection:
            # zapis listy klas do późniejszego wyboru
            self.conv.put(
                {
                    "pk": self._pending_key(msg.from_phone),
                    "sk": "classes",
                    "items": simplified,
                }
            )

            try:
                extra = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_available_classes_select_by_number",
                    lang,
                    {},
                )
            except Exception:
                extra = ""
            
            full_body = f"{body}\n\n{extra}" if extra else body
            
            return [self._reply(msg, lang, full_body)]
        return [self._reply(msg, lang, body)]


    def handle_class_selection(self, msg: Message, lang: str) -> List[Action]:      
        """
        Obsługa stanu STATE_AWAITING_CLASS_SELECTION – użytkownik wybiera
        zajęcia z wcześniej pokazanej listy.
        """
        text = (msg.body or "").strip().lower()

        classes_item = self.conv.get(self._pending_key(msg.from_phone), "classes")
        if not classes_item:
            return None

        items = classes_item.get("items") or []
        if not items:
            return None

        # 1) Użytkownik podał numer (np. "1", "nr 2")
        m = re.search(r"\b(\d{1,2})\b", text)
        if m:
            idx = int(m.group(1))
            selected = next((c for c in items if c.get("index") == idx), None)
            if not selected:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_available_classes_invalid_index",
                    lang,
                    {"max_index": len(items)},
                )
                return [self._reply(msg, lang, body)]
            return self._start_reservation_from_selection(msg, lang, selected)

        # 2) "dzisiaj"/"today" – filtrujemy po dzisiejszej dacie
        today = datetime.now().date().isoformat()  # "YYYY-MM-DD"
        if any(w in text for w in ["dzis", "dziś", "dzisiaj", "today"]):
            todays = [c for c in items if c.get("date") == today]
            if not todays:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_available_classes_no_today",
                    lang,
                    {},
                )
                return [self._reply(msg, lang, body)]

            if len(todays) == 1:
                return self._start_reservation_from_selection(msg, lang, todays[0])

            # kilka klas dzisiaj – pokaż ponumerowaną listę
            lines: list[str] = []
            for c in todays:
                line = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_available_classes_item",
                    lang,
                    {
                        "index": c["index"],
                        "date": c["date"],
                        "time": c["time"],
                        "name": c["name"],
                        "capacity": "",
                    },
                )
                lines.append(line)

            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_available_classes_today",
                lang,
                {"classes": "\n".join(lines)},
            )
            return [self._reply(msg, lang, body)]

        # 3) Użytkownik podał konkretną datę (ISO YYYY-MM-DD)
        iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if iso_match:
            date_str = iso_match.group(1)
            same_day = [c for c in items if c.get("date") == date_str]
            if not same_day:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_available_classes_no_classes_on_date",
                    lang,
                    {"date": date_str},
                )
                return [self._reply(msg, lang, body)]

            if len(same_day) == 1:
                return self._start_reservation_from_selection(msg, lang, same_day[0])

            lines: list[str] = []
            for c in same_day:
                line = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_available_classes_item",
                    lang,
                    {
                        "index": c["index"],
                        "date": c["date"],
                        "time": c["time"],
                        "name": c["name"],
                        "capacity": "",
                    },
                )
                lines.append(line)

            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_available_classes_today",
                lang,
                {"classes": "\n".join(lines)},
            )
            extra = self.tpl.render_named(
                msg.tenant_id,
                "crm_available_classes_select_by_number",
                lang,
                {},
            )
            full_body = f"{body}\n\n{extra}"

            return [self._reply(msg, lang, full_body)]

        # 4) Nic nie wybraliśmy – oddaj dalej do NLU / clarify
        return None


    def start_reservation_from_selection(
        self,
        msg: Message,
        lang: str,
        selection: dict,
    ) -> List[Action]:
        """
        Użytkownik wybrał konkretną klasę z listy.
        Tutaj pilnujemy:
        - że mamy class_id,
        - że użytkownik jest zweryfikowany w PG (w razie potrzeby wywołujemy challenge),
        - że pending rezerwacja używa prawdziwego member_id z PG.
        """
        class_id = selected.get("class_id")
        if not class_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "reserve_class_missing_id",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}

        # 1) Weryfikacja PG – jeśli potrzeba, zainicjuje challenge
        verify_resp = self.ensure_crm_verification(
            msg,
            conv,
            lang,
            post_intent="reserve_class",
            post_slots={"class_id": class_id},
        )
        if verify_resp:
            # tutaj kończymy – challenge / WWW verification przejmie flow
            return verify_resp

        # 2) Po weryfikacji PG oczekujemy crm_member_id w rozmowie
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}
        member_id = conv.get("crm_member_id")
        if not member_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_member_not_linked",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        class_meta = {
            "class_name": selected.get("name"),
            "class_date": selected.get("date"),
            "class_time": selected.get("time"),
        }

        return self.reserve_class_with_id_core(
            msg,
            lang,
            class_id=class_id,
            member_id=member_id,
            class_meta=class_meta,
        )



    def handle_pending_confirmation(
        self,
        msg: Message,
        lang: str,
    ) -> List[Action]:

        """
        Sprawdza, czy istnieje pending rezerwacja i obsługuje odpowiedź TAK/NIE.
        Zasada: tylko TAK -> wykonaj; wszystko inne -> anuluj (brak zgody)
        (Rozszerzone: obsługuje też pending marketing opt-in/opt-out)
        """
        text_raw = (msg.body or "").strip()
        text_lower = text_raw.lower()

        pending = self.conv.get(self._pending_key(msg.from_phone), "pending")
        if not pending:
            return None

        confirm_words = self._get_words_set(
            msg.tenant_id,
            "confirm_words",
            lang,
        )
        
        pending_kind = (pending.get("kind") or "").strip()

        # ---------------------------------------------------------------------
        # pending marketing consent change (opt-out / opt-in)
        # 
        # ---------------------------------------------------------------------
        if pending_kind in ("marketing_optout", "marketing_optin"):
        
            if text_lower in confirm_words:
                # Pobierz conv (potrzebne do ensure_crm_verification oraz crm_member_id)
                channel = msg.channel or "whatsapp"
                channel_user_id = msg.channel_user_id or msg.from_phone
                conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}

                # Wymuszenie weryfikacji konta (email code) – reuse istniejącego flow
                verify_resp = self.ensure_crm_verification(
                    msg,
                    conv,
                    lang,
                    post_intent=pending_kind,
                    post_slots={},
                )
                if verify_resp:
                    return verify_resp

                member_id = conv.get("crm_member_id") or pending.get("member_id")
                if not member_id:
                    # fail-safe: czyścimy pending i zwracamy błąd
                    self.conv.delete(self._pending_key(msg.from_phone), "pending")
                    body = self.tpl.render_named(msg.tenant_id, "system_marketing_change_failed", lang, {})
                    return [self._reply(msg, lang, body)]

                try:
                    if pending_kind == "marketing_optout":
                        self.crm.revoke_marketing_consent_for_member(
                            tenant_id=msg.tenant_id,
                            member_id=member_id,
                            reason="text_command_confirmed",
                        )
                        tpl_name = "system_marketing_optout_done"
                    else:
                        self.crm.grant_marketing_consent_for_member(
                            tenant_id=msg.tenant_id,
                            member_id=member_id,
                            reason="text_command_confirmed",
                        )
                        tpl_name = "system_marketing_optin_done"

                    self.conv.delete(self._pending_key(msg.from_phone), "pending")
                    body = self.tpl.render_named(msg.tenant_id, tpl_name, lang, {})
                    return [self._reply(msg, lang, body)]

                except NotImplementedError:
                    self.conv.delete(self._pending_key(msg.from_phone), "pending")
                    body = self.tpl.render_named(msg.tenant_id, "system_marketing_change_failed", lang, {})
                    return [self._reply(msg, lang, body)]

                except Exception:
                    self.conv.delete(self._pending_key(msg.from_phone), "pending")
                    body = self.tpl.render_named(msg.tenant_id, "system_marketing_change_failed", lang, {})
                    return [self._reply(msg, lang, body)]

            # każdy inny tekst niż TAK = brak zgody na zmianę -> anuluj
            self.conv.delete(self._pending_key(msg.from_phone), "pending")
            body = self.tpl.render_named(msg.tenant_id, "system_confirm_cancelled", lang, {})
            return [self._reply(msg, lang, body)]

        if text_lower in confirm_words:
            class_id = pending.get("class_id")
            member_id = pending.get("member_id")
            idem = pending.get("idempotency_key")
            class_name = pending.get("class_name") or class_id
            class_date = pending.get("class_date")
            class_time = pending.get("class_time")

            # Fallback: jeśli nadal nie mamy sensownych metadanych, spróbuj dociągnąć z CRM
            if (not class_date or not class_time) or (class_name == class_id):
                try:
                    details = self.crm.get_class_by_id(
                        tenant_id=msg.tenant_id,
                        class_id=class_id,
                    ) or {}
                except Exception:
                    details = {}

                if details:
                    start = str(
                        details.get("startDate") or details.get("startdate") or ""
                    )
                    if (not class_date) and len(start) >= 10:
                        class_date = start[:10]
                    if (not class_time) and len(start) >= 16:
                        class_time = start[11:16]

                    if class_name == class_id:
                        ct_raw = details.get("classType") or {}
                        if isinstance(ct_raw, dict):
                            ct_name = ct_raw.get("name")
                            if ct_name:
                                class_name = ct_name

            res = self.crm.reserve_class(
                tenant_id=msg.tenant_id,
                member_id=member_id,
                class_id=class_id,
                idempotency_key=idem,
                comments="booked on whatsapp",
            )


            self.conv.delete(self._pending_key(msg.from_phone), "pending")

            if (res or {}).get("ok", True):
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "reserve_class_confirmed",
                    lang,
                    {
                        "class_id": class_id,
                        "class_name": class_name,
                        "class_date": class_date,
                        "class_time": class_time,
                    },
                )
                return [self._reply(msg, lang, body)]
                
            mapped_error = (res or {}).get("mapped_error")
            pg_code = ((res or {}).get("pg_error") or {}).get("code")

            if mapped_error == "classes_already_booked" or pg_code == "ClassesAlreadyBooked":
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "reserve_class_already_booked",
                    lang,
                    {
                        "class_id": class_id,
                        "class_name": class_name,
                        "class_date": class_date,
                        "class_time": class_time,
                    },
                )
                return [self._reply(msg, lang, body)]

            body = self.tpl.render_named(
                msg.tenant_id,
                "reserve_class_failed",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        self.conv.delete(self._pending_key(msg.from_phone), "pending")
        body = self.tpl.render_named(
            msg.tenant_id,
            "reserve_class_declined",
            lang,
            {},
        )
        return [self._reply(msg, lang, body)]

    def handle_whatsapp_verification_code_linking(
        self,
        msg: Message,
        lang: str,
    ) -> List[Action]:
        """
        Obsługa wiadomości WhatsApp rozpoczynających się od "KOD:" –
        mapowanie kodu z WWW na rozmowę WhatsApp + przypięcie membera PG.
        """
        text = (msg.body or "").strip()
        text_upper = text.upper()

        if msg.channel != "whatsapp" or not text_upper.startswith("KOD:"):
            return None

        code = text_upper.replace("KOD:", "").strip()

        web_conv = self.conv.find_by_verification_code(
            tenant_id=msg.tenant_id,
            verification_code=code,
        )
        if not web_conv:
            body = self.tpl.render_named(
                msg.tenant_id,
                "www_not_verified",
                lang,
                {},
            )
            return [
                self._reply(
                    msg,
                    lang,
                    body,
                    channel="whatsapp",
                    channel_user_id=msg.from_phone,
                )
            ]

        member_id = None

        # member pobierany z PG
        resp = self.crm.get_member_by_phone(msg.tenant_id, msg.from_phone)
        items = (resp or {}).get("value") or []
        if items:
            member_id = str(items[0].get("id") or items[0].get("Id"))

        # fallback
        if not member_id and self.members_index:
            member = self.members_index.get_member(msg.tenant_id, msg.from_phone)
            if member:
                member_id = str(member.get("id") or member.get("member_id"))

        if not member_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "www_user_not_found",
                lang,
                {},
            )
            return [
                self._reply(
                    msg,
                    lang,
                    body,
                    channel="whatsapp",
                    channel_user_id=msg.from_phone,
                )
            ]

        member_id = member["id"]
        now_ts = int(time.time())
        ttl = now_ts + 30 * 60  # 30 minut weryfikacji dla WWW

        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=web_conv["channel"],
            channel_user_id=web_conv["channel_user_id"],
            crm_member_id=member_id,
            crm_verification_level="strong",
            crm_verified_until=ttl,
            verification_code=None,
            state_machine_status=STATE_AWAITING_MESSAGE,
        )

        body = self.tpl.render_named(
            msg.tenant_id,
            "www_verified",
            lang,
            {},
        )
        return [
            self._reply(
                msg,
                lang,
                body,
                channel="whatsapp",
                channel_user_id=msg.from_phone,
            )
        ]

    def _start_reservation_from_selection(
        self, msg: Message, lang: str, selected: dict
    ) -> List[Action]:
        """
        Użytkownik wybrał konkretną klasę z listy.
        Tutaj pilnujemy:
        - że mamy class_id,
        - że użytkownik jest zweryfikowany w PG (w razie potrzeby wywołujemy challenge),
        - że pending rezerwacja używa prawdziwego member_id z PG.
        """
        class_id = selected.get("class_id")
        if not class_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "reserve_class_missing_id",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}

        # 1) Weryfikacja PG – jeśli potrzeba, zainicjuje challenge
        verify_resp = self.ensure_crm_verification(
            msg,
            conv,
            lang,
            post_intent="reserve_class",
            post_slots={"class_id": class_id},
        )
        if verify_resp:
            # tutaj kończymy – challenge / WWW verification przejmie flow
            return verify_resp

        # 2) Po weryfikacji PG oczekujemy pg_member_id w rozmowie
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}
        member_id = conv.get("crm_member_id")
        if not member_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "crm_member_not_linked",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        class_meta = {
            "class_name": selected.get("name"),
            "class_date": selected.get("date"),
            "class_time": selected.get("time"),
        }

        return self.reserve_class_with_id_core(
            msg,
            lang,
            class_id=class_id,
            member_id=member_id,
            class_meta=class_meta,
        )


    def _verify_challenge_answer(
        self,
        tenant_id: str,
        phone: str,
        challenge_type: str,
        answer: str,
    ) -> bool:
        """
        Weryfikacja odpowiedzi na challenge PG.

        Docelowo logika powinna siedzieć w CRMService (odpytywanie PerfectGym
        / wewnętrznego indeksu członków). Tutaj delegujemy do metody
        crm.verify_member_challenge.

        Zwraca True/False.
        """
        answer = (answer or "").strip()
        if not answer:
            return False

        try:
            return bool(
                self.crm.verify_member_challenge(
                    tenant_id=tenant_id,
                    phone=phone,
                    challenge_type=challenge_type,
                    answer=answer,
                )
            )
        except Exception:
            # W razie błędu po stronie integracji traktujemy jako niepowodzenie.
            return False

    def verification_active(
        self, msg: Message, lang: str, member_id: str
    ) -> List[Action]:
        body = self.tpl.render_named(
                msg.tenant_id,
                "crm_verification_active",
                lang,
                {},
            )
        return [self._reply(msg, lang, body)]