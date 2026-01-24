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
from ..common.timing import timed


SYSTEM_PROMPT = """
You are an intent classifier for a fitness club assistant.

Return exactly one valid JSON object with keys:
- "intent": one of [
    "reserve_class",
    "faq",
    "handover",
    "verification",
    "clarify",
    "ticket",
    "crm_available_classes",
    "crm_contract_status"
  ]
- "confidence": float 0..1
- "slots": object with extracted parameters.

INTENT DEFINITIONS:

1) "faq"
Use this intent for ALL informational or knowledge-based content that can be answered
from static FAQ / knowledge base, including but NOT limited to:

- club information:
  hours, price, pricing, location, address, contact, schedule, classes, trainers,
  membership, equipment, parking, rules, facilities, age_limit, guest_pass,
  lost_and_found, cancellation, opening_soon

- conversational / social FAQ:
  greetings (hello, hi, hey, salam),
  farewells (bye, goodbye, see you),
  thanks and acknowledgements (thanks, thank you, shukran),
  questions about the bot itself (who are you, what can you do, are you a bot),
  polite small talk (how are you, nice to meet you),
  language switching requests (can you speak English/Arabic/Polish)

If the user message can reasonably be answered using FAQ or predefined knowledge,
ALWAYS choose "faq".

2) "reserve_class"
User explicitly wants to sign up or reserve a class.
Extract class_id, class_name, date, time, member_id if present.

3) "crm_available_classes"
User asks what classes are currently available, today, tomorrow, this week, etc.

4) "crm_contract_status"
User asks about their membership, contract, subscription, payments, or account status.

5) "ticket"
User reports a problem, complaint, issue, or asks for staff support/help.

6) "handover"
User explicitly asks to speak with a human, staff member, or receptionist.

7) "verification"
User asks for account verification or verification code.

8) "clarify"
Use ONLY if the message is unclear, incomplete, or cannot be confidently mapped
to any intent above.

🔧 SPECIAL RULES (IMPORTANT):

- If the message is ONLY a number or short numeric selection
  (e.g. "1", "2", "nr 3", "option 1"),
  ALWAYS return:
    { "intent": "clarify", "confidence": 0.01, "slots": {} }
  This is NOT a class reservation.
  Numeric selections are handled by a state machine, not NLU.

- Prefer "faq" over "clarify" whenever possible.
  If in doubt between "faq" and "clarify", choose "faq".

- Always respond with ONE minimal JSON object and NOTHING else.
"""

_VALID_INTENTS = {
    "reserve_class", "faq", "handover", "verification", "clarify", "ticket",
    "crm_available_classes", "crm_contract_status", "crm_member_balance", "ack",
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
        # Ustawiamy twardy timeout na requesty do OpenAI, żeby uniknąć długich
        # zawieszeń (domyślnie httpx potrafi czekać bardzo długo).
        # Retry robimy sami w metodzie chat(); SDK retry wyłączamy.
        timeout_s = float(getattr(settings, "openai_timeout_s", 6) or 6)
        self._timeout_s = max(1.0, timeout_s)
        self.client = (
            OpenAI(api_key=self.api_key, timeout=self._timeout_s, max_retries=0)
            if self.enabled
            else None
        )

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

        with timed(
            "openai_chat_once",
            logger=logger, 
            component="openai_client",
            extra={"model": mdl, "max_tokens": max_tokens, "timeout_s": self._timeout_s},
        ):
            resp = self.client.chat.completions.create(
                model=mdl,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=max_tokens,
                timeout=self._timeout_s,
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
        with timed(
            "openai_chat_total",
            logger=logger, 
            component="openai_client",
            extra={"model": model or self.model, "max_tokens": max_tokens, "enabled": self.enabled},
        ):
            last_api_error: Optional[APIError] = None
            max_attempts = 2
            for attempt in range(max_attempts):
                try:
                    with timed(
                        "openai_chat_attempt",
                        logger=logger, 
                        component="openai_client",
                        extra={"attempt": attempt + 1, "max_attempts": max_attempts},
                    ):
                        return self._chat_once(messages, model=model, max_tokens=max_tokens)
                except RateLimitError:
                    sleep_s = min(0.5 * (2**attempt), 1.5) + random.uniform(0, 0.1)
                    with timed("openai_retry_sleep", logger=logger, component="openai_client", extra={"reason": "rate_limit", "sleep_s": round(sleep_s, 3)}):
                        time.sleep(sleep_s)
                except APIStatusError as e:
                    # 429/5xx -> retry, inne statusy -> nie ma sensu retry
                    status = getattr(e, "status_code", 0)
                    if status in (429, 500, 502, 503):
                        sleep_s = min(0.5 * (2**attempt), 1.5) + random.uniform(0, 0.1)
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
                    # problemy sieciowe — próbujemy jeszcze raz, ale nie czekamy długo
                    sleep_s = 0.3 + random.uniform(0, 0.1)
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

    # ---------------------------------------------------------------------
    # Embeddings (for KB / vector retrieval)
    # ---------------------------------------------------------------------
    def embed(
        self,
        texts: list[str],
        *,
        model: str,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Return embeddings for the given texts.

        In offline/dev mode (no API key) returns empty list to allow graceful fallback.
        """
        if not texts:
            return []
        if not self.enabled or not self.client:
            return []

        # OpenAI Embeddings API: returns a list aligned with inputs.
        kwargs = {"model": model, "input": texts}
        if dimensions:
            kwargs["dimensions"] = int(dimensions)

        with timed(
            "openai_embed",
            logger=logger, 
            component="openai_client",
            extra={"model": model, "n_texts": len(texts), "dims": dimensions or "default", "timeout_s": self._timeout_s},
        ):
            resp = self.client.embeddings.create(**kwargs)

        return [d.embedding for d in resp.data]
