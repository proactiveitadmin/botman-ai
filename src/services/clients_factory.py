from __future__ import annotations

from typing import Any

from ..adapters.jira_client import JiraClient
from ..adapters.perfectgym_client import PerfectGymClient
from ..adapters.twilio_client import TwilioClient
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
        self._jira: dict[str, JiraClient] = {}
        self._pg: dict[str, PerfectGymClient] = {}

    def twilio(self, tenant_id: str) -> TwilioClient:
        if tenant_id in self._twilio:
            return self._twilio[tenant_id]
        cfg = self.tenant_cfg.get(tenant_id)
        client = TwilioClient.from_tenant_config(cfg)
        self._twilio[tenant_id] = client
        return client

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
