import os
from src.services.spam_service import SpamService
from src.common.aws import ddb_resource

def test_spam_service_blocks_after_limit(aws_stack):
    fixed_ts = 1_700_000_000  # dowolny stały timestamp

    svc = SpamService(
        now_fn=lambda: fixed_ts,
        bucket_seconds=60,
        max_per_bucket=3,
    )

    tenant = "test-tenant-spam"  # inny tenant niż "default", żeby nie kolidować
    phone = "whatsapp:+48123123123"

    blocked_flags = [svc.is_blocked(tenant, phone) for _ in range(5)]

    assert blocked_flags[:3] == [False, False, False]
    assert blocked_flags[3:] == [True, True]
