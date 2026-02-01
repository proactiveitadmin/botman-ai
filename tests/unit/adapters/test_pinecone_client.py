import types

import pytest

from src.adapters.pinecone_client import PineconeClient, PineconeMatch


class DummyResp:
    def __init__(self, status_code=200, json_data=None, text=''):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.content = (text or '').encode('utf-8') if text is not None else b''

    def json(self):
        return self._json_data


def test_from_tenant_config_handles_non_dict():
    c = PineconeClient.from_tenant_config({"pinecone": "nope"})
    assert isinstance(c, PineconeClient)


def test_upsert_disabled_returns_false():
    c = PineconeClient(api_key=None, index_host=None)
    assert c.enabled is False
    assert c.upsert(vectors=[{"id": "1", "values": [0.1]}], namespace="ns") is False


def test_upsert_success(monkeypatch):
    c = PineconeClient(api_key='k', index_host='example.com', timeout_s=0.01)

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith('/vectors/upsert')
        assert headers['Api-Key'] == 'k'
        assert json['namespace'] == 'ns'
        return DummyResp(status_code=201, json_data={"upsertedCount": 1}, text='{}')

    monkeypatch.setattr('src.adapters.pinecone_client.requests.post', fake_post)
    assert c.upsert(vectors=[{"id": "1", "values": [0.1]}], namespace='ns', max_attempts=1) is True


def test_query_dim_mismatch_returns_empty(monkeypatch):
    # Force expected dim via settings
    from src.common import config
    monkeypatch.setattr(config.settings, 'pinecone_index_dim', 4, raising=False)

    c = PineconeClient(api_key='k', index_host='example.com')
    res = c.query(vector=[0.1, 0.2], namespace='ns')
    assert res == []


def test_query_success_parses_matches(monkeypatch):
    from src.common import config
    monkeypatch.setattr(config.settings, 'pinecone_index_dim', None, raising=False)

    c = PineconeClient(api_key='k', index_host='example.com', timeout_s=0.01)

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith('/query')
        return DummyResp(
            status_code=200,
            json_data={
                "matches": [
                    {"id": "a", "score": 0.9, "metadata": {"x": 1}},
                    {"id": "b", "score": 0.1, "metadata": None},
                ]
            },
            text='{"matches":[]}',
        )

    monkeypatch.setattr('src.adapters.pinecone_client.requests.post', fake_post)

    out = c.query(vector=[0.0, 0.0, 0.0], namespace='ns', max_attempts=1)
    assert [m.id for m in out] == ['a', 'b']
    assert out[0].metadata == {"x": 1}
    assert out[1].metadata == {}


def test_query_retries_and_fails(monkeypatch):
    from src.common import config
    monkeypatch.setattr(config.settings, 'pinecone_index_dim', None, raising=False)

    c = PineconeClient(api_key='k', index_host='example.com', timeout_s=0.01)

    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        return DummyResp(status_code=500, json_data=None, text='err')

    monkeypatch.setattr('src.adapters.pinecone_client.requests.post', fake_post)
    monkeypatch.setattr('src.adapters.pinecone_client.time.sleep', lambda s: None)
    monkeypatch.setattr('src.adapters.pinecone_client.random.random', lambda: 0.0)

    out = c.query(vector=[0.0, 0.0, 0.0], namespace='ns', max_attempts=2)
    assert out == []
    assert calls['n'] == 2
