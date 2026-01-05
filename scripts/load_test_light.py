"""Lekki load test dla SQS -> Lambda.

Użycie:
  export AWS_REGION=eu-central-1
  export InboundEventsQueueUrl=...
  python tools/load_test_light.py --count 200 --duplicates 20

Skrypt wysyła paczki (SendMessageBatch) do inbound-events.fifo.
Opcjonalnie dodaje duplikaty (te same event_id) aby sprawdzić deduplikację/idempotencję.
"""

import argparse
import json
import os
import time
import uuid

import boto3

def new_id(prefix="evt-"):
    return prefix + uuid.uuid4().hex

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--duplicates", type=int, default=0, help="ile duplikatów (powtórzonych event_id) dodać")
    ap.add_argument("--batch", type=int, default=10)
    args = ap.parse_args()

    qurl = os.environ.get("InboundEventsQueueUrl")
    if not qurl:
        raise SystemExit("Missing InboundEventsQueueUrl env var")

    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-central-1"))

    # przygotuj event_id listę + duplikaty
    event_ids = [new_id() for _ in range(args.count)]
    for i in range(min(args.duplicates, args.count)):
        event_ids.append(event_ids[i])  # duplikat

    t0 = time.time()
    sent = 0
    batch = []
    for i, eid in enumerate(event_ids):
        msg = {
            "event_id": eid,
            "from": "whatsapp:+48111111111",
            "to": "whatsapp:+48222222222",
            "body": f"ping {i}",
            "tenant_id": "loadtest",
            "ts": int(time.time() * 1000),
            "channel": "whatsapp",
            "channel_user_id": "whatsapp:+48111111111",
            "conversation_id": "loadtest-conv-1",
        }
        batch.append({
            "Id": str(i),
            "MessageBody": json.dumps(msg),
            "MessageGroupId": msg["conversation_id"],
            "MessageDeduplicationId": eid,
        })

        if len(batch) == args.batch:
            sqs.send_message_batch(QueueUrl=qurl, Entries=batch)
            sent += len(batch)
            batch = []

    if batch:
        sqs.send_message_batch(QueueUrl=qurl, Entries=batch)
        sent += len(batch)

    dt = time.time() - t0
    print(f"Sent: {sent} messages (incl. duplicates={args.duplicates}) in {dt:.2f}s -> {sent/dt:.1f} msg/s")

if __name__ == "__main__":
    main()
