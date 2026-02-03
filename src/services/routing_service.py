"""
Główny serwis routujący wiadomości użytkowników.

Na podstawie wyniku NLU decyduje, czy:
- odpowiedzieć z FAQ,
- zaproponować rezerwację zajęć,
- przekazać sprawę do człowieka (handover),
- dopytać użytkownika (clarify).
"""

import time
import re
import logging
import os
import boto3
from datetime import datetime
from typing import List, Optional
from botocore.config import Config

from ..domain.models import Message, Action
from ..common.utils import build_reply_action
from ..common.config import settings
from ..common.timing import timed
from ..common.security import conversation_key
from ..services.nlu_service import NLUService
from ..services.kb_service import KBService
from ..services.template_service import TemplateService
from ..services.crm_service import CRMService
from .clients_factory import ClientsFactory
from .tenant_config_service import default_tenant_config_service
from ..services.ticketing_service import TicketingService
from ..services.metrics_service import MetricsService
from ..services.crm_flow_service import CRMFlowService
from ..services.language_service import LanguageService
from ..repos.conversations_repo import ConversationsRepo
from ..repos.tenants_repo import TenantsRepo
from ..repos.messages_repo import MessagesRepo
from ..repos.members_index_repo import MembersIndexRepo

from ..common.constants import (
    STATE_AWAITING_CONFIRMATION,
    STATE_AWAITING_CHALLENGE,
    STATE_AWAITING_CLASS_SELECTION,
    SESSION_TIMEOUT_SECONDS,
    STATE_AWAITING_MESSAGE,
)

logger = logging.getLogger(__name__)

COMPREHEND_REGION = os.getenv("COMPREHEND_REGION") or os.getenv("AWS_REGION") or "eu-central-1"

comprehend = boto3.client(
    "comprehend",
    region_name=COMPREHEND_REGION,
    config=Config(retries={"max_attempts": 2, "mode": "standard"}),
)

