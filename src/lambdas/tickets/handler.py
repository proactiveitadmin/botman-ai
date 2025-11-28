import json
from ...adapters.jira_client import JiraClient
from ...repos.messages_repo import MessagesRepo
from ...common.logging import logger

jira = JiraClient()
messages = MessagesRepo()

def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "no-records"}

    for r in records:
        payload = json.loads(r["body"])
        tenant_id = payload["tenant_id"]
        conv_key = payload.get("conversation_id") or payload.get("channel_user_id")

        history_items = messages.get_last_messages(tenant_id, conv_key, limit=10)
        # budujesz description + meta tak jak wyżej
        ...
        jira.create_ticket(...)

    return {"statusCode": 200}
