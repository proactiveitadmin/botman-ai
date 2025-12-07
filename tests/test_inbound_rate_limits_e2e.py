
import os
import json
import boto3
import pytest

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

    Scenariusz:
    - ustalamy mały limit (3 requesty / bucket) dla jednego numeru,
    - wysyłamy 5 wiadomości z tego samego numeru,
    - pierwsze 3 przechodzą (HTTP 200 + lądują na kolejce inbound),
    - kolejne 2 dostają HTTP 429 i NIE pojawiają się na kolejce.
    """

    # 1) Ustaw poprawny URL kolejki inbound (Moto SQS z aws_stack)
    os.environ["InboundEventsQueueUrl"] = aws_stack["inbound"]

    # 2) Przygotuj SpamService z deterministycznym czasem i niskim limitem
    fixed_ts = 1_700_000_000  # dowolny stały timestamp
    max_per_bucket = 3

    svc = SpamService(
        now_fn=lambda: fixed_ts,
        bucket_seconds=60,
        max_per_bucket=max_per_bucket,
        tenant_max_per_bucket=1000,  # żeby nie wchodził limit "per tenant"
    )

    # 3) Wyczyść bucket w DDB (na wszelki wypadek, gdyby inne testy coś zostawiły)
    tenant_id = "default"  # tak jak w inbound_webhook.handler
    from_phone = "whatsapp:+48123123123"
    bucket = svc._bucket_for_ts(fixed_ts)

    table = ddb_resource().Table(os.getenv("DDB_TABLE_INTENTS_STATS", "IntentsStats"))
    table.delete_item(Key={"pk": f"{tenant_id}#{bucket}", "sk": from_phone})
    table.delete_item(Key={"pk": f"{tenant_id}#{bucket}", "sk": "__TOTAL__"})

    # 4) Podmień globalny spam_service w handlerze na naszą instancję
    monkeypatch.setattr(inbound_handler, "spam_service", svc, raising=False)

    # 5) Zbuduj event tak jak w innych testach inbound_webhook
    event = {
        "headers": {"Host": "localhost"},
        "requestContext": {
            "path": "/webhooks/twilio",
            "requestTimeEpoch": fixed_ts * 1000,
        },
        "body": "From=whatsapp%3A%2B48123123123"
                "&To=whatsapp%3A%2B48000000000"
                "&Body=test+rate+limit",
    }

    # 6) Wywołaj webhook kilka razy z tego samego numeru
    statuses = []
    for _ in range(5):
        res = inbound_handler.lambda_handler(event, None)
        statuses.append(res["statusCode"])

    # 7) Pierwsze 3 przechodzą, kolejne 2 zablokowane
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3:] == [429, 429]

    # 8) Na kolejce inbound powinny znaleźć się tylko 3 wiadomości
    inbound_msgs = _read_all(aws_stack["inbound"])
    assert len(inbound_msgs) == max_per_bucket, (
        f"Oczekiwano {max_per_bucket} wiadomości na kolejce inbound, "
        f"dostałem {len(inbound_msgs)}"
    )
    
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
    # czyścimy bucket (łącznie z "__TOTAL__")
    for sk in ["__TOTAL__"] + [f"whatsapp:+48{n:09d}" for n in range(10)]:
        table.delete_item(Key={"pk": f"{tenant_id}#{bucket}", "sk": sk})

    monkeypatch.setattr(inbound_handler, "spam_service", svc, raising=False)
    os.environ["InboundEventsQueueUrl"] = aws_stack["inbound"]

    def make_event(from_phone: str):
        return {
            "headers": {"Host": "localhost"},
            "requestContext": {
                "path": "/webhooks/twilio",
                "requestTimeEpoch": fixed_ts * 1000,
            },
            "body": (
                f"From={from_phone}&To=whatsapp%3A%2B48000000000&Body=test+tenant+limit"
            ),
        }

    statuses = []
    # 8 wiadomości od różnych numerów (ten sam tenant)
    for i in range(8):
        from_phone = f"whatsapp:+48{500000000 + i}"
        res = inbound_handler.lambda_handler(make_event(from_phone), None)
        statuses.append(res["statusCode"])

    # pierwsze 5 (limit tenanta) przechodzą, reszta 429
    assert statuses[:tenant_limit] == [200] * tenant_limit
    assert statuses[tenant_limit:] == [429] * (len(statuses) - tenant_limit)

    inbound_msgs = _read_all(aws_stack["inbound"])
    assert len(inbound_msgs) == tenant_limit

