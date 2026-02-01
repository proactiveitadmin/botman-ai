import os
import json
import boto3
from src.repos.messages_repo import MessagesRepo
from src.lambdas.archive_messages import handler as archiver


def test_archive_and_hydrate_from_s3(aws_stack, monkeypatch):
    # S3 bucket for archive
    s3 = boto3.client("s3", region_name="eu-central-1")
    bucket = "test-archive-bucket"
    s3.create_bucket(
        Bucket=bucket,
        CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
    )

    monkeypatch.setenv("ARCHIVE_BUCKET", bucket)
    monkeypatch.setenv("ARCHIVE_PREFIX", "archive/")
    monkeypatch.setenv("ARCHIVE_HOT_DAYS", "0")  # archive everything older than 'now'
    monkeypatch.setenv("ARCHIVE_MAX_ITEMS", "100")
    monkeypatch.setenv("DDB_TABLE_MESSAGES", "Messages")

    repo = MessagesRepo()

    # Put an old message with body
    item = {
        "pk": "tenantA#conv123",
        "sk": "1#inbound#msg1",
        "tenant_id": "tenantA",
        "conversation_id": "conv123",
        "msg_id": "msg1",
        "direction": "inbound",
        "body": "hello archived",
        "from_phone_last4": "6789",
        "to_phone_last4": "0000",
        "channel": "whatsapp",
        "ttl_ts": 9999999999,
    }
    repo.put(item)

    # Run archiver
    res = archiver.lambda_handler({}, None)
    assert res["archived"] == 1

    # Verify S3 object exists and contains body
    # (key is deterministic: tenant + pk/sk)
    objects = s3.list_objects_v2(Bucket=bucket, Prefix="archive/tenant_id=tenantA/")
    assert objects.get("KeyCount", 0) == 1
    key = objects["Contents"][0]["Key"]
    obj = s3.get_object(Bucket=bucket, Key=key)
    payload = json.loads(obj["Body"].read().decode("utf-8"))
    assert payload["body"] == "hello archived"

    # Verify DDB record is marked Archived and body removed
    ddb = boto3.resource("dynamodb", region_name="eu-central-1")
    table = ddb.Table("Messages")
    stored = table.get_item(Key={"pk": item["pk"], "sk": item["sk"]})["Item"]
    assert stored["archived_status"] == "Archived"
    assert stored["archive_bucket"] == bucket
    assert stored["archive_key"] == key
    assert "body" not in stored

    # Hydration via repo should bring body back (read-only)
    history = repo.get_last_messages("tenantA", "conv123", limit=10)
    assert len(history) == 1
    assert history[0]["body"] == "hello archived"