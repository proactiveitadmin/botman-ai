import pytest
import src.adapters.twilio_http_client as tw


class DummyResp:
    def __init__(self, *, ok=True, status_code=200, json_payload=None, text=""):
        self.ok = ok
        self.status_code = status_code
        self._json_payload = json_payload
        self.text = text
        self.content = b"{}" if json_payload is not None else b""

    def json(self):
        if isinstance(self._json_payload, Exception):
            raise self._json_payload
        return self._json_payload


class DummySession:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def post(self, url, data=None, auth=None, timeout=None):
        self.calls.append({"url": url, "data": data, "auth": auth, "timeout": timeout})
        return self._resp


def test_messages_create_validates_required_params(monkeypatch):
    c = tw.Client("AC123", "token")

    with pytest.raises(RuntimeError):
        c.messages.create(to=None, body="x", from_="whatsapp:+1")

    with pytest.raises(RuntimeError):
        c.messages.create(to="whatsapp:+1", body=None, from_="whatsapp:+2")

    with pytest.raises(RuntimeError):
        c.messages.create(to="whatsapp:+1", body="x")  # missing from_ and messaging_service_sid


def test_messages_create_success(monkeypatch):
    resp = DummyResp(ok=True, status_code=201, json_payload={"sid": "SM123"})
    sess = DummySession(resp)
    monkeypatch.setattr(tw, "get_session", lambda: sess)

    c = tw.Client("AC123", "token")
    m = c.messages.create(to="whatsapp:+1", body="hello", from_="whatsapp:+2")

    assert m.sid == "SM123"
    assert sess.calls[0]["data"]["To"] == "whatsapp:+1"
    assert sess.calls[0]["data"]["Body"] == "hello"
    assert sess.calls[0]["data"]["From"] == "whatsapp:+2"


def test_messages_create_non_ok_raises(monkeypatch):
    resp = DummyResp(ok=False, status_code=400, json_payload={"message": "bad"}, text="BAD")
    sess = DummySession(resp)
    monkeypatch.setattr(tw, "get_session", lambda: sess)

    c = tw.Client("AC123", "token")
    with pytest.raises(RuntimeError) as e:
        c.messages.create(to="whatsapp:+1", body="x", from_="whatsapp:+2")
    assert "Twilio API error 400" in str(e.value)


def test_messages_create_json_decode_fallback(monkeypatch):
    resp = DummyResp(ok=False, status_code=500, json_payload=ValueError("no json"), text="OK")
    sess = DummySession(resp)
    monkeypatch.setattr(tw, "get_session", lambda: sess)

    c = tw.Client("AC123", "token")
    with pytest.raises(RuntimeError) as e:
        c.messages.create(to="whatsapp:+1", body="x", from_="whatsapp:+2")
    assert "500" in str(e.value)
