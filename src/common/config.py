"""
Konfiguracja aplikacji oparta o zmienne środowiskowe.
Udostępnia dataclass Settings jako pojedyncze źródło prawdy.
"""

import os
import boto3
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
    
    #helper - ladowanie parametrow z ssm
    def ssm_param(env_key: str) -> str:
        """
        env_key: nazwa zmiennej środowiskowej, która trzyma nazwę parametru w SSM,
        np. env_key="PHONE_HASH_PEPPER", a ENV ma wartość "/botman/prod/phone_hash_pepper".
        """
        
        _ssm = boto3.client("ssm")
        name = os.getenv(env_key)
        if not name:
            raise RuntimeError(f"Missing env var: {env_key}")

        resp = _ssm.get_parameter(Name=name, WithDecryption=True)
        return resp["Parameter"]["Value"]
    
    # tryb deweloperski
    dev_mode: bool = os.getenv("DEV_MODE", "false").lower() == "true"
    tenant_default_lang: str = os.getenv("TENANT_DEFAULT_LANG", "pl")

    #hash keys
    if dev_mode:
        phone_hash_pepper = os.getenv("PHONE_HASH_PEPPER", "dev-phone")
        user_hash_pepper  = os.getenv("USER_HASH_PEPPER", "dev-user")
        otp_hash_pepper   = os.getenv("OTP_HASH_PEPPER", "dev-otp")
    else:
        phone_hash_pepper = ssm_param("PHONE_HASH_PEPPER")
        user_hash_pepper  = ssm_param("USER_HASH_PEPPER")
        otp_hash_pepper = ssm_param("OTP_HASH_PEPPER")

    #code sender email
    ses_from_email = os.getenv("SES_FROM_EMAIL")

    # Twilio
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_messaging_sid: str = os.getenv("TWILIO_MESSAGING_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_whatsapp_number: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "")

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
    # Data-plane host of the Pinecone index, e.g. "my-index-xxxxx.svc.eu-west1-gcp.pinecone.io"
    pinecone_index_host: str = os.getenv("PINECONE_INDEX_HOST", "")
    pinecone_namespace_prefix: str = os.getenv("PINECONE_NAMESPACE_PREFIX", "kb")
    pinecone_top_k: int = int(os.getenv("PINECONE_TOP_K", "6"))
    # Optional: force-disable vector retrieval (use legacy keyword retrieval)
    kb_vector_enabled: bool = os.getenv("KB_VECTOR_ENABLED", "1").lower() not in ("0", "false", "no")
 
    # PerfectGym
    pg_base_url: str = os.getenv("PG_BASE_URL", "")
    pg_client_id: str = os.getenv("PG_CLIENT_ID", "")
    pg_client_secret: str = os.getenv("PG_CLIENT_SECRET", "")
    pg_rate_limit_rps: float = float(os.getenv("PG_RATE_LIMIT_RPS", "30"))
    pg_rate_limit_burst: float = float(os.getenv("PG_RATE_LIMIT_BURST", "30"))
    pg_retry_max_attempts: int = int(os.getenv("PG_RETRY_MAX_ATTEMPTS", "3"))
    pg_retry_base_delay_s: float = float(os.getenv("PG_RETRY_BASE_DELAY_S", "0.2"))
    pg_retry_max_delay_s: float = float(os.getenv("PG_RETRY_MAX_DELAY_S", "2.0"))

    # Jira
    jira_url: str = os.getenv("JIRA_URL", "")
    jira_token: str = os.getenv("JIRA_TOKEN", "")
    jira_project_key: str = os.getenv("JIRA_PROJECT_KEY", "GI")
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
