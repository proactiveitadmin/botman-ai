import uuid
from src.services.spam_service import SpamService
from src.common.aws import ddb_resource


def test_spam_service_blocks_after_limit(aws_stack):
    fixed_ts = 1_700_000_000  # stały timestamp, ważne tylko żeby był powtarzalny

    svc = SpamService(
        now_fn=lambda: fixed_ts,
        bucket_seconds=60,
        max_per_bucket=3,
    )

    # Używamy unikalnego tenant_id, żeby na 100% nie dziedziczyć starego licznika
    tenant = f"test-tenant-spam-{uuid.uuid4().hex}"
    phone = "whatsapp:+48123123123"

    # (opcjonalnie, ale pomaga przy dziwnych stanach Moto) – czyścimy ewentualny stary rekord
    table = ddb_resource().Table("IntentsStats")
    bucket = svc._bucket_for_ts(fixed_ts)
    table.delete_item(Key={"pk": f"{tenant}#{bucket}", "sk": phone})

    blocked_flags = [svc.is_blocked(tenant, phone) for _ in range(5)]

    # Pierwsze 3 wiadomości przechodzą, 4 i 5 są blokowane
    assert blocked_flags[:3] == [False, False, False]
    assert blocked_flags[3:] == [True, True]
