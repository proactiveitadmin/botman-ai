import time
import re
from typing import Literal, Optional

from ..repos.conversations_repo import ConversationsRepo


OptAction = Literal["optout", "optin"]


class OptOutService:
    """Central place for opt-out / opt-in flow.

    Storage is per (tenant, channel, channel_user_id) inside Conversations table:
      - opt_out: bool
      - opt_out_at: unix ts (audit)
      - opt_out_source: str (text_command / web_link / api / unknown)
    """

    # Most common keywords (PL/EN) + WhatsApp conventions
    _OPTOUT_RE = re.compile(
        r"^(stop|unsubscribe|opt[-_ ]?out|wypisz|rezygnuj|nie\s*chc[eę]|zablokuj)$",
        re.IGNORECASE,
    )
    _OPTIN_RE = re.compile(
        r"^(start|subscribe|opt[-_ ]?in|wzn[oó]w|odblokuj|zgadzam\s*si[eę])$",
        re.IGNORECASE,
    )

    def __init__(self, repo: ConversationsRepo | None = None) -> None:
        self.repo = repo or ConversationsRepo()

    def parse_command(self, text: str | None) -> Optional[OptAction]:
        t = (text or "").strip()
        if not t:
            return None
        # allow emojis / punctuation around
        t = re.sub(r"[\s\.!?,;:]+", " ", t).strip()
        if self._OPTOUT_RE.match(t):
            return "optout"
        if self._OPTIN_RE.match(t):
            return "optin"
        return None

    def set_opt_out(
        self,
        *,
        tenant_id: str,
        channel: str,
        channel_user_id: str,
        opt_out: bool,
        source: str = "unknown",
        ts: int | None = None,
    ) -> None:
        now_ts = int(ts or time.time())
        self.repo.upsert_conversation(
            tenant_id=tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            opt_out=bool(opt_out),
            opt_out_at=now_ts,
            opt_out_source=source,
        )

    def set_opt_out_by_uid(
        self,
        *,
        tenant_id: str,
        channel: str,
        uid: str,
        opt_out: bool,
        source: str = "unknown",
        ts: int | None = None,
    ) -> None:
        now_ts = int(ts or time.time())
        self.repo.upsert_conversation_by_uid(
            tenant_id=tenant_id,
            channel=channel,
            uid=uid,
            opt_out=bool(opt_out),
            opt_out_at=now_ts,
            opt_out_source=source,
        )

    def is_opted_out(self, tenant_id: str, channel: str, channel_user_id: str) -> bool:
        conv = self.repo.get_conversation(tenant_id, channel, channel_user_id) or {}
        return bool(conv.get("opt_out") is True)