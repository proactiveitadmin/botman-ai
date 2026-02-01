import json
import boto3
import uuid
from moto import mock_aws
from src.common.config import settings


@mock_aws
def test_kb_service_uses_language_specific_faq(monkeypatch):
    """
    Sprawdza, że KBService:
    - czyta FAQ z kb/<tenant>/<language>/faq.json
    - zwraca różne odpowiedzi dla różnych języków.
    """

    # 1) Przygotuj S3 + bucket
    s3 = boto3.client("s3", region_name="eu-central-1")

    # <<< TU ZMIANA – unikalna nazwa bucket'a >>>
    bucket_name = f"kb-test-bucket-{uuid.uuid4().hex}"

    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
    )

    # Ustaw bucket w env + w globalnym settings (Settings jest już zainicjalizowany)
    monkeypatch.setenv("KB_BUCKET", bucket_name)
    settings.kb_bucket = bucket_name

    # 2) Wrzucamy dwa różne pliki FAQ: PL i EN
    pl_faq = {"hours": "Godziny otwarcia: 6-22."}
    en_faq = {"hours": "Opening hours: 6am–10pm."}

    s3.put_object(
        Bucket=bucket_name,
        Key="default/faq_pl.json",   # wcześniej: "kb/default/pl/faq.json"
        Body=json.dumps(pl_faq).encode("utf-8"),
    )
    s3.put_object(
        Bucket=bucket_name,
        Key="default/faq_en.json",   # wcześniej: "kb/default/en/faq.json"
        Body=json.dumps(en_faq).encode("utf-8"),
    )

    from src.services.kb_service import KBService

    kb = KBService()

    ans_pl = kb.answer("hours", tenant_id="default", language_code="pl")
    ans_en = kb.answer("hours", tenant_id="default", language_code="en")

    assert ans_pl == "Godziny otwarcia: 6-22."
    assert ans_en == "Opening hours: 6am–10pm."
    assert ans_pl != ans_en