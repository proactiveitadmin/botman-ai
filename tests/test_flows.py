import json
import boto3
import pytest

from src.lambdas.message_router import handler as router_handler
from src.lambdas.outbound_sender import handler as outbound_handler


def _read_all_messages(queue_url: str, max_msgs: int = 10):
    """
    Pomocniczo – czytamy wiadomości z kolejki (Moto SQS).
    Uwaga: WaitTimeSeconds=0 żeby nie blokować testów.
    """
    sqs = boto3.client("sqs", region_name="eu-central-1")
    resp = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max_msgs,
        WaitTimeSeconds=0,
    )
    return resp.get("Messages", [])

@pytest.fixture(autouse=True)
def purge_queues_before_flow_tests(aws_stack):
    """
    Czyścimy outbound (i ewentualnie inbound) przed każdym testem flow,
    żeby nie widzieć wiadomości z innych testów.
    """
    sqs = boto3.client("sqs", region_name="eu-central-1")
    for url in aws_stack.values():
        sqs.purge_queue(QueueUrl=url)
        
def test_faq_flow_to_outbound_queue(aws_stack, mock_ai):
    outbound_url = aws_stack["outbound"]

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-1",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "Godziny otwarcia",
                        "tenant_id": "default",
                    }
                )
            }
        ]
    }

    router_handler.lambda_handler(event, None)

    msgs = _read_all_messages(outbound_url)
    assert len(msgs) >= 1  # może być więcej, bo inne testy też mogły coś dodać

    payloads = [json.loads(m["Body"]) for m in msgs]

    faq_msgs = [
        p for p in payloads
        if p.get("to") == "whatsapp:+48123123123"
        and (
            "godzin" in p.get("body", "").lower()
            or "otwar" in p.get("body", "").lower()
        )
    ]

    assert faq_msgs, (
        f"Nie znaleziono odpowiedzi FAQ w wiadomościach: "
        f"{[p.get('body') for p in payloads]}"
    )


def test_reservation_flow_with_confirmation(aws_stack, mock_ai, mock_pg):
    outbound_url = aws_stack["outbound"]

    # 1. Wiadomość "chcę się zapisać"
    event1 = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-2",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "Chcę się zapisać na zajęcia",
                        "tenant_id": "default",
                    }
                )
            }
        ]
    }
    router_handler.lambda_handler(event1, None)

    # Czytamy z kolejki – może być więcej wiadomości, więc filtrujemy
    msgs_1 = _read_all_messages(outbound_url, max_msgs=10)
    assert msgs_1, "Brak jakichkolwiek wiadomości po pierwszym kroku rezerwacji"

    payloads_1 = [json.loads(m["Body"]) for m in msgs_1]

    confirm_msgs = [
        p for p in payloads_1
        if p.get("to") == "whatsapp:+48123123123"
        and "potwierdzasz rezerwacj" in p.get("body", "").lower()
    ]
    assert confirm_msgs, (
        "Nie znaleziono wiadomości z prośbą o potwierdzenie rezerwacji.\n"
        f"Wiadomości w kolejce: {[p.get('body') for p in payloads_1]}"
    )

    # 2. Potwierdzenie "TAK"
    event2 = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-3",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "TAK",
                        "tenant_id": "default",
                    }
                )
            }
        ]
    }
    router_handler.lambda_handler(event2, None)

    msgs_2 = _read_all_messages(outbound_url, max_msgs=10)
    assert msgs_2, "Brak jakichkolwiek wiadomości po potwierdzeniu rezerwacji"

    payloads_2 = [json.loads(m["Body"]) for m in msgs_2]
    success_msgs = [
        p for p in payloads_2
        if p.get("to") == "whatsapp:+48123123123"
        and "zarezerwowano" in p.get("body", "").lower()
    ]

    assert success_msgs, (
        "Nie znaleziono wiadomości potwierdzającej rezerwację.\n"
        f"Wiadomości w kolejce: {[p.get('body') for p in payloads_2]}"
    )

def test_clarify_flow_when_intent_unknown(aws_stack, mock_ai):
    outbound_url = aws_stack["outbound"]

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-4",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "asdfasdfasdf",  # przypadkowy tekst → intent=clarify
                        "tenant_id": "default",
                    }
                )
            }
        ]
    }

    # Uruchamiamy router
    router_handler.lambda_handler(event, None)

    # Czytamy wiadomości z kolejki (może być ich kilka!)
    msgs = _read_all_messages(outbound_url, max_msgs=10)
    assert msgs, f"Brak jakichkolwiek wiadomości w kolejce outbound: {msgs}"

    payloads = [json.loads(m["Body"]) for m in msgs]

    # Szukamy odpowiedzi clarify
    clarify = [
        p for p in payloads
        if "doprec" in p.get("body", "").lower()  # obsługuje doprecyzuj / doprecyzować
        and p.get("to") == "whatsapp:+48123123123"
    ]

    assert clarify, (
        "Brak wiadomości clarify (prośby o doprecyzowanie) w kolejce.\n"
        f"A oto wszystkie wiadomości: {[p.get('body') for p in payloads]}"
    )



def test_outbound_sender_uses_twilio_client(mock_twilio):
    event = {
        "Records": [
            {"body": json.dumps({"to": "whatsapp:+48123123123", "body": "Hej z testu!"})}
        ]
    }

    outbound_handler.lambda_handler(event, None)

    assert len(mock_twilio) == 1
    assert mock_twilio[0]["to"] == "whatsapp:+48123123123"
    assert "Hej z testu!" in mock_twilio[0]["body"]
