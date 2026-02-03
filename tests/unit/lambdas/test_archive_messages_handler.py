import json
from decimal import Decimal

import pytest

from src.lambdas.archive_messages import handler as arch


class FakeTable:
    def __init__(self, items):
        self._items = items
        self.scan_calls = []
        self.update_calls = []

    def scan(self, **kwargs):
        self.scan_calls.append(kwargs)
        return {
            'Items': self._items,
            'ScannedCount': len(self._items),
            'LastEvaluatedKey': None,
        }

    def update_item(self, **kwargs):
        self.update_calls.append(kwargs)
        return {}


class FakeDDB:
    def __init__(self, table):
        self._table = table

    def Table(self, name):
        return self._table


class FakeS3:
    def __init__(self):
        self.put_calls = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        return {}


def test_json_default_decimal():
    assert arch._json_default(Decimal('2')) == 2
    assert arch._json_default(Decimal('2.5')) == 2.5
    with pytest.raises(TypeError):
        arch._json_default(object())


def test_archive_key_sanitizes_and_prefix(monkeypatch):
    k = arch._archive_key('pref', 't1', 'a#b', '1#2')
    assert k.startswith('pref/')
    assert 'pk=a_b' in k
    assert 'sk=1_2' in k


def test_lambda_handler_missing_bucket(monkeypatch):
    monkeypatch.delenv('ARCHIVE_BUCKET', raising=False)
    with pytest.raises(RuntimeError):
        arch.lambda_handler({}, None)


def test_lambda_handler_archives_items(monkeypatch):
    monkeypatch.setenv('ARCHIVE_BUCKET', 'bkt')
    monkeypatch.setenv('ARCHIVE_PREFIX', 'archive')
    monkeypatch.setenv('DDB_TABLE_MESSAGES', 'Messages')
    monkeypatch.setenv('ARCHIVE_HOT_DAYS', '0')
    monkeypatch.setenv('ARCHIVE_MAX_ITEMS', '10')
    monkeypatch.setenv('ARCHIVE_SCAN_PAGE_LIMIT', '50')

    items = [
        {
            'pk': 't1#conv#c1',
            'sk': '0#msg#1',
            'tenant_id': 't1',
            'body': 'hello',
            'ttl_ts': Decimal('1'),
        }
    ]
    table = FakeTable(items)
    s3 = FakeS3()

    monkeypatch.setattr(arch, 'ddb_resource', lambda: FakeDDB(table))
    monkeypatch.setattr(arch, 's3_client', lambda: s3)
    monkeypatch.setattr(arch, '_now_ts', lambda: 1000)

    out = arch.lambda_handler({}, None)

    assert out['statusCode'] == 200
    assert out['archived'] == 1
    assert len(s3.put_calls) == 1
    put = s3.put_calls[0]
    assert put['Bucket'] == 'bkt'
    assert put['ContentType'] == 'application/json'
    # Body should be json bytes
    parsed = json.loads(put['Body'].decode('utf-8'))
    assert parsed['pk'] == 't1#conv#c1'
    assert len(table.update_calls) == 1
    upd = table.update_calls[0]
    assert upd['Key'] == {'pk': 't1#conv#c1', 'sk': '0#msg#1'}
    assert ':a' in upd['ExpressionAttributeValues']
