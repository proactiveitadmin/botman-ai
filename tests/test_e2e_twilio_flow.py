from src.lambdas.inbound_webhook import handler as inbound_lambda
from src.lambdas.message_router import handler as router_lambda
import json, boto3


def _read_all(q_url, max_msgs=10):
    """
    Pomocniczo – czytamy wiadomości z kolejki (Moto SQS).
    WaitTimeSeconds=0, żeby test nie blokował.
    """
    sqs = boto3.client("sqs", region_name="eu-central-1")
    resp = sqs.receive_message(QueueUrl=q_url, MaxNumberOfMessages=max_msgs, WaitTimeSeconds=0)
    return resp.get("Messages", [])



def test_e2e_twilio_to_outbound_queue(aws_stack, mock_ai):
    """
    E2E: Twilio → inbound_webhook → InboundEventsQueue → message_router → OutboundQueue.

    Wejście: przykładowy event Twilio z tests/events/inbound.json (body: "chcę się zapisać")
    Oczekujemy: w OutboundQueue pojawia się wiadomość z prośbą o potwierdzenie rezerwacji.
    """
    event = json.load(open("tests/events/inbound.json", "r", encoding="utf-8"))

    # 1) Twilio → webhook → inbound SQS
    res = inbound_lambda.lambda_handler(event, None)
    assert res["statusCode"] == 200

    inbound_msgs = _read_all(aws_stack["inbound"])
    assert inbound_msgs, "Brak wiadomości w kolejce inbound po webhooku"

    # 2) inbound SQS → router
    router_event = {"Records": [{"body": m["Body"]} for m in inbound_msgs]}
    router_lambda.lambda_handler(router_event, None)

    # 3) router → outbound SQS
    outbound_msgs = _read_all(aws_stack["outbound"])
    assert outbound_msgs, "Brak wiadomości w kolejce outbound po przejściu przez router"

    bodies = [json.loads(m["Body"]) for m in outbound_msgs]
    # np. pierwsza wiadomość jest o rezerwacji:
    assert any("potwierdzasz rezerwacj" in b.get("body", "").lower() for b in bodies)
