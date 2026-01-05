import json
import os

from src.lambdas.outbound_sender import handler as outbound_handler

def _sqs_event(messages):
    return {"Records": [{"messageId": f"m{i}", "body": json.dumps(m)} for i,m in enumerate(messages)]}

def test_outbound_sender_idempotency_skips_duplicates(aws_stack, mock_twilio):
    os.environ["DEV_MODE"] = "true"
    # same idempotency_key twice -> only one Twilio call
    msg = {"tenant_id": "t1", "to": "whatsapp:+48123456789", "body": "hi", "channel": "whatsapp", "idempotency_key": "k-1"}
    event = _sqs_event([msg, msg])
    res = outbound_handler.lambda_handler(event, None)

    assert len(mock_twilio) == 1
    # should not fail the batch
    assert res.get("batchItemFailures") in (None, [])
    os.environ.pop("DEV_MODE", None)
