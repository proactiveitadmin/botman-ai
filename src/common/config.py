"""src.common.config

Najważniejsze założenie dla Lambd: **żadnych zdalnych wywołań w czasie importu**.

Poprzednia wersja wykonywała odczyty z SSM (SecureString) podczas ładowania modułu,
co znacząco wydłużało cold start (szczególnie w message_router / outbound_sender).

W fazie demo ważniejsza jest responsywność niż pełna ochrona danych/historyczna
kompatybilność, dlatego konfiguracja jest teraz czysto oparta o ENV, a sekrety
z SSM są ładowane *leniwie* w miejscach, które ich realnie potrzebują (np.
src.common.security).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv, find_dotenv

# Ładujemy zmienne z .env (jeżeli plik istnieje).
load_dotenv(find_dotenv())


@dataclass
class Settings:
    """
    Zbiór ustawień konfiguracyjnych odczytywanych ze zmiennych środowiskowych.

    Pola są zgrupowane logicznie (Twilio, OpenAI, PerfectGym, Jira, KB, kolejki).
    """
    
    # tryb deweloperski
    dev_mode: bool = os.getenv("DEV_MODE", "false").lower() == "true"
    tenant_default_lang: str = os.getenv("TENANT_DEFAULT_LANG", "pl")

    # --- peppers (dla kompatybilności testów i security.py)
    # UWAGA: nie ładujemy z SSM podczas importu.
    # Jeśli w prod env zawiera ścieżkę "/param/...", security.py i tak może
    # zrobić lazy-load (jeśli to włączyliśmy), więc tu trzymamy tylko ENV.
    phone_hash_pepper: str = os.getenv("PHONE_HASH_PEPPER", "")
    user_hash_pepper: str = os.getenv("USER_HASH_PEPPER", "")
    otp_hash_pepper: str = os.getenv("OTP_HASH_PEPPER", "")

    openai_timeout_s: float = float(os.getenv("OPENAI_TIMEOUT_S", "6"))

    #code sender email
    ses_from_email = os.getenv("SES_FROM_EMAIL")

    # OpenAI / LLM
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # OpenAI embeddings
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_dimensions: int | None = (
        int(os.getenv("EMBEDDING_DIMENSIONS")) if os.getenv("EMBEDDING_DIMENSIONS", "").strip() else None
    )
    
    # Vector DB (Pinecone)
    pinecone_api_key: str = os.getenv("PINECONE_API_KEY", "")
    pinecone_namespace_prefix: str = os.getenv("PINECONE_NAMESPACE_PREFIX", "kb")
    pinecone_top_k: int = int(os.getenv("PINECONE_TOP_K", "6"))
    # Optional: force-disable vector retrieval (use legacy keyword retrieval)
    kb_vector_enabled: bool = os.getenv("KB_VECTOR_ENABLED", "1").lower() not in ("0", "false", "no")
 
    pg_rate_limit_rps: float = float(os.getenv("PG_RATE_LIMIT_RPS", "30"))
    pg_rate_limit_burst: float = float(os.getenv("PG_RATE_LIMIT_BURST", "30"))
    pg_retry_max_attempts: int = int(os.getenv("PG_RETRY_MAX_ATTEMPTS", "3"))
    pg_retry_base_delay_s: float = float(os.getenv("PG_RETRY_BASE_DELAY_S", "0.2"))
    pg_retry_max_delay_s: float = float(os.getenv("PG_RETRY_MAX_DELAY_S", "2.0"))

    jira_default_issue_type: str = "Task"

    # KB (FAQ z S3)
    kb_bucket: str = os.getenv("KB_BUCKET", "")

    # Kolejki (opcjonalnie, żeby mieć 1 źródło prawdy)
    inbound_queue_url: str = os.getenv("InboundEventsQueueUrl", "")
    outbound_queue_url: str = os.getenv("OutboundQueueUrl", "")
    
    # np. w common/config.py
    def get_default_language(self) -> str:
        return self.tenant_default_lang or "en"



# Globalna instancja ustawień używana w całej aplikacji.
settings = Settings()
