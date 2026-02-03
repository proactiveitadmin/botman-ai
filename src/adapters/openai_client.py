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
Classify the user message and extract intent + slots.

Return ONLY JSON:
{"intent": "...", "confidence": 0..1, "slots": {...}}

Intents:
- reserve_class
- crm_available_classes
- crm_contract_status
- crm_member_balance
- verification
- ticket
- handover
- ack
- faq
- clarify
- ticket_status
- marketing_optout
- marketing_optin

FAQ KEY POLICY (IMPORTANT):
- slots.faq_key is OPTIONAL. Use it ONLY when the message unambiguously maps to exactly ONE FAQ key.
- Do NOT guess. If there is any ambiguity between multiple keys, omit slots.faq_key.
- If the user asks a general question that could match multiple FAQ entries (e.g., "hours" without specifying what),
  omit slots.faq_key.
- If the user mentions a specific entity (e.g., "sauna", "pool", "locker room", "kids zone"), prefer the matching key ONLY
  if that entity is explicitly present in the user's text.
- Do NOT map between similar categories (e.g., sauna vs pool) unless the user's text explicitly contains the target entity.
- If unsure, return intent="faq" and leave slots empty.

Rules:
- If message is only a number -> intent=clarify (confidence 0.01)
- Prefer faq over clarify
- Messages describing urgent problems, lost items, access to personal belongings,
  safety issues, or situations requiring immediate human assistance
  MUST be classified as intent "ticket".
  
Conversational shortcuts:
- Single-token or very short greetings, farewells, and politeness expressions
  (e.g. greetings, goodbyes, thanks, acknowledgements) are HIGH confidence.
- For such messages, set confidence >= 0.9.
- These messages are NOT ambiguous and should not be classified as clarify.

If the message is a greeting or farewell:
- Use intent "faq".
- These messages are HIGH confidence (>= 0.9).

If the message is a short acknowledgement or politeness response
(e.g. confirming, thanking, or reacting to a previous message):
- Use intent "ack".
- These messages are HIGH confidence (>= 0.9).
"""

_VALID_INTENTS = {
    "reserve_class", "faq", "handover", "verification", "clarify", "ticket",
    "crm_available_classes", "crm_contract_status", "crm_member_balance", "ack",
    "ticket_status", "marketing_optout", "marketing_optin",
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

        # In-memory embedding cache (per warm Lambda runtime).
        # Keyed by (model, dimensions, normalized_text).
        import os
        self._embed_cache_ttl_s = float(os.getenv("OPENAI_EMBED_CACHE_TTL", "300") or 300)
        self._embed_cache_max = int(os.getenv("OPENAI_EMBED_CACHE_MAX", "2000") or 2000)
        self._embed_cache: dict[tuple[str, int | None, str], tuple[float, list[float]]] = {}

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
        # prompt_size: cheap, token-agnostic approximation (chars).
        try:
            prompt_chars = sum(len(str(m.get("content") or "")) for m in (messages or []))
            prompt_msgs = len(messages or [])
        except Exception:
            prompt_chars = None
            prompt_msgs = None

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
        with timed(
            "prompt_build",
            logger=logger,
            component="openai_client",
            extra={"prompt": "intent_classification", "lang": lang},
        ):
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

        prompt_size = sum(len(m.get("content") or "") for m in messages)
        logger.warning(
            {
                "component": "openai_client",
                "event": "prompt_size",
                "prompt": "intent_classification",
                "size_chars": prompt_size,
                "messages": len(messages),
            }
        )

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

        # Small in-memory TTL cache to avoid repeated embedding calls for identical
        # questions within warm Lambdas.
        import time
        now = time.time()
        norm_texts = [(t or "").strip() for t in texts]

        cached_vecs: list[list[float] | None] = [None] * len(norm_texts)
        missing: list[str] = []
        missing_idx: list[int] = []

        for i, t in enumerate(norm_texts):
            key = (model, int(dimensions) if dimensions else None, t)
            item = self._embed_cache.get(key)
            if item:
                exp, vec = item
                if exp > now and vec:
                    cached_vecs[i] = vec
                    continue
                # expired
                try:
                    del self._embed_cache[key]
                except Exception:
                    pass
            missing.append(t)
            missing_idx.append(i)

        # If everything is cached, return fast.
        if not missing:
            return [v or [] for v in cached_vecs]

        # OpenAI Embeddings API: returns a list aligned with inputs.
        kwargs = {"model": model, "input": missing}
        if dimensions:
            kwargs["dimensions"] = int(dimensions)

        with timed(
            "openai_embed",
            logger=logger, 
            component="openai_client",
            extra={"model": model, "n_texts": len(missing), "dims": dimensions or "default", "timeout_s": self._timeout_s},
        ):
            resp = self.client.embeddings.create(**kwargs)

        new_vecs = [d.embedding for d in resp.data]
        # merge results back into full list
        for j, vec in enumerate(new_vecs):
            i = missing_idx[j]
            cached_vecs[i] = vec
            key = (model, int(dimensions) if dimensions else None, missing[j])
            # simple eviction: if over max, clear (cheap + safe)
            if len(self._embed_cache) >= self._embed_cache_max:
                self._embed_cache.clear()
            self._embed_cache[key] = (now + self._embed_cache_ttl_s, vec)

        return [v or [] for v in cached_vecs]
