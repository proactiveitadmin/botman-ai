import json
import os
import urllib.parse

import pytest


@pytest.mark.slow
def test_e2e_twilio_to_outbound_queue_aws(aws_stack, mock_ai, monkeypatch):
    # Importy wewnątrz testu (ważne dla moto/mock_aws)
    from src.lambdas.inbound_webhook import handler as inbound_lambda
    from src.lambdas.message_router import handler as router_lambda

    inbound_msgs = []
    outbound_msgs = []

    class FakeSQS:
        def send_message(self, QueueUrl, MessageBody, **kwargs):
            if "inbound" in QueueUrl:
                inbound_msgs.append({"Body": MessageBody})
            else:
                outbound_msgs.append({"Body": MessageBody})
            return {"MessageId": "fake-msg"}

    fake_sqs = FakeSQS()

    def fake_sqs_client():
        return fake_sqs

    # Queue urls – tylko znaczniki, FakeSQS rozróżnia po substringu
    os.environ["InboundEventsQueueUrl"] = "inbound-queue"
    os.environ["OutboundQueueUrl"] = "outbound-queue"
    os.environ["WebOutboundEventsQueueUrl"] = "outbound-queue"

    # Spam off
    class NoSpam:
        def is_blocked(self, tenant_id=None, phone=None, **kwargs):
            return False

    monkeypatch.setattr(inbound_lambda, "spam_service", NoSpam(), raising=False)

    # podmieniamy SQS w obu lambdach – żadnych prawdziwych wywołań AWS
    monkeypatch.setattr(inbound_lambda, "sqs_client", fake_sqs_client, raising=True)
    monkeypatch.setattr(router_lambda, "sqs_client", fake_sqs_client, raising=True)

    # resolve_queue_url ma zwracać nasze „fake” url-e
    monkeypatch.setattr(
        inbound_lambda,
        "resolve_queue_url",
        lambda name: os.environ["InboundEventsQueueUrl"],
        raising=True,
    )
    monkeypatch.setattr(
        router_lambda,
        "resolve_queue_url",
        lambda name: os.environ["OutboundQueueUrl"],
        raising=True,
    )

    # --- 1) webhook Twilio -> inbound queue
    form = urllib.parse.urlencode(
        {
            "From": "whatsapp:+48123123123",
            "Body": "Chcę zapisać się na zajęcia",
        }
    )
    event = {
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "body": form,
        "isBase64Encoded": False,
        "pathParameters": {"tenant": "default"},
        "requestContext": {"path": "/webhook/default", "requestTimeEpoch": 0},
    }
    inbound_lambda.lambda_handler(event, None)

    assert inbound_msgs, "Brak wiadomości na inbound queue po webhooku"

    # --- 2) router -> outbound queue
    router_event = {"Records": [{"body": m["Body"]} for m in inbound_msgs]}
    router_lambda.lambda_handler(router_event, None)

    assert outbound_msgs, "Brak wiadomości na outbound queue po routerze"

    bodies = [json.loads(m["Body"]) for m in outbound_msgs]
    assert any(
        (
            "kod" in (b.get("body", "").lower())
            or "weryfik" in (b.get("body", "").lower())
            or "challenge" in (b.get("body", "").lower())
        )
        for b in bodies
    ), f"Nie znaleziono wiadomości dot. weryfikacji. Bodies: {[b.get('body') for b in bodies]}"
