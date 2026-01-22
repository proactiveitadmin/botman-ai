from __future__ import annotations
import re
from ..adapters.openai_client import OpenAIClient

_RE_ONLY_EMOJI_OR_PUNCT = re.compile(r"^[^\w\d]{1,12}$", re.UNICODE)


class NLUService:
    def __init__(self):
        self.client = OpenAIClient()

    def _fast_classify(self, text: str) -> dict | None:
        t = (text or "").strip()
        if not t:
            return {"intent": "clarify", "confidence": 0.4, "slots": {"reason": "empty"}}

        # Emoji / interpunkcja typu "👍" "🙂" "!" – traktujemy jak szybkie potwierdzenie.
        if _RE_ONLY_EMOJI_OR_PUNCT.match(t):
            return {"intent": "ack", "confidence": 0.9, "slots": {}}

        return None

    def classify_intent(self, text: str, lang: str):
        fast = self._fast_classify(text)
        if fast is not None:
            return fast
        return self.client.classify(text, lang)