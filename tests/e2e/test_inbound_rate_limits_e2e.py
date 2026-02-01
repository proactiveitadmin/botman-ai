import os
import json
import pytest
import urllib.parse


def _read_all(sqs, q_url, *, max_msgs=10, max_loops=20):
    """
    Czytamy wiadomości z kolejki (Moto SQS).
    Ograniczamy liczbę pętli, żeby test nigdy nie "mielił" w nieskończoność.
    """
    messages = []
    loops = 0

    while loops < max_loops:
        loops += 1
        resp = sqs.receive_message(
            QueueUrl=q_url,
            MaxNumberOfMessages=max_msgs,
            WaitTimeSeconds=0,
        )
        batch = resp.get("Messages", [])
        if not batch:
            break
        messages.extend(batch)

    return messages


@pytest.mark.slow
def test_inbound_rate_limit_per_phone_blocks_after_threshold(aws_stack, monkeypatch):
    """
    E2E: Twilio webhook + SpamService + DDB + SQS.
    """
    # Importy dopiero w teście (po ustawieniu env przez conftest/fixture)
    import boto3
    from src.services.spam_service import SpamService
    from src.common.aws import ddb_resource
    from src.lambdas.inbound_webhook import handler as inbound_handler

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
        "requestContext": {"path": "/webhooks/twilio", "requestTimeEpoch": fixed_ts * 1000},
        "pathParameters": {"tenant": "default"},
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

    sqs = boto3.client("sqs", region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"))
    inbound_msgs = _read_all(sqs, aws_stack["inbound"])
    assert len(inbound_msgs) == max_per_bucket


@pytest.mark.slow
def test_inbound_rate_limit_per_tenant_blocks_after_threshold(aws_stack, monkeypatch):
    import boto3
    from src.services.spam_service import SpamService
    from src.common.aws import ddb_resource
    from src.lambdas.inbound_webhook import handler as inbound_handler

    fixed_ts = 1_700_000_000
    tenant_limit = 5

    svc = SpamService(
        now_fn=lambda: fixed_ts,
        bucket_seconds=60,
        max_per_bucket=1000,          # per phone wyłączony
        tenant_max_per_bucket=tenant_limit,
    )

    tenant_id = "default"
    bucket = svc._bucket_for_ts(fixed_ts)

    table = ddb_resource().Table(os.getenv("DDB_TABLE_INTENTS_STATS", "IntentsStats"))
    table.delete_item(Key={"pk": f"{tenant_id}#{bucket}", "sk": "__TOTAL__"})

    monkeypatch.setattr(inbound_handler, "spam_service", svc, raising=False)
    os.environ["InboundEventsQueueUrl"] = aws_stack["inbound"]

    def make_event(from_phone: str):
        encoded_from = urllib.parse.quote_plus(from_phone)
        return {
            "headers": {"Host": "localhost"},
            "requestContext": {"path": "/webhooks/twilio", "requestTimeEpoch": fixed_ts * 1000},
            "pathParameters": {"tenant": "default"},
            "body": (
                f"From={encoded_from}"
                "&To=whatsapp%3A%2B48000000000"
                "&Body=test+tenant+limit"
            ),
        }

    statuses = []
    for i in range(8):
        from_phone = f"whatsapp:+48{500000000 + i}"
        res = inbound_handler.lambda_handler(make_event(from_phone), None)
        statuses.append(res["statusCode"])

    assert statuses[:tenant_limit] == [200] * tenant_limit
    assert statuses[tenant_limit:] == [429] * (len(statuses) - tenant_limit)

    sqs = boto3.client("sqs", region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"))
    inbound_msgs = _read_all(sqs, aws_stack["inbound"])
    assert len(inbound_msgs) == tenant_limit
