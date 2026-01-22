# src/lambdas/pg_reservations/handler.py
import json
from ...services.clients_factory import ClientsFactory

clients = ClientsFactory()

def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}")
    member_id = body.get("member_id")
    class_id = body.get("class_id")
    idem = body.get("idempotency_key")

    if not (member_id and class_id and idem):
        return {"statusCode": 400, "body": "Missing required fields"}

    res = clients.perfectgym(tenant_id).reserve_class(member_id=member_id, class_id=class_id, idempotency_key=idem)
    return {"statusCode": 200, "body": json.dumps(res)}
