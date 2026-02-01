import os

import pytest

import src.common.aws as aws_mod


def test_resolve_queue_url_prefers_env(monkeypatch):
    monkeypatch.delenv("TEST_QUEUE", raising=False)
    monkeypatch.setenv("TEST_QUEUE", "https://sqs.example/123/test")
    # gdyby poszło do sqs_client, chcemy to zauważyć
    monkeypatch.setattr(aws_mod, "sqs_client", lambda: pytest.fail("sqs_client nie powinien być wołany"))

    url = aws_mod.resolve_queue_url("TEST_QUEUE")
    assert url == "https://sqs.example/123/test"


def test_resolve_queue_url_falls_back_to_sqs(monkeypatch):
    class DummySQS:
        def get_queue_url(self, QueueName):
            return {"QueueUrl": f"https://local/{QueueName}"}

    monkeypatch.delenv("DYNAMIC_QUEUE", raising=False)
    monkeypatch.setattr(aws_mod, "sqs_client", lambda: DummySQS())

    url = aws_mod.resolve_queue_url("DYNAMIC_QUEUE")
    assert url == "https://local/DYNAMIC_QUEUE"


def test_resolve_queue_url_raises_when_missing(monkeypatch):
    class DummySQS:
        def get_queue_url(self, QueueName):
            raise RuntimeError("no such queue")

    monkeypatch.delenv("MISSING_QUEUE", raising=False)
    monkeypatch.setattr(aws_mod, "sqs_client", lambda: DummySQS())

    with pytest.raises(ValueError):
        aws_mod.resolve_queue_url("MISSING_QUEUE")


def test_resolve_optional_queue_url(monkeypatch):
    # 1) env ustawione -> zwracamy
    monkeypatch.setenv("OPT_Q", "https://q1")
    assert aws_mod.resolve_optional_queue_url("OPT_Q") == "https://q1"

    # 2) brak env, sqs zwraca URL
    class DummySQS:
        def get_queue_url(self, QueueName):
            return {"QueueUrl": f"https://local/{QueueName}"}

    monkeypatch.delenv("OPT_Q2", raising=False)
    monkeypatch.setattr(aws_mod, "sqs_client", lambda: DummySQS())
    assert aws_mod.resolve_optional_queue_url("OPT_Q2") == "https://local/OPT_Q2"

    # 3) brak env, sqs rzuca -> None
    class DummySQSFail:
        def get_queue_url(self, QueueName):
            raise RuntimeError("no queue")

    monkeypatch.setattr(aws_mod, "sqs_client", lambda: DummySQSFail())
    assert aws_mod.resolve_optional_queue_url("OPT_Q3") is None


def test_s3_client_uses_endpoint_when_present(monkeypatch):
    """
    Autouse fixture w conftest nadpisuje _endpoint_for -> None,
    dlatego tutaj nadpisujemy je ponownie, żeby sprawdzić ścieżkę z endpoint_url.
    """
    calls = {}

    def fake_endpoint_for(service_name: str):
        if service_name == "s3":
            return "http://custom-s3"
        return None

    def fake_client(service_name, **kwargs):
        calls["service_name"] = service_name
        calls["kwargs"] = kwargs
        return "CLIENT"

    monkeypatch.setattr(aws_mod, "_endpoint_for", fake_endpoint_for, raising=False)
    monkeypatch.setattr(aws_mod, "boto3", type("B", (), {"client": staticmethod(fake_client)}))

    c = aws_mod.s3_client()
    assert c == "CLIENT"
    assert calls["service_name"] == "s3"
    assert calls["kwargs"]["endpoint_url"] == "http://custom-s3"


def test_ddb_resource_uses_endpoint_when_present(monkeypatch):
    calls = {}

    def fake_endpoint_for(service_name: str):
        if service_name == "dynamodb":
            return "http://ddb"
        return None

    def fake_resource(service_name, **kwargs):
        calls["service_name"] = service_name
        calls["kwargs"] = kwargs
        return "RES"

    monkeypatch.setattr(aws_mod, "_endpoint_for", fake_endpoint_for, raising=False)
    monkeypatch.setattr(aws_mod, "boto3", type("B", (), {"resource": staticmethod(fake_resource)}))

    r = aws_mod.ddb_resource()
    assert r == "RES"
    assert calls["service_name"] == "dynamodb"
    assert calls["kwargs"]["endpoint_url"] == "http://ddb"
