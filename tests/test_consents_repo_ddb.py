from moto import mock_aws
import boto3

from src.repos.consents_repo import ConsentsRepo
from src.common.aws import _region


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

    # opt-in
    item = repo.set_opt_in("tenant-1", "+48123", source="test")
    assert item["pk"] == "tenant-1#+48123"
    assert item["opt_in"] is True
    assert item["source"] == "test"

    loaded = repo.get("tenant-1", "+48123")
    assert loaded is not None
    assert loaded["opt_in"] is True

    # opt-out
    out_item = repo.set_opt_out("tenant-1", "+48123")
    assert out_item["opt_in"] is False

    loaded2 = repo.get("tenant-1", "+48123")
    assert loaded2 is not None
    assert loaded2["opt_in"] is False

    # delete
    repo.delete("tenant-1", "+48123")
    assert repo.get("tenant-1", "+48123") is None
