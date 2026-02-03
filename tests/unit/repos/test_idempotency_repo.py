import os
from botocore.exceptions import ClientError

import pytest

import src.repos.idempotency_repo as ir


class FakeTable:
    def __init__(self):
        self.put_calls = []
        self.raise_error = None

    def put_item(self, **kwargs):
        self.put_calls.append(kwargs)
        if self.raise_error:
            raise self.raise_error
        return {}


class FakeDdb:
    def __init__(self, table):
        self._t = table

    def Table(self, name):
        return self._t


def _client_error(code: str):
    return ClientError(
        {"Error": {"Code": code, "Message": "x"}, "ResponseMetadata": {"HTTPStatusCode": 400}},
        "PutItem",
    )


def test_try_acquire_dev_mode_in_memory(monkeypatch):
    t = FakeTable()
    monkeypatch.setattr(ir, "ddb_resource", lambda: FakeDdb(t))
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setattr(ir.settings, "dev_mode", True)

    repo = ir.IdempotencyRepo(table_name_env="")
    assert repo.try_acquire("k1") is True
    assert repo.try_acquire("k1") is False


def test_try_acquire_ddb_conditional_fail_returns_false(monkeypatch):
    t = FakeTable()
    t.raise_error = _client_error("ConditionalCheckFailedException")
    monkeypatch.setattr(ir, "ddb_resource", lambda: FakeDdb(t))

    # force non-dev path
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setattr(ir.settings, "dev_mode", False)

    repo = ir.IdempotencyRepo(table_name_env="")
    assert repo.try_acquire("k2") is False


def test_try_acquire_ddb_other_error_raises(monkeypatch):
    t = FakeTable()
    t.raise_error = _client_error("ThrottlingException")
    monkeypatch.setattr(ir, "ddb_resource", lambda: FakeDdb(t))

    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setattr(ir.settings, "dev_mode", False)

    repo = ir.IdempotencyRepo(table_name_env="")
    with pytest.raises(ClientError):
        repo.try_acquire("k3")