class RoutingService:
    """
    Serwis łączący NLU, KB i integracje zewnętrzne tak,
    by obsłużyć pełen flow rozmowy.
    """

    def __init__(
        self,
        nlu: NLUService | None = None,
        kb: KBService | None = None,
        tpl: TemplateService | None = None,
        metrics: MetricsService | None = None,
        conv: ConversationsRepo | None = None,
        tenants: TenantsRepo | None = None,
        messages: MessagesRepo | None = None,
        members_index: MembersIndexRepo | None = None,
        _clients_factory: ClientsFactory | None = None,
        crm: CRMService | None = None,
        ticketing: TicketingService | None = None,
        crm_flow: CRMFlowService | None = None, 
        language: LanguageService | None = None,
    ) -> None:
        self.nlu = nlu or NLUService()
        self.kb = kb or KBService()
        self.tpl = tpl or TemplateService()
        self.metrics = metrics or MetricsService()
        self.conv = conv or ConversationsRepo()
        self.tenants = tenants or TenantsRepo()
        self.messages = messages or MessagesRepo()
        self.members_index = members_index or MembersIndexRepo()
        self._clients_factory = ClientsFactory()
        self.crm = crm or CRMService(clients_factory=self._clients_factory)
        self.ticketing = ticketing or TicketingService(clients_factory=self._clients_factory)
        self.crm_flow = crm_flow or CRMFlowService(
            crm=self.crm,
            tpl=self.tpl,
            conv=self.conv,
            members_index=self.members_index,
        )
        self.language = language or LanguageService(conv=self.conv)
        # cache na słowa typu TAK / NIE z templatek
        self._words_cache: dict[tuple[str, str, str], set[str]] = {}

    # -------------------------------------------------------------------------
    #  Helpers ogólne
    # -------------------------------------------------------------------------

    def _reply(self, msg, lang, body, channel=None, channel_user_id=None):
        return build_reply_action(msg, lang, body, channel, channel_user_id)
   
    # -------------------------------------------------------------------------
    #  NLU + zapis intentu/stanu
    # -------------------------------------------------------------------------

    def _classify_intent(self, msg: Message, lang: str):
        """Opakowanie NLU + fallback na clarify."""
        if msg.intent:
            intent = msg.intent
            slots = msg.slots or {}
            confidence = 1.0
        else:
            nlu = self.nlu.classify_intent(msg.body, lang)
            if isinstance(nlu, dict):
                intent = nlu.get("intent", "clarify")
                slots = nlu.get("slots") or {}
                confidence = float(nlu.get("confidence", 1.0))
            else:
                intent = getattr(nlu, "intent", "clarify")
                slots = getattr(nlu, "slots", {}) or {}
                confidence = float(getattr(nlu, "confidence", 1.0))

        if intent not in ("clarify") and confidence < 0.3:
            intent = "clarify"

        return intent, slots, confidence

    def _update_conversation_state(
        self,
        msg: Message,
        lang: str,
        intent: str,
        slots: dict,
    ) -> None:
        """Ustawia last_intent + ewentualny stan maszyny."""
        sm_state = None
        if intent == "reserve_class":
            cid = (slots.get("class_id") or "").strip()
            if cid and cid.isdigit():
                sm_state = STATE_AWAITING_CONFIRMATION
            elif cid:
                sm_state = STATE_AWAITING_CLASS_SELECTION
        elif intent == "crm_available_classes":
            sm_state = STATE_AWAITING_CLASS_SELECTION

        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=msg.channel or "whatsapp",
            channel_user_id=msg.channel_user_id or msg.from_phone,
            last_intent=intent,
            state_machine_status=sm_state,
            language_code=lang,
        )

    # -------------------------------------------------------------------------
    #  Główna metoda
    # -------------------------------------------------------------------------

    def handle(self, msg: Message) -> List[Action]:
        """
        Przetwarza pojedynczą wiadomość biznesową i zwraca listę akcji do wykonania.
        """
        text_raw = (msg.body or "").strip()

        # 1) Język
        lang = self.language.resolve_and_persist_language(msg)

        # 2) Rozmowa + stan maszyny
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}
        
        state = conv.get("state_machine_status")

        now_ts = int(time.time())
        last_ts = int(conv.get("updated_at") or 0)
        gap = now_ts - last_ts if last_ts else 0
        is_new_session = last_ts == 0 or gap > SESSION_TIMEOUT_SECONDS

        # 3) Stany specjalne – bez NLU

        # 3a) Challenge PG na WhatsApp
        if state == STATE_AWAITING_CHALLENGE and channel == "whatsapp":
            return self.crm_flow.handle_crm_challenge(msg, conv, lang)

        # 3b) Użytkownik wybiera zajęcia z listy
        if state == STATE_AWAITING_CLASS_SELECTION:
            selection_response = self.crm_flow.handle_class_selection(msg, lang)
            if selection_response is not None:
                return selection_response

        # 3c) Pending rezerwacja – TAK/NIE
        pending_response = self.crm_flow.handle_pending_confirmation(msg, lang)
        if pending_response is not None:
            return pending_response

        # 3d) KOD:... z WhatsApp (powiązanie z WWW)
        code_response = self.crm_flow.handle_whatsapp_verification_code_linking(msg, lang)
        if code_response is not None:
            return code_response

        # 4) NLU – klasyfikacja intencji
        intent, slots, _ = self._classify_intent(msg, lang)
        
        # 4x) Fast-path intents (bez LLM/CRM/KB) – tylko szablony.
        #      Zero hardkodowania: treść kontroluje TemplatesRepo.
        if intent == "ack":
            tpl_name = "system_ack"
            body = self.tpl.render_named(msg.tenant_id, tpl_name, lang, {})
            if body == tpl_name:
                body = "OK"  # absolutny fallback
            self._update_conversation_state(msg, lang, intent, slots)
            return [self._reply(msg, lang, body)]

        # 4a) Kontekstowa poprawka: follow-up po FAQ
        # Jeśli poprzednia intencja była "faq", sesja jest ciągle ta sama,
        # a NLU zwróciło "clarify" (bo pytanie jest krótkie, typu "A w sobotę?"),
        # to traktujemy to jako FAQ z kontekstem.
        last_intent = conv.get("last_intent")
        if (
            not is_new_session
            and last_intent == "faq"
            and intent == "clarify"
        ):
            intent = "faq"
            # Slots zwykle i tak nie są potrzebne dla AI-FAQ,
            # więc nie musimy ich tu ruszać.
            
        # 5) Zapis intentu / stanu
        self._update_conversation_state(msg, lang, intent, slots)

        # 6) Routing po intencji
        # 6.1.a FAQ
        if intent == "faq":
            slots = slots or {}
            faq_key = (slots.get("faq_key") or "").strip()
            
            with timed("list_faq_keys", logger=logger, component="routing_service", extra={"tenant_id": msg.tenant_id}):
                if faq_key:
                    # lista kluczy z realnej bazy FAQ (S3/default), bez hardcode
                    if faq_key not in self.kb.list_faq_keys(msg.tenant_id, lang):
                        faq_key = ""
            if faq_key:
                with timed("answer_by_key", logger=logger, component="routing_service", extra={"tenant_id": msg.tenant_id}):
            
                    direct = self.kb.answer_by_key(
                        tenant_id=msg.tenant_id,
                        language_code=lang,
                        faq_key=faq_key,
                    )
                    if direct:
                        return [self._reply(msg, lang, direct)]

                body = self.tpl.render_named(msg.tenant_id, "faq_no_info", lang, {})
                return [self._reply(msg, lang, body)]
            
            conv_key = conversation_key(
                msg.tenant_id,
                msg.channel or "whatsapp",
                msg.channel_user_id or msg.from_phone,
                msg.conversation_id,
            )
            chat_history: list[dict] = []

            # historia potrzebna nam tylko jako fallback do answer_ai
            if not is_new_session and self.messages:
                try:
                    history_items = self.messages.get_last_messages(
                        tenant_id=msg.tenant_id,
                        conv_key=conv_key,
                        limit=10,
                    ) or []
                except Exception as e:
                    logger.error({
                        "sender": "routing",
                        "error": "get_last_messages_failed",
                        "err": str(e),
                    })
                    history_items = []
                else:
                    for item in reversed(history_items):
                        direction = item.get("direction")
                        body_item = item.get("body") or ""
                        if not body_item:
                            continue
                        if direction == "inbound":
                            chat_history.append(
                                {"role": "user", "content": body_item}
                            )
                        elif direction == "outbound":
                            chat_history.append(
                                {"role": "assistant", "content": body_item}
                            )
                    chat_history = chat_history[-6:]

            # 3) Fallback – jeśli NLU nie podało topic albo FAQ nie ma wpisu,
            #    używamy dotychczasowego AI-FAQ (answer_ai) z historią
            ai_body = self.kb.answer_ai(
                question=msg.body,
                tenant_id=msg.tenant_id,
                language_code=lang,
                history=chat_history,
            )

            if ai_body:
                body = ai_body
            else:
                # Deterministic fallback (no extra LLM calls).
                body = self.tpl.render_named(msg.tenant_id, "faq_no_info", lang, {})         
            return [self._reply(msg, lang, body)]

        # 6.2 Rezerwacja zajęć
        if intent == "reserve_class":
            class_id = (slots.get("class_id") or "").strip()

            # brak class_id → najpierw lista zajęć
            if not class_id:
                # tu ustawiamy stan ręcznie
                if not self.crm_flow.is_crm_member(msg.tenant_id, msg.from_phone):
                    self.conv.upsert_conversation(
                        tenant_id=msg.tenant_id,
                        channel=msg.channel or "whatsapp",
                        channel_user_id=msg.channel_user_id or msg.from_phone,
                        last_intent="crm_available_classes",
                        state_machine_status=STATE_AWAITING_MESSAGE,
                        language_code=lang,
                    )
                    return self.crm_flow.build_available_classes_response(
                        msg,
                        lang,
                        auto_confirm_single=False,
                        allow_selection=False,
                    )

                self.conv.upsert_conversation(
                    tenant_id=msg.tenant_id,
                    channel=msg.channel or "whatsapp",
                    channel_user_id=msg.channel_user_id or msg.from_phone,
                    last_intent=intent,
                    state_machine_status=STATE_AWAITING_CLASS_SELECTION,
                    language_code=lang,
                )
                return self.crm_flow.build_available_classes_response(msg, lang, auto_confirm_single=True)

            # class_id to nie ID tylko nazwa typu zajęć (np. 'pilates') → lista z filtrem
            if class_id and not class_id.isdigit():
                if not self.crm_flow.is_crm_member(msg.tenant_id, msg.from_phone):
                    self.conv.upsert_conversation(
                        tenant_id=msg.tenant_id,
                        channel=msg.channel or "whatsapp",
                        channel_user_id=msg.channel_user_id or msg.from_phone,
                        last_intent="crm_available_classes",
                        state_machine_status=STATE_AWAITING_MESSAGE,
                        language_code=lang,
                    )
                    return self.crm_flow.build_available_classes_response(
                        msg,
                        lang,
                        auto_confirm_single=False,
                        class_type_query=class_id,
                        allow_selection=False,
                    )
                self.conv.upsert_conversation(
                    tenant_id=msg.tenant_id,
                    channel=msg.channel or "whatsapp",
                    channel_user_id=msg.channel_user_id or msg.from_phone,
                    last_intent=intent,
                    state_machine_status=STATE_AWAITING_CLASS_SELECTION,
                    language_code=lang,
                )
                return self.crm_flow.build_available_classes_response(
                    msg,
                    lang,
                    auto_confirm_single=True,
                    class_type_query=class_id,
                )

            # mamy class_id → standardowy flow z weryfikacją PG i pending
            verify_resp = self.crm_flow.ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent="reserve_class",
                post_slots={"class_id": class_id},
            )
            if verify_resp:
                return verify_resp

            member_id = conv.get("crm_member_id")
            if not member_id:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_member_not_linked",
                    lang,
                    {},
                )
                return [self._reply(msg, lang, body)]

            return self.crm_flow.reserve_class_with_id_core(
                msg,
                lang,
                class_id=class_id,
                member_id=member_id,
            )

        # 6.3 Handover do człowieka
       # if intent == "handover":
       #     self.conv.assign_agent(
       #         tenant_id=msg.tenant_id,
       #         channel=msg.channel or "whatsapp",
       #         channel_user_id=msg.channel_user_id or msg.from_phone,
       #         agent_id=slots.get("agent_id", "UNKNOWN"),
       #     )
       #     body = self.tpl.render_named(
       #         msg.tenant_id,
       #         "handover_to_staff",
       #         lang,
       #         {},
       #     )
       #     return [self._reply(msg, lang, body)]

        # 6.4 Ticket do systemu ticketowego
        if intent == "ticket" or intent == "handover":
            conv_key = conversation_key(
                msg.tenant_id,
                msg.channel or "whatsapp",
                msg.channel_user_id or msg.from_phone,
                msg.conversation_id,
            )

            history_items: list[dict] = []
            if self.messages:
                try:
                    history_items = self.messages.get_last_messages(
                        tenant_id=msg.tenant_id,
                        conv_key=conv_key,
                        limit=10,
                    ) or []
                except Exception:
                    history_items = []

            history_lines = []
            for item in reversed(history_items):
                direction = item.get("direction", "?")
                body_item = item.get("body", "")
                history_lines.append(f"{direction}: {body_item}")

            history_block = (
                "\n".join(history_lines) if history_lines else "(brak historii)"
            )

            summary = slots.get("summary") or self.tpl.render_named(
                msg.tenant_id,
                "ticket_summary",
                lang,
                {},
            )

            description = (
                slots.get("description")
                or f"Request from chat.\n\Last message:\n{msg.body}\n\History:\n{history_block}"
            )

            meta = {
                "conversation_id": conv_key,
                "phone": msg.from_phone,
                "channel": msg.channel,
                "channel_user_id": msg.channel_user_id,
                "intent": intent,
                "slots": slots,
                "language_code": lang,
            }

            res = self.ticketing.create_ticket(
                tenant_id=msg.tenant_id,
                summary=summary,
                description=description,
                meta=meta,
            )

            ticket_id = None
            if isinstance(res, dict):
                ticket_id = res.get("ticket") or res.get("key")

            if ticket_id:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "ticket_created_ok",
                    lang,
                    {"ticket": ticket_id},
                )
            else:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "ticket_created_failed",
                    lang,
                    {},
                )

            return [self._reply(msg, lang, body)]

        # 6.5 Lista dostępnych zajęć (bez natychmiastowej rezerwacji)
        if intent == "crm_available_classes":
            return self.crm_flow.build_available_classes_response(msg, lang, auto_confirm_single=False)

        # 6.6 Status kontraktu
        if intent == "crm_contract_status":
            verify_resp = self.crm_flow.ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent="crm_contract_status",
                post_slots=slots,
            )
            if verify_resp:
                return verify_resp

            member_id = conv.get("crm_member_id")
            if not member_id:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_member_not_linked",
                    lang,
                    {},
                )
                return [self._reply(msg, lang, body)]

            return self.crm_flow.crm_contract_status_core(msg, lang, member_id)

        # 6.7 Saldo członkowskie
        if intent == "crm_member_balance":
            verify_resp = self.crm_flow.ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent="crm_member_balance",
                post_slots=slots,
            )
            if verify_resp:
                return verify_resp

            member_id = conv.get("crm_member_id")
            if not member_id:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "crm_member_not_linked",
                    lang,
                    {},
                )
                return [self._reply(msg, lang, body)]

            return self.crm_flow.crm_member_balance_core(msg, lang, member_id)
        
        # 6.8 Prośba o weryfikację
        if intent == "verification":
            verify_resp = self.crm_flow.ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent="crm_contract_status",
                post_slots=slots,
            )
            if verify_resp:
                return verify_resp
            return self.crm_flow.verification_active(msg, lang, member_id)

        # 6.9 Zgody marketingowe (opt-in / opt-out) – PG-only, z confirm na "TAK"
        if intent == "marketing_optout":
            self.crm_flow.set_pending_marketing_consent_change(
                msg, 
                "marketing_optout"
            )
            body = self.tpl.render_named(
                msg.tenant_id, 
                "system_marketing_optout_confirm", 
                lang, {}
            )
            return [self._reply(msg, lang, body)]

        if intent == "marketing_optin":
            self.crm_flow.set_pending_marketing_consent_change(
                msg, 
                "marketing_optin"
            )
            body = self.tpl.render_named(
                msg.tenant_id, 
                "system_marketing_optin_confirm", 
                lang, {}
            )
            return [self._reply(msg, lang, body)]
        
        # 6.10 Domyślny clarify
        body = self.tpl.render_named(
            msg.tenant_id,
            "clarify_generic",
            lang,
            {},
        )
        return [self._reply(msg, lang, body)]
