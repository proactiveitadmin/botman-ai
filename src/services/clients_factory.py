from __future__ import annotations

from typing import Any, Dict, Type, TypeVar

from ..adapters.jira_client import JiraClient
from ..adapters.perfectgym_client import PerfectGymClient
from ..adapters.twilio_client import TwilioClient
from ..adapters.whatsapp_cloud_client import WhatsAppCloudClient
from ..adapters.pinecone_client import PineconeClient
from ..common.logging import logger
from .tenant_config_service import TenantConfigService, default_tenant_config_service


T = TypeVar("T")


class ClientsFactory:
    """
    Creates per-tenant clients (Twilio/Jira/PerfectGym) based on TenantConfigService.
    Instances are cached per lambda runtime per tenant.
    """

    def __init__(self, tenant_cfg: TenantConfigService | None = None) -> None:
        self.tenant_cfg = tenant_cfg or default_tenant_config_service()
        self._twilio: dict[str, TwilioClient] = {}
        self._whatsapp_cloud: dict[str, WhatsAppCloudClient] = {}
        self._jira: dict[str, JiraClient] = {}
        self._pg: dict[str, PerfectGymClient] = {}
        self._pinecone: dict[str, PineconeClient] = {}
        self._whatsapp_sender: dict[str, Any] = {}

    def _feature_enabled(self, cfg: dict, flag_name: str) -> bool:
        f = (cfg or {}).get("features") or {}
        if not isinstance(f, dict):
            return True
        v = f.get(flag_name)
        # absent flag => enabled by default (demo-friendly)
        return bool(True if v is None else v)

    def _get_client(self, tenant_id: str, cache: Dict[str, T], client_cls: Type[T]) -> T:
        if tenant_id in cache:
            return cache[tenant_id]
        cfg = self.tenant_cfg.get(tenant_id)
        if cfg is None:
            raise ValueError(f"Missing tenant config for tenant_id={tenant_id}")
        client = client_cls.from_tenant_config(cfg)
        cache[tenant_id] = client
        return client

    def twilio(self, tenant_id: str) -> TwilioClient:
        return self._get_client(tenant_id, self._twilio, TwilioClient)


    def whatsapp_cloud(self, tenant_id: str) -> WhatsAppCloudClient:
        return self._get_client(tenant_id, self._whatsapp_cloud, WhatsAppCloudClient)


    def whatsapp(self, tenant_id: str):
        """Returns the configured WhatsApp sender for the tenant.

        Selection rules:
          1) if tenant cfg has whatsapp_provider == 'cloud' -> Cloud API
          2) if whatsapp_cloud is configured/enabled -> Cloud API
          3) fallback -> Twilio
        """
        cached = self._whatsapp_sender.get(tenant_id)
        if cached is not None:
            return cached

        cfg = self.tenant_cfg.get(tenant_id)
        provider = (cfg.get("whatsapp_provider") or cfg.get("provider") or "").strip().lower()

        cloud = self.whatsapp_cloud(tenant_id)
        sender = cloud if (provider == "cloud" or (provider == "" and cloud.enabled)) else self.twilio(tenant_id)

        self._whatsapp_sender[tenant_id] = sender
        return sender

    def jira(self, tenant_id: str) -> JiraClient:
        cfg = self.tenant_cfg.get(tenant_id)
        if not self._feature_enabled(cfg, "jira"):
            # No-op dev mode: JiraClient.create_ticket returns dev ticket when url is empty
            return JiraClient.from_tenant_config({"jira": {}})
        return self._get_client(tenant_id, self._jira, JiraClient)

    def perfectgym(self, tenant_id: str) -> PerfectGymClient:
        cfg = self.tenant_cfg.get(tenant_id)
        if not self._feature_enabled(cfg, "perfectgym"):
            return PerfectGymClient.from_tenant_config({"perfectgym": {}})
        return self._get_client(tenant_id, self._pg, PerfectGymClient)

    def pinecone(self, tenant_id: str) -> PineconeClient:
        cfg = self.tenant_cfg.get(tenant_id)
        if not self._feature_enabled(cfg, "kb_vector"):
            return PineconeClient.from_tenant_config({"pinecone": {}})
        return self._get_client(tenant_id, self._pinecone, PineconeClient)

