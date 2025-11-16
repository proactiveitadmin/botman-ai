"""
Adapter do OpenAI Chat Completions używany jako NLU.

Udostępnia metody:
- chat / chat_async: surowe wywołanie modelu z mechanizmem retry,
- classify / classify_async: wygodny wrapper do klasyfikacji intencji.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
import json
import time
import random
import asyncio

from openai import OpenAI
from openai import APIError, APIConnectionError, APIStatusError, RateLimitError

from ..common.config import settings

SYSTEM_PROMPT = """Jesteś klasyfikatorem intencji dla siłowni/fitness klubu.
Zwracaj JSON o kluczach: intent (reserve_class|faq|handover|clarify|ticket), confidence (0..1), slots (dict).
faq slots: {"topic": one of [hours, price, location, contact]}
reserve_class slots: {"class_id": optional, "member_id": optional}
"""

_VALID_INTENTS = {"reserve_class", "faq", "handover", "clarify", "ticket"}


class OpenAIClient:
    """
    Klient OpenAI używany przez warstwę NLU.

    Dba o poprawną konfigurację, retry oraz zwracanie bezpiecznych fallbacków,
    gdy API jest niedostępne lub źle skonfigurowane.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        """
        Inicjalizuje klienta na podstawie przekazanego API key lub globalnych ustawień.

        Args:
            api_key: opcjonalny klucz do OpenAI; jeżeli brak, używa settings.openai_api_key
            model: nazwa modelu, np. "gpt-4o-mini"; jeżeli brak, używa settings.llm_model
        """
        self.api_key = api_key or getattr(settings, "openai_api_key", None)
        self.enabled = bool(self.api_key)
        self.model = model or getattr(settings, "llm_model", "gpt-4o-mini")
        self.client = OpenAI(api_key=self.api_key) if self.enabled else None

    def _chat_once(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = 256,
    ) -> str:
        """
        Jednokrotne (bez retry) wywołanie Chat Completions.

        W trybie bez API key (dev/offline) zwraca prosty, bezpieczny JSON,
        który informuje dalszą logikę, że trzeba dopytać użytkownika.
        """
        if not self.enabled or not self.client:
            # tryb „bez AI” — bezpieczny fallback
            user_msg = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"),
                "",
            )
            return json.dumps(
                {
                    "intent": "clarify",
                    "confidence": 0.49,
                    "slots": {"echo": user_msg[:80]},
                }
            )

        mdl = model or self.model
        resp = self.client.chat.completions.create(
            model=mdl,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or "{}"

    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = 256,
    ) -> str:
        """
        Wywołanie modelu z mechanizmem retry i bezpiecznym fallbackiem.

        Retry dotyczy:
          - RateLimitError,
          - APIStatusError dla 429/5xx,
          - APIConnectionError (problemy sieciowe).

        Błędy konfiguracyjne (np. brak uprawnień, zły model) nie są retryowane,
        tylko powodują szybki powrót z fallbackiem.
        """
        last_api_error: Optional[APIError] = None

        for attempt in range(5):
            try:
                return self._chat_once(messages, model=model, max_tokens=max_tokens)
            except RateLimitError:
                time.sleep(min(2**attempt, 8) + random.uniform(0, 0.3))
            except APIStatusError as e:
                # 429/5xx -> retry, inne statusy -> nie ma sensu retry
                status = getattr(e, "status_code", 0)
                if status in (429, 500, 502, 503):
                    time.sleep(min(2**attempt, 8) + random.uniform(0, 0.3))
                else:
                    last_api_error = e
                    break
            except APIConnectionError:
                # problemy sieciowe — próbujemy jeszcze raz
                time.sleep(1.0 + random.uniform(0, 0.3))
            except APIError as e:
                # „logiczny” błąd API — raczej nie ustąpi po retry
                last_api_error = e
                break

        # ostateczny fallback (json, żeby parser po drugiej stronie nie padł)
        note = "LLM unavailable (retries exhausted)"
        if last_api_error is not None:
            note = f"LLM error: {type(last_api_error).__name__}"

        return json.dumps(
            {
                "intent": "clarify",
                "confidence": 0.3,
                "slots": {"note": note},
            }
        )

    async def chat_async(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = 256,
    ) -> str:
        """
        Asynchroniczna wersja chat, wykonująca wywołanie w wątku roboczym,
        aby nie blokować event loopa.
        """
        return await asyncio.to_thread(self.chat, messages, model, max_tokens)

    def classify(self, text: str, lang: str = "pl") -> Dict[str, Any]:
        """
        Wygodny wrapper do klasyfikacji intencji.

        Buduje prompt system/user, wywołuje LLM i normalizuje wynik do postaci:
        {"intent": ..., "confidence": ..., "slots": {...}}.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"LANG={lang}\nTEXT={text}"},
        ]
        content = self.chat(messages, model=self.model, max_tokens=256)
        return self._parse_classification(content)

    async def classify_async(self, text: str, lang: str = "pl") -> Dict[str, Any]:
        """
        Asynchroniczna wersja classify, przydatna w potencjalnie asynchronicznych workerach.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"LANG={lang}\nTEXT={text}"},
        ]
        content = await self.chat_async(messages, model=self.model, max_tokens=256)
        return self._parse_classification(content)

    def _parse_classification(self, content: str) -> Dict[str, Any]:
        """
        Normalizuje odpowiedź modelu do słownika o polach:
        - intent: jedna z wartości _VALID_INTENTS (lub 'clarify' w razie błędu),
        - confidence: float 0..1,
        - slots: słownik z dodatkowymi informacjami.
        """
        try:
            data = json.loads(content or "{}")
        except Exception:
            return {"intent": "clarify", "confidence": 0.3, "slots": {}}

        intent = str(data.get("intent", "clarify")).strip()
        if intent not in _VALID_INTENTS:
            intent = "clarify"

        # confidence -> float 0..1
        try:
            conf = float(data.get("confidence", 0.5))
        except Exception:
            conf = 0.5
        conf = max(0.0, min(1.0, conf))

        slots = data.get("slots") or {}
        if not isinstance(slots, dict):
            slots = {}

        return {"intent": intent, "confidence": conf, "slots": slots}
