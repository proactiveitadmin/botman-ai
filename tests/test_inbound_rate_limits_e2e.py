import os
import json
import boto3
import pytest
import urllib.parse
from src.services.spam_service import SpamService
from src.common.aws import ddb_resource
from src.lambdas.inbound_webhook import handler as inbound_handler


def _read_all(q_url, max_msgs=10):
    """
    Pomocniczo – czytamy wszystkie wiadomości z kolejki (Moto SQS).
    WaitTimeSeconds=0, żeby test nie blokował.
    """
    sqs = boto3.client("sqs", region_name="eu-central-1")
    messages = []

    while True:
        resp = sqs.receive_message(
            QueueUrl=q_url,
            MaxNumberOfMessages=max_msgs,
            WaitTimeSeconds=0,
        )
        batch = resp.get("Messages", [])
        if not batch:
            break
        messages.extend(batch)

        # w testach nie bawimy się w kasowanie, wystarczy liczba
        # sqs.delete_message_batch(...) byłby tu w "prawdziwym" kodzie

    return messages

@pytest.mark.slow
def test_inbound_rate_limit_per_phone_blocks_after_threshold(aws_stack, monkeypatch):
    """
    E2E: Twilio webhook + SpamService + DDB + SQS.

    - limit 3 requesty / bucket / phone
    - wysyłamy 5 wiadomości z tego samego numeru
    - 3x 200, potem 2x 429
    - na inbound kolejce tylko 3 wiadomości
    """
    os.environ["InboundEventsQueueUrl"] = aws_stack["inbound"]

    fixed_ts = 1_700_000_000
    max_per_bucket = 3

    svc = SpamService(
        now_fn=lambda: fixed_ts,
        bucket_seconds=60,
        max_per_bucket=max_per_bucket,
        tenant_max_per_bucket=1000,
    )

    tenant_id = "default"
    from_phone = "whatsapp:+48123123123"
    bucket = svc._bucket_for_ts(fixed_ts)

    table = ddb_resource().Table(os.getenv("DDB_TABLE_INTENTS_STATS", "IntentsStats"))
    table.delete_item(Key={"pk": f"{tenant_id}#{bucket}", "sk": from_phone})
    table.delete_item(Key={"pk": f"{tenant_id}#{bucket}", "sk": "__TOTAL__"})

    monkeypatch.setattr(inbound_handler, "spam_service", svc, raising=False)

    event = {
        "headers": {"Host": "localhost"},
        "requestContext": {
            "path": "/webhooks/twilio",
            "requestTimeEpoch": fixed_ts * 1000,
        },
        "body": (
            "From=whatsapp%3A%2B48123123123"
            "&To=whatsapp%3A%2B48000000000"
            "&Body=test+rate+limit"
        ),
    }

    statuses = []
    for _ in range(5):
        res = inbound_handler.lambda_handler(event, None)
        statuses.append(res["statusCode"])

    assert statuses[:3] == [200, 200, 200]
    assert statuses[3:] == [429, 429]

    inbound_msgs = _read_all(aws_stack["inbound"])
    assert len(inbound_msgs) == max_per_bucket

@pytest.mark.slow
def test_inbound_rate_limit_per_tenant_blocks_after_threshold(aws_stack, monkeypatch):
    fixed_ts = 1_700_000_000
    tenant_limit = 5

    svc = SpamService(
        now_fn=lambda: fixed_ts,
        bucket_seconds=60,
        max_per_bucket=1000,          # per phone praktycznie wyłączony
        tenant_max_per_bucket=tenant_limit,
    )

    tenant_id = "default"
    bucket = svc._bucket_for_ts(fixed_ts)

    table = ddb_resource().Table(os.getenv("DDB_TABLE_INTENTS_STATS", "IntentsStats"))

    # czyścimy TOTAL (wystarczy) — reszta SK nie musi być czyszczona,
    # bo per-phone mamy wyłączone (max_per_bucket=1000)
    table.delete_item(Key={"pk": f"{tenant_id}#{bucket}", "sk": "__TOTAL__"})

    monkeypatch.setattr(inbound_handler, "spam_service", svc, raising=False)
    os.environ["InboundEventsQueueUrl"] = aws_stack["inbound"]

    def make_event(from_phone: str):
        # Twilio wysyła urlencoded form body
        encoded_from = urllib.parse.quote_plus(from_phone)
        return {
            "headers": {"Host": "localhost"},
            "requestContext": {
                "path": "/webhooks/twilio",
                "requestTimeEpoch": fixed_ts * 1000,
            },
            "body": (
                f"From={encoded_from}"
                "&To=whatsapp%3A%2B48000000000"
                "&Body=test+tenant+limit"
            ),
        }

    statuses = []
    # 8 wiadomości od różnych numerów (ten sam tenant)
    for i in range(8):
        from_phone = f"whatsapp:+48{500000000 + i}"
        res = inbound_handler.lambda_handler(make_event(from_phone), None)
        statuses.append(res["statusCode"])

    assert statuses[:tenant_limit] == [200] * tenant_limit
    assert statuses[tenant_limit:] == [429] * (len(statuses) - tenant_limit)

    inbound_msgs = _read_all(aws_stack["inbound"])
    assert len(inbound_msgs) == tenant_limit

