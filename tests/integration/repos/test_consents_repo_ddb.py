from moto import mock_aws
import boto3

from src.repos.consents_repo import ConsentsRepo
from src.common.aws import _region
from src.common.security import phone_hmac, phone_last4


@mock_aws
def test_consents_repo_set_get_and_delete():
    """
    Używamy moto, żeby nie dotykać prawdziwego AWS.
    Tworzymy tabelę Consents tak, jak oczekuje repozytorium.
    """
    region = _region()
    ddb = boto3.resource("dynamodb", region_name=region)
    ddb.create_table(
        TableName="Consents",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


    repo = ConsentsRepo()

    phone = "+48123"
    tenant = "tenant-1"

    # opt-in
    item = repo.set_opt_in(tenant, phone, source="test")

    assert item["pk"] == f"{tenant}#{phone_hmac(tenant, phone)}"

@mock_aws
def test_set_opt_in_does_not_store_raw_phone():
    region = _region()
    ddb = boto3.resource("dynamodb", region_name=region)
    ddb.create_table(
        TableName="Consents",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    repo = ConsentsRepo()

    phone = "+48123"
    tenant = "tenant-1"

    item = repo.set_opt_in(tenant, phone, source="test")

    assert item["pk"] == f"{tenant}#{phone_hmac(tenant, phone)}"
    assert item["phone_hmac"] == phone_hmac(tenant, phone)
    assert item["phone_last4"] == phone_last4(phone)

    assert "phone" not in item  # kluczowe: żadnego raw phone w DDB