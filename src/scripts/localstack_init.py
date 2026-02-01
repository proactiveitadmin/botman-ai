#!/usr/bin/env python3
"""Create LocalStack resources: SQS queues + minimal DDB tables."""
import os, boto3

AWS_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
REGION = os.getenv("AWS_DEFAULT_REGION", "eu-central-1")

sqs = boto3.client("sqs", endpoint_url=AWS_ENDPOINT, region_name=REGION)
ddb = boto3.client("dynamodb", endpoint_url=AWS_ENDPOINT, region_name=REGION)

def ensure_queue(name):
    try:
        resp = sqs.get_queue_url(QueueName=name)
        print(f"[init] queue exists: {name} -> {resp['QueueUrl']}")
        return resp["QueueUrl"]
    except:
        resp = sqs.create_queue(QueueName=name)
        print(f"[init] queue created: {name} -> {resp['QueueUrl']}")
        return resp["QueueUrl"]

def ensure_table(name, attrs, keys):
    try:
        ddb.describe_table(TableName=name)
        print(f"[init] table exists: {name}")
    except ddb.exceptions.ResourceNotFoundException:
        ddb.create_table(
            TableName=name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=attrs,
            KeySchema=keys,
        )
        print(f"[init] table created: {name}")

if __name__ == "__main__":
    inbound = ensure_queue("inbound-events")
    outbound = ensure_queue("outbound-messages")

    ensure_table("Messages",
        [{"AttributeName":"pk","AttributeType":"S"},{"AttributeName":"sk","AttributeType":"S"}],
        [{"AttributeName":"pk","KeyType":"HASH"},{"AttributeName":"sk","KeyType":"RANGE"}]
    )
    ensure_table(
        "Conversations",
        [
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        [
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
    )
    ensure_table("Campaigns",
        [{"AttributeName":"pk","AttributeType":"S"}],
        [{"AttributeName":"pk","KeyType":"HASH"}]
    )
    ensure_table("IntentsStats",
        [{"AttributeName":"pk","AttributeType":"S"},{"AttributeName":"sk","AttributeType":"S"}],
        [{"AttributeName":"pk","KeyType":"HASH"},{"AttributeName":"sk","KeyType":"RANGE"}]
    )
    ensure_table(
        "Consents",
        [{"AttributeName": "pk", "AttributeType": "S"}],
        [{"AttributeName": "pk", "KeyType": "HASH"}],
    )


    print("\n[init] export these env vars in your shell:")
    print(f"export AWS_ENDPOINT_URL={AWS_ENDPOINT}")
    print(f"export AWS_DEFAULT_REGION={REGION}")
    print(f"export InboundEventsQueueUrl={inbound}")
    print(f"export OutboundQueueUrl={outbound}")
