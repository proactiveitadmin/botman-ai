import os, time
from ..common.aws import ddb_resource
from boto3.dynamodb.conditions import Key
from ..common.security import user_hmac
from decimal import Decimal
from typing import Any


# Sentinel pozwalający odróżnić: "parametr nie podany" od "parametr ustawiony na None".
# Dzięki temu możemy wspierać kasowanie pól (REMOVE) bez psucia istniejących wywołań.
_UNSET = object()

class ConversationsRepo:
    def __init__(self):
        self.table = ddb_resource().Table(
            os.environ.get("DDB_TABLE_CONVERSATIONS", "Conversations")
        )
        self.retention_days: int = int(os.getenv("CONVERSATIONS_RETENTION_DAYS", "365"))

    def conversation_pk(self, tenant_id: str, channel: str, channel_user_id: str) -> dict:
        """DDB key for conversation.

        NOTE: channel_user_id may contain PII (phone / session id). We never put it
        into PK/SK. Instead we derive a salted user_id using HMAC + pepper.
        """
        uid = user_hmac(tenant_id, channel, channel_user_id)
        return {
            "pk": f"tenant#{tenant_id}",
            "sk": f"conv#{channel}#{uid}",
        }
        
    def _to_native(self, v: Any) -> Any:
        """Normalize DynamoDB-decoded values.

        boto3 returns numbers as Decimal; tests and most of our code expects int
        for timestamps/counters. We convert Decimal to int where it's integral.
        """
        if isinstance(v, Decimal):
            # if integral -> int, else float
            if v % 1 == 0:
                return int(v)
            return float(v)
        if isinstance(v, list):
            return [self._to_native(x) for x in v]
        if isinstance(v, dict):
            return {k: self._to_native(val) for k, val in v.items()}
        return v

    def _normalize_item(self, item: dict | None) -> dict | None:
        if not item:
            return item
        return self._to_native(item)

    def conversation_pk_by_uid(self, tenant_id: str, channel: str, uid: str) -> dict:
        """DDB key for conversation when you already have hashed user id (uid)."""
        return {
            "pk": f"tenant#{tenant_id}",
            "sk": f"conv#{channel}#{uid}",
        }

    def upsert_conversation_by_uid(
        self,
        tenant_id: str,
        channel: str,
        uid: str,
        *,
        language_code=_UNSET,
        last_intent=_UNSET,
        state_machine_status=_UNSET,
        crm_member_id=_UNSET,
        crm_verification_level=_UNSET,
        crm_verified_until=_UNSET,
        verification_code=_UNSET,
        crm_challenge_type=_UNSET,
        crm_challenge_attempts=_UNSET,
        crm_otp_hash=_UNSET,
        crm_otp_expires_at=_UNSET,
        crm_otp_attempts_left=_UNSET,
        crm_otp_last_sent_at=_UNSET,
        crm_otp_email=_UNSET,
        assigned_agent=_UNSET,
        crm_post_intent=_UNSET,
        crm_post_slots=_UNSET,
        crm_verification_blocked_until=_UNSET,
    ):
        """Upsert rozmowy po pre-hashowanym UID (bez PII w handlerze)."""
        key = self.conversation_pk_by_uid(tenant_id, channel, uid)

        set_parts: list[str] = []
        remove_parts: list[str] = []
        expr_vals: dict = {}

        def set_field(field_name: str, value):
            set_parts.append(f"{field_name} = :{field_name}")
            expr_vals[f":{field_name}"] = value

        def maybe_set_or_remove(field_name: str, value):
            if value is _UNSET:
                return
            if value is None:
                remove_parts.append(field_name)
                return
            set_field(field_name, value)

        now_ts = int(time.time())
        set_field("updated_at", now_ts)

        ttl_ts = now_ts + self.retention_days * 86400
        set_field("ttl_ts", ttl_ts)

        maybe_set_or_remove("language_code", language_code)
        maybe_set_or_remove("last_intent", last_intent)
        maybe_set_or_remove("state_machine_status", state_machine_status)
        maybe_set_or_remove("crm_member_id", crm_member_id)
        maybe_set_or_remove("crm_verification_level", crm_verification_level)
        maybe_set_or_remove("crm_verified_until", crm_verified_until)
        maybe_set_or_remove("verification_code", verification_code)
        maybe_set_or_remove("crm_challenge_type", crm_challenge_type)
        maybe_set_or_remove("crm_challenge_attempts", crm_challenge_attempts)
        maybe_set_or_remove("crm_otp_hash", crm_otp_hash)
        maybe_set_or_remove("crm_otp_expires_at", crm_otp_expires_at)
        maybe_set_or_remove("crm_otp_attempts_left", crm_otp_attempts_left)
        maybe_set_or_remove("crm_otp_last_sent_at", crm_otp_last_sent_at)
        maybe_set_or_remove("crm_otp_email", crm_otp_email)
        maybe_set_or_remove("assigned_agent", assigned_agent)
        maybe_set_or_remove("crm_post_intent", crm_post_intent)
        maybe_set_or_remove("crm_post_slots", crm_post_slots)
        maybe_set_or_remove("crm_verification_blocked_until", crm_verification_blocked_until)

        if not set_parts and not remove_parts:
            return

        expr = ""
        if set_parts:
            expr += "SET " + ", ".join(set_parts)
        if remove_parts:
            if expr:
                expr += " "
            expr += "REMOVE " + ", ".join(remove_parts)

        self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues=expr_vals or None,
        )

    def get_conversation(self, tenant_id: str, channel: str, channel_user_id: str) -> dict | None:
        resp = self.table.get_item(
            Key=self.conversation_pk(tenant_id, channel, channel_user_id)
        )
        return self._normalize_item(resp.get("Item"))
    
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
        language_code=_UNSET,
        last_intent=_UNSET,
        state_machine_status=_UNSET,
        crm_member_id=_UNSET,
        crm_verification_level=_UNSET,
        crm_verified_until=_UNSET,
        verification_code=_UNSET,
        crm_challenge_type=_UNSET,
        crm_challenge_attempts=_UNSET,
        crm_otp_hash=_UNSET,
        crm_otp_expires_at=_UNSET,
        crm_otp_attempts_left=_UNSET,
        crm_otp_last_sent_at=_UNSET,
        crm_otp_email=_UNSET,
        assigned_agent=_UNSET,
        crm_post_intent=_UNSET,
        crm_post_slots=_UNSET,
        crm_verification_blocked_until=_UNSET,
    ):
        """Upsert rozmowy.

        - pola z wartością `_UNSET` są ignorowane (nie aktualizujemy),
        - pola ustawione na `None` są usuwane (REMOVE),
        - pozostałe pola są ustawiane (SET).
        """
        key = self.conversation_pk(tenant_id, channel, channel_user_id)

        set_parts: list[str] = []
        remove_parts: list[str] = []
        expr_vals: dict = {}

        def set_field(field_name: str, value):
            set_parts.append(f"{field_name} = :{field_name}")
            expr_vals[f":{field_name}"] = value

        def maybe_set_or_remove(field_name: str, value):
            if value is _UNSET:
                return
            if value is None:
                remove_parts.append(field_name)
                return
            set_field(field_name, value)

        now_ts = int(time.time())
        set_field("updated_at", now_ts)
              
        ttl_ts = now_ts + self.retention_days * 86400
        set_field("ttl_ts", ttl_ts)

        maybe_set_or_remove("language_code", language_code)
        maybe_set_or_remove("last_intent", last_intent)
        maybe_set_or_remove("state_machine_status", state_machine_status)
        maybe_set_or_remove("crm_member_id", crm_member_id)
        maybe_set_or_remove("crm_verification_level", crm_verification_level)
        maybe_set_or_remove("crm_verified_until", crm_verified_until)
        maybe_set_or_remove("verification_code", verification_code)
        maybe_set_or_remove("crm_challenge_type", crm_challenge_type)
        maybe_set_or_remove("crm_challenge_attempts", crm_challenge_attempts)
        maybe_set_or_remove("crm_otp_hash", crm_otp_hash)
        maybe_set_or_remove("crm_otp_expires_at", crm_otp_expires_at)
        maybe_set_or_remove("crm_otp_attempts_left", crm_otp_attempts_left)
        maybe_set_or_remove("crm_otp_last_sent_at", crm_otp_last_sent_at)
        maybe_set_or_remove("crm_otp_email", crm_otp_email)
        maybe_set_or_remove("assigned_agent", assigned_agent)
        maybe_set_or_remove("crm_post_intent", crm_post_intent)
        maybe_set_or_remove("crm_post_slots", crm_post_slots)
        maybe_set_or_remove("crm_verification_blocked_until", crm_verification_blocked_until)

        if not set_parts and not remove_parts:
            return

        update_expr = "SET " + ", ".join(set_parts)
        if remove_parts:
            update_expr += " REMOVE " + ", ".join(remove_parts)

        self.table.update_item(
            Key=key,
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_vals,
        )

    def clear_crm_challenge(self, tenant_id: str, channel: str, channel_user_id: str) -> None:
        """
        Usuwa pola związane z challenge PG i post-intentem z rekordu rozmowy.
        """
        key = self.conversation_pk(tenant_id, channel, channel_user_id)
        self.table.update_item(
            Key=key,
            UpdateExpression=(
                "REMOVE crm_challenge_type, crm_challenge_attempts, crm_post_intent, crm_post_slots, crm_otp_hash, crm_otp_expires_at, crm_otp_attempts_left, crm_otp_last_sent_at, crm_otp_email"
            ),
        )
        
    def find_by_verification_code(self, tenant_id: str, verification_code: str) -> dict | None:
        resp = self.table.query(
            IndexName="tenant_verification_idx",
            KeyConditionExpression=Key("tenant_id").eq(tenant_id)
                                   & Key("verification_code").eq(verification_code),
            Limit=1,
        )
        items = resp.get("Items") or []
        return self._normalize_item(items[0]) if items else None
        
    def get(self, pk: str, sk: str):
        return self._normalize_item(self.table.get_item(Key={"pk": pk, "sk": sk}).get("Item"))

    def delete(self, pk: str, sk: str):
        self.table.delete_item(Key={"pk": pk, "sk": sk})

    def put(self, item: dict):
        self.table.put_item(Item=item)


        
    

