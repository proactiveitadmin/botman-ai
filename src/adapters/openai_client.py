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
from ..common.logging import logger

SYSTEM_PROMPT = """
You are an intent classifier for a fitness club. 
Return exactly one valid json object with keys:
- "intent": one of ["reserve_class", "faq", "handover", "clarify", "ticket", "crm_available_classes", "crm_contract_status", "greeting"]
- "confidence": float 0..1
- "slots": object with extracted parameters.

Intent rules:
- "greeting": message is only a greeting/polite phrase in any language and contains no request.
- "faq": user asks for general information on topics [hours price location contact schedule classes trainers membership equipment parking rules facilities age_limit guest_pass lost_and_found cancellation opening_soon].
- "reserve_class": user wants to sign up/reserve a class (extract class_id, member_id if present).
- "crm_available_classes": user asks what classes are available.
- "crm_contract_status": user asks about membership/contract/account status.
- "ticket": user reports a problem or asks for staff help.
- "handover": user explicitly wants to speak to a human.

🔧 SPECIAL RULES:
- If the message is only a number or short numeric selection (e.g. "1", "2", "nr 3", "option 1"), 
  treat it as: 
    { "intent": "clarify", "confidence": 0.01, "slots": {} }
  This is NOT a class reservation request. Selections are processed by state machine, not NLU.

- If the message is unclear or does not fit any other intent → "clarify".

Always respond with one minimal json object and nothing else.
"""




_VALID_INTENTS = {
    "reserve_class", "faq", "handover", "clarify", "ticket",
    "crm_available_classes", "crm_contract_status", "greeting",
}



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
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                return self._chat_once(messages, model=model, max_tokens=max_tokens)
            except RateLimitError:
                time.sleep(min(2**attempt, 8) + random.uniform(0, 0.3))
            except APIStatusError as e:
                # 429/5xx -> retry, inne statusy -> nie ma sensu retry
                status = getattr(e, "status_code", 0)
                if status in (429, 500, 502, 503):
                    sleep_s = min(2**attempt, 8) + random.uniform(0, 0.3)
                    logger.warning(
                        {
                            "component": "openai_client",
                            "event": "retry_sleep",
                            "reason": "api_status",
                            "status_code": status,
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "sleep_s": round(sleep_s, 3),
                        }
                    )
                    time.sleep(sleep_s)
                else:
                    last_api_error = e
                    logger.error(
                        {
                            "component": "openai_client",
                            "event": "non_retryable_status",
                            "status_code": status,
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                        }
                    )
                    break
            except APIConnectionError:
                # problemy sieciowe — próbujemy jeszcze raz
                sleep_s = 1.0 + random.uniform(0, 0.3)
                logger.warning(
                    {
                        "component": "openai_client",
                        "event": "retry_sleep",
                        "reason": "connection_error",
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "sleep_s": round(sleep_s, 3),
                    }
                )
                time.sleep(sleep_s)
            except APIError as e:
                # „logiczny” błąd API — raczej nie ustąpi po retry
                last_api_error = e
                logger.error(
                    {
                        "component": "openai_client",
                        "event": "api_error",
                        "error_type": type(e).__name__,
                        "message": str(e),
                    }
                )
                break
        
        # ostateczny fallback (json, żeby parser po drugiej stronie nie padł)
        logger.error(
            {
                "component": "openai_client",
                "event": "chat_failed_after_retries",
                "max_attempts": max_attempts,
                "had_last_api_error": bool(last_api_error),
            }
        )
        note = "LLM unavailable (retries exhausted)"
        if last_api_error is not None:
            note = f"LLM error: {type(last_api_error).__name__}: {last_api_error}"

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
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"LANG={lang}\nTEXT={text}\n\n"
                    "Respond strictly in json according to the specification above."
                ),
            },
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
