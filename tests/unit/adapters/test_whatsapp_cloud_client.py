from src.adapters.whatsapp_cloud_client import (
    WhatsAppCloudClient,
    _strip_whatsapp_prefix,
    _normalize_to_msisdn,
)


class DummyResp:
    def __init__(self, ok=True, status_code=200, json_data=None, text=''):
        self.ok = ok
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.content = (text or '').encode('utf-8') if text is not None else b''

    def json(self):
        return self._json_data


class DummySession:
    def __init__(self, resp=None, exc=None):
        self.resp = resp
        self.exc = exc
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.resp


def test_helpers_normalize_and_strip():
    assert _strip_whatsapp_prefix('whatsapp:+48123') == '+48123'
    assert _normalize_to_msisdn('whatsapp:+48 123 456') == '48123456'
    assert _normalize_to_msisdn('+481234') == '481234'


def test_send_text_disabled_returns_dev_ok(monkeypatch):
    c = WhatsAppCloudClient(access_token='', phone_number_id='')
    assert c.enabled is False
    out = c.send_text('whatsapp:+48123', 'hi')
    assert out['status'] == 'DEV_OK'


def test_send_text_missing_destination():
    c = WhatsAppCloudClient(access_token='t', phone_number_id='pid')
    out = c.send_text('', 'hi')
    assert out['status'] == 'ERROR'


def test_send_text_network_exception(monkeypatch):
    sess = DummySession(exc=RuntimeError('net'))
    monkeypatch.setattr('src.adapters.whatsapp_cloud_client.get_session', lambda: sess)

    c = WhatsAppCloudClient(access_token='t', phone_number_id='pid')
    out = c.send_text('+48123', 'hi')
    assert out['status'] == 'ERROR'
    assert 'net' in out['error']


def test_send_text_http_error_parses_text(monkeypatch):
    # Simulate non-ok response with invalid json
    resp = DummyResp(ok=False, status_code=400, json_data=None, text='bad')
    # Force json() to raise
    def boom_json():
        raise ValueError('no json')
    resp.json = boom_json  # type: ignore

    sess = DummySession(resp=resp)
    monkeypatch.setattr('src.adapters.whatsapp_cloud_client.get_session', lambda: sess)

    c = WhatsAppCloudClient(access_token='t', phone_number_id='pid')
    out = c.send_text('whatsapp:+48123', 'hi')
    assert out['status'] == 'ERROR'
    assert out['http_status'] == 400
    assert out['error']['raw'] == 'bad'


def test_send_text_success_extracts_message_id(monkeypatch):
    resp = DummyResp(ok=True, status_code=200, json_data={"messages": [{"id": "mid"}]}, text='{}')
    sess = DummySession(resp=resp)
    monkeypatch.setattr('src.adapters.whatsapp_cloud_client.get_session', lambda: sess)

    c = WhatsAppCloudClient(access_token='t', phone_number_id='pid', api_version='v20.0')
    out = c.send_text('whatsapp:+48123', 'hello')
    assert out['status'] == 'OK'
    assert out['message_id'] == 'mid'
    assert sess.calls[0]['json']['to'] == '48123'
