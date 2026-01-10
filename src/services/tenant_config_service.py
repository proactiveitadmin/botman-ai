
from __future__ import annotations

import os
import time
from typing import Any, Dict

from ..common.aws import ssm_client
from ..common.logging import logger
from ..repos.tenants_repo import TenantsRepo


class TenantConfigService:
    """
    Loads tenant configuration from DynamoDB (Tenants table) and expands secrets
    from SSM Parameter Store (SecureString/plain) referenced by *_param fields.

    Caches:
      - tenant configs (expanded) for TTL seconds
      - SSM params per cold start (and across gets)
    """

    def __init__(self, repo: TenantsRepo | None = None, *, ttl_seconds: int | None = None) -> None:
        self.repo = repo or TenantsRepo()
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else int(os.getenv("TENANT_CONFIG_CACHE_TTL", "600"))

        # tenant_id -> (expires_at_epoch, expanded_cfg)
        self._cfg_cache: dict[str, tuple[float, dict]] = {}
        # param_name -> value
        self._ssm_cache: dict[str, str] = {}

    def _now(self) -> float:
        return time.time()

    def _get_ssm(self, param_name: str) -> str:
        if not param_name:
            return ""
        if param_name in self._ssm_cache:
            return self._ssm_cache[param_name]
        try:
            resp = ssm_client().get_parameter(Name=param_name, WithDecryption=True)
            val = (resp.get("Parameter") or {}).get("Value") or ""
            self._ssm_cache[param_name] = val
            return val
        except Exception as e:
            logger.error(
                {
                    "tenant_cfg": "ssm_get_parameter_failed", 
                    "param": param_name, "error": str(e)
                }
            )
            self._ssm_cache[param_name] = ""
            return ""

    def _expand_section(self, cfg: dict, section_name: str, mapping: dict[str, str]) -> None:
        """
        mapping: output_key -> input_param_key
        Example:
          mapping={"auth_token": "auth_token_param"}
        If cfg[section][param_key] exists, loads SSM and writes cfg[section][output_key].
        """
        section = cfg.get(section_name)
        if not isinstance(section, dict):
            return

        for out_key, param_key in mapping.items():
            param = (section.get(param_key) or "").strip()
            if param:
                section[out_key] = self._get_ssm(param)

    def get_raw(self, tenant_id: str) -> dict | None:
        return self.repo.get(tenant_id)

    def get(self, tenant_id: str) -> dict:
        if not tenant_id:
            raise ValueError("tenant_id required")

        # cache hit
        cached = self._cfg_cache.get(tenant_id)
        if cached:
            exp, cfg = cached
            if exp > self._now():
                return cfg

        item = self.repo.get(tenant_id) or {}
        if not item:
            raise ValueError(f"Tenant not found: {tenant_id}")

        # Make a shallow copy to avoid mutating the stored item dict
        cfg: dict[str, Any] = dict(item)

        # Expand secrets from SSM
        self._expand_section(cfg, "twilio", {
            "account_sid": "account_sid_param",
            "auth_token": "auth_token_param",
        })
        self._expand_section(cfg, "pg", {
            "client_id": "client_id_param",
            "client_secret": "client_secret_param",
        })
        self._expand_section(cfg, "jira", {
            "token": "token_param",
        })

        # store cache
        self._cfg_cache[tenant_id] = (self._now() + float(self.ttl_seconds), cfg)
        return cfg