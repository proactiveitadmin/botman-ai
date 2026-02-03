"""A tiny Twilio REST API client that mimics the subset of the official SDK.

Why this exists:
- The full `twilio` package is intentionally not a hard dependency of this demo.
- Our code (and tests) use the *SDK-like* contract: `Client(...).messages.create(...)`.

This module provides that contract using plain HTTPS requests.

Supported kwargs for `messages.create`:
- to (str)
- body (str)
- from_ (str)              # optional
- messaging_service_sid (str)  # optional

Return value:
- An object with at least `.sid` attribute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..common.http_client import get_session


@dataclass
class _Message:
    sid: str | None = None
    raw: dict[str, Any] | None = None


class _MessagesResource:
    def __init__(self, *, account_sid: str, auth_token: str) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token

    def create(self, **kwargs: Any) -> _Message:
        """Create (send) a message via Twilio REST API.

        Raises:
            RuntimeError: on non-2xx responses or network errors.
        """
        to = kwargs.get("to")
        body = kwargs.get("body")
        from_ = kwargs.get("from_")
        messaging_service_sid = kwargs.get("messaging_service_sid")

        # Keep behaviour close to the SDK: invalid params -> raise.
        if not to or not body:
            raise RuntimeError("Missing required parameters: to/body")
        if not messaging_service_sid and not from_:
            raise RuntimeError("Missing required parameter: from_ or messaging_service_sid")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        data = {
            "To": to,
            "Body": body,
        }
        if messaging_service_sid:
            data["MessagingServiceSid"] = messaging_service_sid
        if from_:
            data["From"] = from_

        s = get_session()
        try:
            resp = s.post(url, data=data, auth=(self._account_sid, self._auth_token), timeout=12)
        except Exception as e:
            raise RuntimeError(f"Twilio HTTP request failed: {e}") from e

        # Twilio returns JSON. For errors it still returns JSON, but we don't rely on it.
        try:
            payload = resp.json() if resp.content else {}
        except Exception:
            payload = {"raw": resp.text}

        if not resp.ok:
            # Close to SDK behaviour: raise an exception.
            # Include http status and Twilio message if present.
            msg = payload.get("message") if isinstance(payload, dict) else None
            detail = msg or resp.text
            raise RuntimeError(f"Twilio API error {resp.status_code}: {detail}")

        sid = None
        if isinstance(payload, dict):
            sid = payload.get("sid")

        return _Message(sid=sid, raw=payload if isinstance(payload, dict) else {"raw": payload})


class Client:
    """SDK-like entrypoint: Client(account_sid, auth_token)."""

    def __init__(self, account_sid: str, auth_token: str) -> None:
        self.messages = _MessagesResource(account_sid=account_sid, auth_token=auth_token)
