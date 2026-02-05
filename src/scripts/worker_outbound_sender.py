import os
import time
import json
import logging

import boto3
import botocore

# -----------------------
# IMPORTANT for LocalStack
# -----------------------
ENDPOINT = os.getenv("AWS_ENDPOINT_URL") or os.getenv("LOCALSTACK_ENDPOINT") or "http://localhost:4566"
REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "eu-central-1"

os.environ.setdefault("AWS_ENDPOINT_URL", ENDPOINT)
os.environ.setdefault("LOCALSTACK_ENDPOINT", ENDPOINT)
os.environ.setdefault("SQS_ENDPOINT", ENDPOINT)
os.environ.setdefault("DYNAMODB_ENDPOINT", ENDPOINT)
os.environ.setdefault("SSM_ENDPOINT", ENDPOINT)
os.environ.setdefault("S3_ENDPOINT", ENDPOINT)

os.environ.setdefault("AWS_REGION", REGION)
os.environ.setdefault("AWS_DEFAULT_REGION", REGION)

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from src.lambdas.outbound_sender.handler import lambda_handler  # noqa: E402

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger("worker_outbound_sender")

OUT_Q = os.getenv("OutboundQueueUrl")
if not OUT_Q:
    raise RuntimeError("Missing env var OutboundQueueUrl. Run scripts/create_local_resources.ps1 first.")

sqs = boto3.client("sqs", endpoint_url=ENDPOINT, region_name=REGION)

def _build_sqs_record(m: dict) -> dict:
    return {
        "messageId": m.get("MessageId"),
        "receiptHandle": m.get("ReceiptHandle"),
        "body": m.get("Body"),
        "attributes": m.get("Attributes") or {},
        "messageAttributes": m.get("MessageAttributes") or {},
        "md5OfBody": m.get("MD5OfBody"),
        "eventSource": "aws:sqs",
        "eventSourceARN": os.getenv("OutboundQueueArn", ""),
        "awsRegion": REGION,
    }

def _failed_ids(result) -> set[str]:
    if not isinstance(result, dict):
        return set()
    failures = result.get("batchItemFailures") or []
    return {str(f.get("itemIdentifier")) for f in failures if f.get("itemIdentifier")}

print(f"[worker_outbound_sender] polling {OUT_Q} (endpoint={ENDPOINT}, region={REGION})")

while True:
    try:
        resp = sqs.receive_message(
            QueueUrl=OUT_Q,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=10,
            AttributeNames=["All"],
            MessageAttributeNames=["All"],
        )
        msgs = resp.get("Messages", [])
        if not msgs:
            continue

        print(f"[worker_outbound_sender] got {len(msgs)} msg(s)")
        event = {"Records": [_build_sqs_record(m) for m in msgs]}

        result = lambda_handler(event, None)
        failed = _failed_ids(result)

        deleted = 0
        for m in msgs:
            mid = m.get("MessageId")
            if mid and mid in failed:
                log.warning("keeping failed messageId=%s for retry", mid)
                continue
            sqs.delete_message(QueueUrl=OUT_Q, ReceiptHandle=m["ReceiptHandle"])
            deleted += 1

        print(f"[worker_outbound_sender] done. deleted={deleted} failed={len(failed)}")

    except botocore.exceptions.ClientError as e:
        print(f"[worker_outbound_sender] aws error: {e}")
        time.sleep(1)
    except Exception as e:
        print(f"[worker_outbound_sender] error: {e}")
        time.sleep(1)
