"""
Konfiguracja aplikacji oparta o zmienne środowiskowe.
Udostępnia dataclass Settings jako pojedyncze źródło prawdy.
"""

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

    # Twilio
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_messaging_sid: str = os.getenv("TWILIO_MESSAGING_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_whatsapp_number: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "")

    # OpenAI / LLM
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # PerfectGym
    pg_base_url: str = os.getenv("PG_BASE_URL", "")
    pg_client_id: str = os.getenv("PG_CLIENT_ID", "")
    pg_client_secret: str = os.getenv("PG_CLIENT_SECRET", "")

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
