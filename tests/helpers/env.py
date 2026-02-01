from __future__ import annotations

import os

import pytest


def getenv(name: str, default: str | None = None) -> str | None:
    """Small wrapper to keep env access consistent across tests."""

    return os.getenv(name, default)


def require_env(*names: str) -> dict[str, str]:
    """Return required env vars or skip the test if any are missing.

    This is intentionally test-friendly: nightly/prod canary jobs won't fail
    just because an environment wasn't wired yet.
    """

    missing = [n for n in names if not os.getenv(n)]
    if missing:
        pytest.skip(f"Missing required env vars: {', '.join(missing)}")
    return {n: os.environ[n] for n in names}
