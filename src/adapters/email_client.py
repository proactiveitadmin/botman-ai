from __future__ import annotations

import os
from ..common.config import settings
from ..common.aws import ses_client
from ..common.logging import logger
from ..common.logging_utils import mask_email
from ..repos.tenants_repo import TenantsRepo

class EmailClient:
    """Minimalny klient email (SES) do wysyłki OTP."""

    def __init__(self, from_email: str | None = None, from_name: str | None = None) -> None:
        self._fallback_from_email = (from_email or settings.ses_from_email or os.getenv("SES_FROM_EMAIL", "").strip())
        self._fallback_from_name = (from_name or os.getenv("SES_FROM_NAME", "").strip() or None)
        self.tenants = TenantsRepo()

    def send_otp(
        self,
        *,
        tenant_id: str | None = None,
        to_email: str,
        subject: str,
        body_text: str,
        configuration_set: str | None = None,
    ) -> bool:
        """Wysyła email OTP.

        Zwraca True/False, żeby caller mógł nie ustawiać stanu challenge jeśli wysyłka się nie uda.
        """
        from_email = self._fallback_from_email
        from_name = self._fallback_from_name

        # Per-tenant override (jeśli jest skonfigurowane)
        if tenant_id:
            try:
                cfg = self.tenants.get_email_config(tenant_id)
            except Exception:
                cfg = None
            if cfg:
                from_email = (cfg.get("from_email") or from_email or "").strip() or from_email
                from_name = (cfg.get("from_name") or from_name or None)

        if not from_email:
            logger.error({"email": "missing_from_email", "tenant_id": tenant_id})
            return False

        try:
            source = f"{from_name} <{from_email}>" if from_name else from_email

            kwargs = {}
            if configuration_set:
                kwargs["ConfigurationSetName"] = configuration_set

            ses_client().send_email(
                Source=source,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
                },
                **kwargs,
            )
            logger.info({
                "email": "sent", 
                "to": mask_email(to_email)})
            return True
        except Exception as e:
            logger.error({
                "email": "send_failed", 
                "to": mask_email(to_email), 
                "tenant_id": tenant_id, 
                "error": str(e)})
            return False
