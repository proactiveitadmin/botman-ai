from typing import List, Dict
from datetime import datetime, time
import os

from ..common.logging import logger


# Domyślne okno wysyłki – zgodnie z dokumentacją (9:00–20:00) :contentReference[oaicite:1]{index=1}
DEFAULT_SEND_FROM = os.getenv("CAMPAIGN_SEND_FROM", "09:00")
DEFAULT_SEND_TO = os.getenv("CAMPAIGN_SEND_TO", "20:00")


class CampaignService:
    def __init__(self, now_fn=None) -> None:
        """
        now_fn – do testów możemy wstrzyknąć własną funkcję zwracającą datetime.
        Domyślnie używamy UTC (Lambda).
        """
        self._now_fn = now_fn or datetime.utcnow

    def select_recipients(self, campaign: Dict) -> List[str]:
        recipients = campaign.get("recipients", [])
        logger.info({"campaign": "recipients", "count": len(recipients)})
        return recipients

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
