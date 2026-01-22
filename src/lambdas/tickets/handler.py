import json
from ...repos.messages_repo import MessagesRepo
from ...services.ticketing_service import TicketingService
from ...services.clients_factory import ClientsFactory
from ...services.tenant_config_service import TenantConfigService
from ...common.logging import logger
from ...common.security import conversation_key

messages = MessagesRepo()
ticketing = TicketingService(clients_factory=ClientsFactory(TenantConfigService()))

def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "no-records"}

    for r in records:
        payload = json.loads(r["body"])
        tenant_id = payload["tenant_id"]
        conv_key = conversation_key(
            tenant_id,
            payload.get("channel", "whatsapp"),
            payload.get("channel_user_id"),
            payload.get("conversation_id"),
        )
        history_items = messages.get_last_messages(tenant_id, conv_key, limit=10)
        # budujesz description + meta tak jak wyżej
        ticketing.create_ticket(tenant_id=tenant_id, summary=..., description=..., meta=...)

    return {"statusCode": 200}
