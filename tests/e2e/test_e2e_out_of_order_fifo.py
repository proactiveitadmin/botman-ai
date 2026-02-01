import json
import types

import pytest

from src.lambdas.message_router import handler as h


class DummyIdempotency:
    def try_acquire(self, key, meta=None):
        return True


class DummyTable:
    def __init__(self):
        self.items = []

    def get_item(self, **kwargs):
        return {}

    def put_item(self, **kwargs):
        self.items.append(kwargs)


class DummyMessagesRepo:
    def __init__(self):
        self.table = DummyTable()


class DummyRouter:
    def __init__(self):
        self.calls = []
        self.crm = types.SimpleNamespace(reset_invocation_limits=lambda: None)

    def handle(self, msg):
        # record order of processing
        self.calls.append(msg.body)
        return []


def _record(message_id, body, group_id, seq, dedup_id):
    return {
        "messageId": message_id,
        "body": json.dumps(body),
        "attributes": {
            "MessageGroupId": group_id,
            "SequenceNumber": str(seq),
            "MessageDeduplicationId": dedup_id,
        },
    }


def test_message_router_sorts_records_by_fifo_sequence_number(monkeypatch):
    dummy_router = DummyRouter()
    monkeypatch.setattr(h, "ROUTER", dummy_router)
    monkeypatch.setattr(h, "IDEMPOTENCY", DummyIdempotency())
    monkeypatch.setattr(h, "MESSAGES", DummyMessagesRepo())

    # avoid publishing actions
    monkeypatch.setattr(h, "_publish_actions", lambda actions, original_body: None)

    conv = "conv#whatsapp#abc"
    r1 = _record(
        "m1",
        {"event_id": "evt-1", "conversation_id": conv, "tenant_id": "t1", "channel": "whatsapp", "body": "first"},
        group_id=conv,
        seq=1,
        dedup_id="evt-1",
    )
    r2 = _record(
        "m2",
        {"event_id": "evt-2", "conversation_id": conv, "tenant_id": "t1", "channel": "whatsapp","body": "second"},
        group_id=conv,
        seq=2,
        dedup_id="evt-2",
    )

    # out-of-order delivery in batch: r2 before r1
    event = {"Records": [r2, r1]}
    res = h.lambda_handler(event, context=None)

    assert res.get("statusCode") == 200
    assert dummy_router.calls == ["first", "second"]


def test_message_router_rejects_group_id_mismatch(monkeypatch):
    dummy_router = DummyRouter()
    monkeypatch.setattr(h, "ROUTER", dummy_router)
    monkeypatch.setattr(h, "IDEMPOTENCY", DummyIdempotency())
    monkeypatch.setattr(h, "MESSAGES", DummyMessagesRepo())
    monkeypatch.setattr(h, "_publish_actions", lambda actions, original_body: None)

    conv = "conv#whatsapp#abc"
    bad = _record(
        "m1",
        {"event_id": "evt-1", "conversation_id": conv, "tenant_id": "t1", "channel": "whatsapp"},
        group_id="conv#whatsapp#WRONG",
        seq=1,
        dedup_id="evt-1",
    )

    event = {"Records": [bad]}
    res = h.lambda_handler(event, context=None)

    assert "batchItemFailures" in res
    assert res["batchItemFailures"] == [{"itemIdentifier": "m1"}]
