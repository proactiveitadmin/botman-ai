from typing import List, Dict
from datetime import datetime, time
import os

from ..common.logging import logger


# Domyślne okno wysyłki – zgodnie z dokumentacją (9:00–20:00) :contentReference[oaicite:1]{index=1}
DEFAULT_SEND_FROM = os.getenv("CAMPAIGN_SEND_FROM", "09:00")
DEFAULT_SEND_TO = os.getenv("CAMPAIGN_SEND_TO", "20:00")


class CampaignService:
    def __init__(self, now_fn=None) -> None:
        self._now_fn = now_fn or datetime.utcnow

    def select_recipients(self, campaign: Dict) -> List[str]:
        """
        Zwraca listę numerów telefonu dla kampanii.

        Obsługiwane formaty:
          1) Proste: ["whatsapp:+48...", ...]
          2) Z tagami:
             [
               {"phone": "whatsapp:+48...", "tags": ["vip", "active"]},
               ...
             ]

        Filtry:
          - include_tags: jeżeli niepuste, bierzemy tylko odbiorców posiadających
            przynajmniej jeden z tagów
          - exclude_tags: jeżeli odbiorca ma którykolwiek z tych tagów, jest pomijany
        """
        raw_recipients = campaign.get("recipients", []) or []
        include_tags = set(campaign.get("include_tags") or [])
        exclude_tags = set(campaign.get("exclude_tags") or [])

        result: List[str] = []

        # tryb: brak filtrów -> zachowaj się jak dotychczas
        if not include_tags and not exclude_tags:
            for r in raw_recipients:
                if isinstance(r, dict):
                    phone = r.get("phone")
                else:
                    phone = r
                if phone:
                    result.append(phone)
            logger.info(
                {"campaign": "recipients",
                 "mode": "simple",
                 "count": len(result)}
            )
            return result

        # tryb z filtrami / tagami
        for r in raw_recipients:
            if isinstance(r, dict):
                phone = r.get("phone")
                tags = set(r.get("tags") or [])
            else:
                # brak struktury -> nie umiemy ocenić tagów,
                # więc traktujemy tags = empty set
                phone = r
                tags = set()

            if not phone:
                continue

            # include_tags: musi być przecięcie
            if include_tags and not (tags & include_tags):
                continue

            # exclude_tags: jeśli przecięcie niepuste -> skip
            if exclude_tags and (tags & exclude_tags):
                continue

            result.append(phone)

        logger.info(
            {
                "campaign": "recipients",
                "mode": "filtered",
                "count": len(result),
                "include_tags": list(include_tags),
                "exclude_tags": list(exclude_tags),
            }
        )
        return result


    @staticmethod
    def _parse_hhmm(value: str) -> time:
        """
        Parsuje 'HH:MM' do obiektu time.
        Jeżeli format jest niepoprawny – użyjemy bezpiecznego defaultu.
        """
        try:
            hh, mm = value.split(":")
            return time(hour=int(hh), minute=int(mm))
        except Exception:
            # Fallback: 9:00 lub 20:00 w razie błędu
            if value == DEFAULT_SEND_FROM:
                return time(9, 0)
            if value == DEFAULT_SEND_TO:
                return time(20, 0)
            return time(9, 0)

    def _resolve_window(self, campaign: Dict) -> tuple[time, time]:
        """
        Na razie używamy tylko globalnych envów.
        W przyszłości możesz dodać np. campaign["send_from"], campaign["send_to"].
        """
        send_from_str = campaign.get("send_from") or DEFAULT_SEND_FROM
        send_to_str = campaign.get("send_to") or DEFAULT_SEND_TO
        return self._parse_hhmm(send_from_str), self._parse_hhmm(send_to_str)

    def is_within_send_window(self, campaign: Dict) -> bool:
        """
        Sprawdza, czy aktualny czas (UTC) mieści się w oknie wysyłki.
        Wspiera także okna „przez północ” (np. 22:00–06:00).
        """
        now = self._now_fn().time()
        start, end = self._resolve_window(campaign)

        # Zwykłe okno, np. 09:00–20:00
        if start <= end:
            return start <= now <= end

        # Okno przez północ, np. 22:00–06:00
        return now >= start or now <= end
