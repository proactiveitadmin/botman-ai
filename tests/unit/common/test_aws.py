import types
import pytest

import src.common.aws as aws


class DummySQS:
    def __init__(self, url='http://local/queue'):
        self.url = url
        self.calls = []

    def get_queue_url(self, QueueName=None):
        self.calls.append(QueueName)
        return {'QueueUrl': self.url}


def test_resolve_queue_url_from_env(monkeypatch):
    monkeypatch.setenv('MY_QUEUE', 'http://aws/q')
    assert aws.resolve_queue_url('MY_QUEUE') == 'http://aws/q'


def test_resolve_queue_url_fallback_to_sqs(monkeypatch):
    monkeypatch.delenv('MY_QUEUE', raising=False)
    dummy = DummySQS(url='http://local/MY_QUEUE')
    monkeypatch.setattr(aws, 'sqs_client', lambda: dummy)
    assert aws.resolve_queue_url('MY_QUEUE') == 'http://local/MY_QUEUE'
    assert dummy.calls == ['MY_QUEUE']


def test_resolve_queue_url_missing_raises(monkeypatch):
    monkeypatch.delenv('NOPE', raising=False)
    monkeypatch.setattr(aws, 'sqs_client', lambda: (_ for _ in ()).throw(Exception('boom')))
    with pytest.raises(ValueError):
        aws.resolve_queue_url('NOPE')


def test_resolve_optional_queue_url(monkeypatch):
    monkeypatch.delenv('OPT', raising=False)
    monkeypatch.setattr(aws, 'sqs_client', lambda: (_ for _ in ()).throw(Exception('boom')))
    assert aws.resolve_optional_queue_url('OPT') is None


@pytest.mark.allow_custom_aws_endpoints
def test_endpoint_resolution_precedence(monkeypatch):
    per = "http://per-service"
    glob = "http://global"

    # Use real env contract from src/common/aws.py
    monkeypatch.setenv("SQS_ENDPOINT", per)
    monkeypatch.setenv("AWS_ENDPOINT_URL", glob)

    assert aws._endpoint_for("sqs") == per

    monkeypatch.delenv("SQS_ENDPOINT", raising=False)
    assert aws._endpoint_for("sqs") == glob

    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    assert aws._endpoint_for("sqs") is None