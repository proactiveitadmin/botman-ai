import os
import boto3
from boto3.dynamodb.conditions import Key
from src.common.security import phone_hmac, normalize_phone


def _put_message(ddb, pk: str, sk: str, created_at: int):
    ddb.Table("Messages").put_item(
        Item={"pk": pk, "sk": sk, "created_at": created_at, "ttl_ts": created_at + 86400}
    )

def _put_conversation(ddb, pk: str, sk: str, updated_at: int):
    ddb.Table("Conversations").put_item(Item={"pk": pk, "sk": sk, "updated_at": updated_at, "ttl_ts": updated_at + 86400})

def _put_intents_stat(ddb, tenant_id: str, bucket: str, phone: str, last_ts: int):
    canonical = normalize_phone(phone)
    sk = phone_hmac(tenant_id, canonical)
    ddb.Table("IntentsStats").put_item(
        Item={"pk": f"{tenant_id}#{bucket}", "sk": sk, "cnt": 1, "last_ts": last_ts}
    )
    return sk

def test_housekeeping_ttl_mode_noop_does_not_delete(aws_stack, monkeypatch):
    from src.lambdas.housekeeping import handler as hk

    fixed_now = 1_700_000_000
    monkeypatch.setattr(hk.time, "time", lambda: fixed_now)

    ddb = boto3.resource("dynamodb", region_name="eu-central-1")

    # Arrange: wstawiamy "stare" dane
    conv_pk = "tenant#default"
    conv_sk = "conv#whatsapp#u1"
    _put_conversation(ddb, conv_pk, conv_sk, updated_at=fixed_now - 10 * 24 * 3600)

    msg_pk = "default#conv#whatsapp#u1"
    _put_message(ddb, msg_pk, "1#inbound#m1", created_at=fixed_now - 10 * 24 * 3600)

    # Act: bez gdpr_delete
    resp = hk.lambda_handler({}, None)

    # Assert: nic nie usunięto (TTL nie jest symulowany w teście)
    assert resp["statusCode"] == 200
    assert resp["mode"] == "ttl_enabled"
    assert "Item" in ddb.Table("Conversations").get_item(Key={"pk": conv_pk, "sk": conv_sk})
    assert "Item" in ddb.Table("Messages").get_item(Key={"pk": msg_pk, "sk": "1#inbound#m1"})

def test_housekeeping_gdpr_delete_by_user_hmac(aws_stack, monkeypatch):
    from src.lambdas.housekeeping import handler as hk

    fixed_now = 1_700_000_000
    monkeypatch.setattr(hk.time, "time", lambda: fixed_now)

    ddb = boto3.resource("dynamodb", region_name="eu-central-1")

    # Data for user u1 (whatsapp)
    _put_conversation(ddb, "tenant#default", "conv#whatsapp#u1", updated_at=fixed_now)
    _put_message(ddb, "default#conv#whatsapp#u1", "1#inbound#m1", created_at=fixed_now)
    _put_message(ddb, "default#conv#whatsapp#u1", "2#outbound#m2", created_at=fixed_now)

    # IntentsStats for that phone (stored as phone_hmac)
    phone_u1 = "whatsapp:+48123456789"
    bucket1 = "202501010101"
    sk_u1 = _put_intents_stat(ddb, "default", bucket1, phone_u1, last_ts=fixed_now)

    # Another user stays
    _put_conversation(ddb, "tenant#default", "conv#whatsapp#u2", updated_at=fixed_now)
    _put_message(ddb, "default#conv#whatsapp#u2", "1#inbound#m3", created_at=fixed_now)
    phone_u2 = "whatsapp:+48200000000"
    bucket2 = "202501010102"
    sk_u2 = _put_intents_stat(ddb, "default", bucket2, phone_u2, last_ts=fixed_now)

    # Act
    resp = hk.lambda_handler(
        {"gdpr_delete": {"tenant_id": "default", "user_hmac": "u1", "channels": ["whatsapp"], "phone": phone_u1}},
        None,
    )

    # Assert
    assert resp["statusCode"] == 200

    assert "Item" not in ddb.Table("Conversations").get_item(
        Key={"pk": "tenant#default", "sk": "conv#whatsapp#u1"}
    )

    remaining = ddb.Table("Messages").query(
        KeyConditionExpression=Key("pk").eq("default#conv#whatsapp#u1")
    )["Items"]
    assert remaining == []

    # IntentsStats for u1 deleted
    assert "Item" not in ddb.Table("IntentsStats").get_item(
        Key={"pk": "default#202501010101", "sk": sk_u1}
    )

    # other user untouched
    assert "Item" in ddb.Table("Conversations").get_item(
        Key={"pk": "tenant#default", "sk": "conv#whatsapp#u2"}
    )
    assert "Item" in ddb.Table("IntentsStats").get_item(
        Key={"pk": "default#202501010102", "sk": sk_u2}
    )
