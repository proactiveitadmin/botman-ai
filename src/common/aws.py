# src/common/aws.py
import os
import boto3
from botocore.config import Config

def _region():
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "eu-central-1"

def _cfg():
    return Config(
        retries={"max_attempts": int(os.getenv("AWS_MAX_ATTEMPTS", "3")), "mode": "standard"}
    )

def resolve_queue_url(env_name: str) -> str:
    url = os.getenv(env_name)
    if url:
        return url

    # LocalStack fallback by queue name
    try:
        sqs = sqs_client()
        return sqs.get_queue_url(QueueName=env_name)["QueueUrl"]
    except Exception:
        raise ValueError(f"Missing queue URL env: {env_name}")

def resolve_optional_queue_url(env_name: str) -> str | None:
    url = os.getenv(env_name)
    if url:
        return url
    try:
        return sqs_client().get_queue_url(QueueName=env_name)["QueueUrl"]
    except Exception:
        return None
    
def _endpoint_for(service: str) -> str | None:
    # 1) endpoint per-usługa (najwyższy priorytet)
    per_service = os.getenv(f"{service.upper()}_ENDPOINT") or os.getenv("LOCALSTACK_ENDPOINT") # np. S3_ENDPOINT, SQS_ENDPOINT
    if per_service:
        return per_service

    # 2) globalny override
    global_ep = os.getenv("AWS_ENDPOINT_URL")
    if global_ep:
        return global_ep

    # 3) heurystyka SAM/LocalStack (bez twardego localhosta):
    # SAM/LocalStack zwykle wstrzykują LOCALSTACK_HOSTNAME do kontenera
    host = os.getenv("LOCALSTACK_HOSTNAME")
    if host:
        return f"http://{host}:4566"

    # 4) jeżeli pracujesz ręcznie lokalnie i chcesz fallback,
    # zamiast hardcodu w kodzie – ustaw to w środowisku:
    #   $Env:S3_ENDPOINT="http://localhost:4566"
    # (brak zwrotki => boto3 użyje prawdziwego AWS)
    return None

def s3_client():
    ep = _endpoint_for("s3")
    kwargs = {"region_name": _region(), "config": _cfg()}
    if ep:
        kwargs["endpoint_url"] = ep
    return boto3.client("s3", **kwargs)

def sqs_client():
    ep = _endpoint_for("sqs")
    kwargs = {"region_name": _region(), "config": _cfg()}
    if ep:
        kwargs["endpoint_url"] = ep
    return boto3.client("sqs", **kwargs)

def ddb_resource():
    ep = _endpoint_for("dynamodb")
    kwargs = {"region_name": _region(), "config": _cfg()}
    if ep:
        kwargs["endpoint_url"] = ep
    return boto3.resource("dynamodb", **kwargs)
