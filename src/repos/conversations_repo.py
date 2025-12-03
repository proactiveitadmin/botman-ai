import os, time
from ..common.aws import ddb_resource
from boto3.dynamodb.conditions import Key

class ConversationsRepo:
    def __init__(self):
        self.table = ddb_resource().Table(
            os.environ.get("DDB_TABLE_CONVERSATIONS", "Conversations")
        )

    def conversation_pk(self, tenant_id: str, channel: str, channel_user_id: str) -> dict:
        return {
            "pk": f"tenant#{tenant_id}",
            "sk": f"conv#{channel}#{channel_user_id}",
        }

    def get_conversation(self, tenant_id: str, channel: str, channel_user_id: str) -> dict | None:
        resp = self.table.get_item(
            Key=self.conversation_pk(tenant_id, channel, channel_user_id)
        )
        return resp.get("Item")
    
    def assign_agent(self, tenant_id: str, channel: str, channel_user_id: str, agent_id: str):
        self.upsert_conversation(
            tenant_id,
            channel,
            channel_user_id,
            assigned_agent=agent_id,
            state_machine_status="handover",
        )

    def release_agent(self, tenant_id: str, channel: str, channel_user_id: str):
        self.upsert_conversation(
            tenant_id,
            channel,
            channel_user_id,
            assigned_agent=None,
            state_machine_status=None,
        )

    def upsert_conversation(
        self,
        tenant_id: str,
        channel: str,
        channel_user_id: str,
        *,
        language_code: str | None = None,
        last_intent: str | None = None,
        state_machine_status: str | None = None,
        pg_member_id: str | None = None,
        pg_verification_level: str | None = None,
        pg_verified_until: int | None = None,
        verification_code: str | None = None,
        pg_challenge_type: str | None = None,
        pg_challenge_attempts: int | None = None,
        assigned_agent: str | None = None,
    ):
        """
        Upsert rozmowy – tylko pola, które nie są None, są aktualizowane.
        """
        key = self.conversation_pk(tenant_id, channel, channel_user_id)

        update_expr_parts = []
        expr_vals = {}

        def set_field(field_name: str, value):
            update_expr_parts.append(f"{field_name} = :{field_name}")
            expr_vals[f":{field_name}"] = value

        now_ts = int(time.time())
        set_field("updated_at", now_ts)

        if language_code is not None:
            set_field("language_code", language_code)
        if last_intent is not None:
            set_field("last_intent", last_intent)
        if state_machine_status is not None:
            set_field("state_machine_status", state_machine_status)
        if pg_member_id is not None:
            set_field("pg_member_id", pg_member_id)
        if pg_verification_level is not None:
            set_field("pg_verification_level", pg_verification_level)
        if pg_verified_until is not None:
            set_field("pg_verified_until", pg_verified_until)
        if verification_code is not None:
            set_field("verification_code", verification_code)
        if pg_challenge_type is not None:
            set_field("pg_challenge_type", pg_challenge_type)
        if pg_challenge_attempts is not None:
            set_field("pg_challenge_attempts", pg_challenge_attempts)
        if assigned_agent is not None:
            set_field("assigned_agent", assigned_agent)

        if not update_expr_parts:
            return

        update_expr = "SET " + ", ".join(update_expr_parts)

        self.table.update_item(
            Key=key,
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_vals,
        )

    def find_by_verification_code(self, tenant_id: str, verification_code: str) -> dict | None:
        resp = self.table.query(
            IndexName="tenant_verification_idx",
            KeyConditionExpression=Key("tenant_id").eq(tenant_id)
                                   & Key("verification_code").eq(verification_code),
            Limit=1,
        )
        items = resp.get("Items") or []
        return items[0] if items else None
        
    def get(self, pk: str, sk: str):
        return self.table.get_item(Key={"pk": pk, "sk": sk}).get("Item")

    def delete(self, pk: str, sk: str):
        self.table.delete_item(Key={"pk": pk, "sk": sk})

    def put(self, item: dict):
        self.table.put_item(Item=item)


        
    

