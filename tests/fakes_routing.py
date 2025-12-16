from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class InMemoryConversations:
    """Minimalny in-memory odpowiednik ConversationsRepo.

    Wspólny dla testów routingu/PG. Trzyma:
    - rozmowy w `data` pod kluczem (tenant_id, channel, channel_user_id)
    - itemy typu pending/classes w `pending` pod kluczem pk
    """

    def __init__(self):
        self.data: dict[tuple[str, str, str], dict] = {}
        self.pending: dict[str, dict] = {}
        self.cleared_calls: list[tuple[str, str, str]] = []
        self.verification_map: dict[str, dict] = {}

    def conversation_pk(self, tenant_id: str, channel: str, channel_user_id: str):
        return (tenant_id, channel, channel_user_id)

    def get_conversation(self, tenant_id: str, channel: str, channel_user_id: str):
        return self.data.get(self.conversation_pk(tenant_id, channel, channel_user_id))

    def upsert_conversation(self, tenant_id: str, channel: str, channel_user_id: str, **attrs):
        key = self.conversation_pk(tenant_id, channel, channel_user_id)
        conv = self.data.setdefault(key, {})
        conv.update(attrs)
        conv.setdefault("updated_at", int(time.time()))
        return conv

    # itemy (pending/classes)
    def get(self, pk: str, sk: str):
        # w testach ignorujemy sk – pk jest unikalny
        return self.pending.get(pk)

    def put(self, item: dict):
        pk = item.get("pk")
        if pk is None:
            return
        self.pending[pk] = dict(item)

    def delete(self, pk: str, sk: str | None = None):
        self.pending.pop(pk, None)

    def set_language(self, tenant_id: str, phone: str, new_lang: str):
        key = self.conversation_pk(tenant_id, "whatsapp", phone)
        conv = self.data.setdefault(key, {})
        conv["language_code"] = new_lang
        return conv

    def find_by_verification_code(self, tenant_id: str, verification_code: str):
        return self.verification_map.get(f"{tenant_id}:{verification_code}")

    def clear_crm_challenge(self, tenant_id: str, channel: str, channel_user_id: str):
        key = self.conversation_pk(tenant_id, channel, channel_user_id)
        conv = self.data.get(key, {})
        for field in ("crm_challenge_type", "crm_challenge_attempts", "crm_post_intent", "crm_post_slots", "crm_otp_hash", "crm_otp_expires_at", "crm_otp_attempts_left", "crm_otp_last_sent_at", "crm_otp_email"):
            conv.pop(field, None)
        self.cleared_calls.append((tenant_id, channel, channel_user_id))


class FakeTenantsRepo:
    def __init__(self, lang: str = "pl"):
        self.lang = lang

    def get(self, tenant_id: str):
        return {"tenant_id": tenant_id, "language_code": self.lang}


class FakeMembersIndex:
    def __init__(self, member_id: str = "999"):
        self.member_id = member_id
        self.calls: list[dict] = []

    def get_member(self, tenant_id: str, phone: str):
        self.calls.append({"tenant_id": tenant_id, "phone": phone})
        return {"id": self.member_id}


class FakeCRM:
    """Prosty fake CRM wykorzystywany w testach flow PG."""

    def __init__(self):
        self.reservations: list[dict] = []
        self.verify_calls: list[dict] = []
        self.available_classes_resp: dict = {
            "value": [
                {
                    "id": "CLASS-1",
                    "startDate": "2025-11-23T10:00:00+01:00",
                    "attendeesCount": 3,
                    "attendeesLimit": 10,
                    "classType": {"name": "Zumba"},
                }
            ]
        }

    def get_available_classes(
        self,
        tenant_id: str,
        club_id=None,
        from_iso=None,
        to_iso=None,
        member_id=None,
        fields=None,
        top=None,
    ):
        return self.available_classes_resp

    def reserve_class(self, tenant_id: str, member_id: str, class_id: str, idempotency_key: str, comments: str):
        self.reservations.append(
            {
                "tenant_id": tenant_id,
                "member_id": member_id,
                "class_id": class_id,
                "idem": idempotency_key,
                "comments": comments,
            }
        )
        return {"ok": True}

    def get_member_balance(self, tenant_id: str, member_id: int):
        return {"balance": 123.45}

    def get_contracts_by_email_and_phone(self, tenant_id: str, email: str, phone_number: str):
        return {"value": []}

    def verify_member_challenge(self, tenant_id: str, phone: str, challenge_type: str, answer: str) -> bool:
        self.verify_calls.append(
            {
                "tenant_id": tenant_id,
                "phone": phone,
                "challenge_type": challenge_type,
                "answer": answer,
            }
        )
        return True

    def get_member_by_phone(self, tenant_id: str, phone: str) -> dict:
        return {"value": []}


class FakeTemplateServicePG:
    """TemplateService fake – obsługuje szablony używane w testach flow PG."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def render_named(self, tenant_id: str, template_code: str, language_code: str, ctx: dict):
        self.calls.append({"tenant_id": tenant_id, "name": template_code, "lang": language_code, "ctx": ctx})

        # lista zajęć
        if template_code == "crm_available_classes_item":
            idx = ctx.get("index")
            date = ctx.get("date", "?")
            time_ = ctx.get("time", "?")
            name = ctx.get("name", "Zajęcia")
            capacity = ctx.get("capacity", "")
            return f"{idx}. {name} {date} {time_} {capacity}".strip()

        if template_code == "crm_available_classes":
            classes_block = ctx.get("classes", "")
            return "Dostępne zajęcia:\n" + classes_block if classes_block else "Brak dostępnych zajęć."
            return "Nieprawidłowy numer zajęć (max {max_index}).".format(**ctx)

        # rezerwacja
        if template_code == "reserve_class_confirm":
            return f"Czy potwierdzasz rezerwację zajęć {ctx.get('class_id')}?"

        if template_code == "reserve_class_confirmed":
            return ("Rezerwacja potwierdzona: {class_name} {class_date} {class_time}").format(**ctx)

        if template_code == "reserve_class_failed":
            return "Nie udało się zarezerwować zajęć."

        if template_code == "reserve_class_declined":
            return "Anulowano rezerwację."

        if template_code == "reserve_class_missing_id":
            return "Nie znam ID zajęć."

        # słowa TAK / NIE
        if template_code == "reserve_class_confirm_words":
            return "tak ok potwierdzam"

        if template_code == "reserve_class_decline_words":
            return "nie rezygnuję"

        # challenge / saldo
        if template_code == "crm_challenge_success":
            return "Weryfikacja zakończona sukcesem."

        if template_code == "crm_member_balance":
            return f"Twoje saldo to {ctx.get('balance')}."

        if template_code == "crm_member_not_linked":
            return "Nie znaleziono powiązanego członka PG."

        if template_code == "crm_challenge_retry":
            return f"Spróbuj ponownie, pozostało prób: {ctx.get('attempts_left')}."

        if template_code == "crm_challenge_fail_handover":
            return "Nie udało się potwierdzić tożsamości – przekazuję do pracownika."

        if template_code == "handover_to_staff":
            return "Łączę Cię z pracownikiem."

        return template_code


class FakeTemplateBasic:
    def render_named(self, tenant_id: str, template_name: str, lang: str | None, ctx: dict):
        if template_name == "clarify_generic":
            return "Czy możesz doprecyzować, w czym pomóc?"
        return f"{template_name}|{ctx}"
