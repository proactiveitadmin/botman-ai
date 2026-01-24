from __future__ import annotations

from typing import Any

from ..adapters.jira_client import JiraClient
from ..adapters.perfectgym_client import PerfectGymClient
from ..adapters.twilio_client import TwilioClient
from ..adapters.whatsapp_cloud_client import WhatsAppCloudClient
from ..adapters.pinecone_client import PineconeClient
from ..common.logging import logger
from .tenant_config_service import TenantConfigService


class ClientsFactory:
    """
    Creates per-tenant clients (Twilio/Jira/PerfectGym) based on TenantConfigService.
    Instances are cached per lambda runtime per tenant.
    """

    def __init__(self, tenant_cfg: TenantConfigService | None = None) -> None:
        self.tenant_cfg = tenant_cfg or TenantConfigService()
        self._twilio: dict[str, TwilioClient] = {}
        self._whatsapp_cloud: dict[str, WhatsAppCloudClient] = {}
        self._jira: dict[str, JiraClient] = {}
        self._pg: dict[str, PerfectGymClient] = {}
        self._pinecone: dict[str, PineconeClient] = {}

    def twilio(self, tenant_id: str) -> TwilioClient:
        if tenant_id in self._twilio:
            return self._twilio[tenant_id]
        cfg = self.tenant_cfg.get(tenant_id)
        client = TwilioClient.from_tenant_config(cfg)
        self._twilio[tenant_id] = client
        return client


    def whatsapp_cloud(self, tenant_id: str) -> WhatsAppCloudClient:
        if tenant_id in self._whatsapp_cloud:
            return self._whatsapp_cloud[tenant_id]
        cfg = self.tenant_cfg.get(tenant_id)
        client = WhatsAppCloudClient.from_tenant_config(cfg)
        self._whatsapp_cloud[tenant_id] = client
        return client

    def whatsapp(self, tenant_id: str):
        """Returns the configured WhatsApp sender for the tenant.

        Selection rules:
          1) if tenant cfg has whatsapp_provider == 'cloud' -> Cloud API
          2) if whatsapp_cloud is configured/enabled -> Cloud API
          3) fallback -> Twilio
        """
        cfg = self.tenant_cfg.get(tenant_id)
        provider = (cfg.get("whatsapp_provider") or cfg.get("provider") or "").strip().lower()
        cloud = self.whatsapp_cloud(tenant_id)
        if provider == "cloud" or (provider == "" and cloud.enabled):
            return cloud
        return self.twilio(tenant_id)

    def jira(self, tenant_id: str) -> JiraClient:
        if tenant_id in self._jira:
            return self._jira[tenant_id]
        cfg = self.tenant_cfg.get(tenant_id)
        client = JiraClient.from_tenant_config(cfg)
        self._jira[tenant_id] = client
        return client

    def perfectgym(self, tenant_id: str) -> PerfectGymClient:
        if tenant_id in self._pg:
            return self._pg[tenant_id]
        cfg = self.tenant_cfg.get(tenant_id)
        client = PerfectGymClient.from_tenant_config(cfg)
        self._pg[tenant_id] = client
        return client

    def pinecone(self, tenant_id: str) -> PineconeClient:
        if tenant_id in self._pinecone:
            return self._pinecone[tenant_id]
        cfg = self.tenant_cfg.get(tenant_id)
        client = PineconeClient.from_tenant_config(cfg)
        self._pinecone[tenant_id] = client
        return client
