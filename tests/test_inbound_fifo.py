import json
import types

import pytest
from src.common.security import user_hmac


class DummySQS:
    """
    Zapisuje wywołania send_message, żeby można było je asercjami sprawdzić.
    """
    def __init__(self):
        self.calls = []

    def send_message(self, **kwargs):
        self.calls.append(kwargs)
        return {"MessageId": "m-1"}


@pytest.fixture
def dummy_sqs():
    """Fixture zwracająca atrapę klienta SQS."""
    return DummySQS()


def test_inbound_webhook_wysyla_na_fifo_z_group_id_i_dedup(monkeypatch, dummy_sqs):
    """
    inbound_webhook:
    - MUSI wysłać wiadomość do kolejki FIFO
    - MessageGroupId musi być równy conversation_id
    - MessageDeduplicationId musi być równy event_id

    Test zabezpiecza przed regresją, w której:
    - zapomnimy o MessageGroupId (FIFO przestaje działać),
    - groupId będzie inne niż conversation_id (psuje kolejność rozmowy),
    - zabraknie deduplikacji.
    """
    from src.lambdas.inbound_webhook import handler as h

    # Podmieniamy klienta SQS na atrapę
    monkeypatch.setattr(h, "sqs_client", lambda: dummy_sqs)

    # Podmieniamy resolver URL kolejki
    monkeypatch.setattr(h, "resolve_queue_url", lambda _name: "https://example.com/inbound.fifo")

    # Jeśli jest mechanizm antyspamowy – wyłączamy go na potrzeby testu
    if hasattr(h, "spam_service"):
        monkeypatch.setattr(h.spam_service, "is_blocked", lambda **kwargs: False)

    # Minimalny event w formacie webhooka (Twilio / WhatsApp)
    event = {
        "body": "From=whatsapp%3A%2B48111111111&Body=hello&MessageSid=SM123",
        "isBase64Encoded": False,
        "headers": {"content-type": "application/x-www-form-urlencoded"},
        "requestContext": {"requestTimeEpoch": 1700000000000},
    }

    response = h.lambda_handler(event, context=types.SimpleNamespace())
    assert response["statusCode"] in (200, 201, 204)

    # Dokładnie jedna wiadomość powinna trafić do SQS
    assert len(dummy_sqs.calls) == 1

    call = dummy_sqs.calls[0]
    body = json.loads(call["MessageBody"])

    assert body["conversation_id"].startswith("conv#whatsapp#")
    assert call["MessageGroupId"] == body["conversation_id"]
    assert call["MessageDeduplicationId"] == body["event_id"]


def test_web_widget_wysyla_na_fifo_z_group_id_i_dedup(monkeypatch, dummy_sqs):
    """
    web_widget:
    - wylicza conversation_id na podstawie channel_user_id
    - wysyła wiadomość do kolejki FIFO
    - ustawia MessageGroupId = conversation_id
    - ustawia MessageDeduplicationId = event_id
    """
    from src.lambdas.web_widget import handler as h

    monkeypatch.setattr(h, "sqs_client", lambda: dummy_sqs)
    monkeypatch.setattr(h, "resolve_queue_url", lambda _name: "https://example.com/inbound.fifo")

    event = {
        "body": json.dumps(
            {
                "tenant_id": "t1",
                "channel_user_id": "user-abc",
                "body": "wiadomość z weba",
                "language_code": "pl",
            }
        ),
        "isBase64Encoded": False,
        "headers": {"content-type": "application/json"},
    }

    response = h.lambda_handler(event, context=types.SimpleNamespace())
    assert response["statusCode"] in (200, 201, 204)

    assert len(dummy_sqs.calls) == 1

    call = dummy_sqs.calls[0]
    body = json.loads(call["MessageBody"])

    assert body["conversation_id"] == f"conv#web#{user_hmac('t1', 'web', 'user-abc')}"
    assert call["MessageGroupId"] == body["conversation_id"]
    assert call["MessageDeduplicationId"] == body["event_id"]
