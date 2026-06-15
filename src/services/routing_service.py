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

from ..common.constants import (
    #STATES
    STATE_AWAITING_CONFIRMATION,
    STATE_AWAITING_CHALLENGE,
    STATE_AWAITING_CLASS_SELECTION,
    STATE_AWAITING_MESSAGE,
    STATE_AWAITING_TICKET_COMMENT,
    #INTENTS
    INTENT_RESERVE_CLASS,
    INTENT_FAQ,
    INTENT_HANDOVER,
    INTENT_VERIFICATION,
    INTENT_CLARIFY,
    INTENT_TICKET,
    INTENT_TICKET_STATUS,
    INTENT_AVAILABLE_CLASSES,
    INTENT_CONTRACT_STATUS,
    INTENT_CRM_MEMBER_BALANCE,
    INTENT_ACK,
    INTENT_MARKETING_OPTOUT,
    INTENT_MARKETING_OPTIN,
    #PARAMS
    DEFAULT_NLU_CONFIDENCE,
    DEFAULT_CHANNEL,
    SESSION_TIMEOUT_SECONDS,
    FAQ_AI_HISTORY_LIMIT,
    HISTORY_FETCH_LIMIT,
)

logger = logging.getLogger(__name__)

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
        self._clients_factory = _clients_factory or ClientsFactory()
        self.crm = crm or CRMService(clients_factory=self._clients_factory)
        self.ticketing = ticketing or TicketingService(clients_factory=self._clients_factory)
        self.crm_flow = crm_flow or CRMFlowService(
            crm=self.crm,
            tpl=self.tpl,
            conv=self.conv,
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
            confidence = DEFAULT_NLU_CONFIDENCE
        else:
            nlu = self.nlu.classify_intent(msg.body, lang)
            if isinstance(nlu, dict):
                intent = nlu.get("intent", INTENT_CLARIFY)
                slots = nlu.get("slots") or {}
                confidence = float(nlu.get("confidence", 1.0))
            else:
                intent = getattr(nlu, "intent", INTENT_CLARIFY)
                slots = getattr(nlu, "slots", {}) or {}
                confidence = float(getattr(nlu, "confidence", 1.0))
        nlu_min_confidence =  float(getattr(settings, "nlu_min_confidence", 0.3))
        if intent != INTENT_CLARIFY and confidence < nlu_min_confidence:
            intent = INTENT_CLARIFY

        return intent, slots, confidence

        
    def _upsert_conv(self, msg: Message, lang: str, last_intent: str, sm_state: str | None):
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=msg.channel or DEFAULT_CHANNEL,
            channel_user_id=msg.channel_user_id or msg.from_phone,
            last_intent=last_intent,
            state_machine_status=sm_state,
            language_code=lang,
        )
        
    def _update_conversation_state(
        self,
        msg: Message,
        lang: str,
        intent: str,
        slots: dict,
    ) -> None:
        """Ustawia last_intent + ewentualny stan maszyny."""
        sm_state = None
        if intent == INTENT_RESERVE_CLASS:
            cid = (slots.get("class_id") or "").strip()
            if cid and cid.isdigit():
                sm_state = STATE_AWAITING_CONFIRMATION
            elif cid:
                sm_state = STATE_AWAITING_CLASS_SELECTION
        elif intent == INTENT_AVAILABLE_CLASSES:
            sm_state = STATE_AWAITING_CLASS_SELECTION

        self._upsert_conv(msg, lang, intent, sm_state)

    def _conv_key(self, msg: Message) -> str:
        return conversation_key(
            msg.tenant_id,
            msg.channel or DEFAULT_CHANNEL,
            msg.channel_user_id or msg.from_phone,
            msg.conversation_id,
        )
        
    def _fetch_history_items(self, tenant_id: str, conv_key: str) -> list[dict]:  
        try:
            history_items = self.messages.get_last_messages(
                tenant_id=tenant_id,
                conv_key=conv_key,
                limit=HISTORY_FETCH_LIMIT,
            ) or []
        except Exception as e:
            history_items = []
        return history_items
        
    def _history_for_ticket_description(self, items) -> str:
        history_lines = []
        for item in reversed(items):
            direction = item.get("direction", "?")
            body_item = item.get("body", "")
            history_lines.append(f"{direction}: {body_item}")
        return "\n".join(history_lines)

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
        channel = msg.channel or DEFAULT_CHANNEL
        channel_user_id = msg.channel_user_id or msg.from_phone
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}
        
        state = conv.get("state_machine_status")

        now_ts = int(time.time())
        last_ts = int(conv.get("updated_at") or 0)
        gap = now_ts - last_ts if last_ts else 0
        is_new_session = last_ts == 0 or gap > SESSION_TIMEOUT_SECONDS

        # 3) Stany specjalne – bez NLU
        #3x) Ticket: czekamy na komentarz uzytkownika
        if state == STATE_AWAITING_TICKET_COMMENT:    
            conv_key = self._conv_key(msg)
      
            history_items: list[dict] = []
            if self.messages:
                history_items = self._fetch_history_items(msg.tenant_id, conv_key)

            history_block = self._history_for_ticket_description(history_items)
            
            res = self.ticketing.create_data_and_ticket(msg, lang, conv_key, history_block)
            
            self.conv.upsert_conversation(
                tenant_id=msg.tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
                language_code=lang,
            )
            ticket_id = None
            if isinstance(res, dict):
                ticket_id = res.get(INTENT_TICKET) or res.get("key")

            if ticket_id:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "ticket_created_ok",
                    lang,
                    {INTENT_TICKET: ticket_id},
                )
            else:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "ticket_created_failed",
                    lang,
                    {},
                )
            return [self._reply(msg, lang, body)]

        # 3a) Challenge PG na WhatsApp
        if state == STATE_AWAITING_CHALLENGE and channel == DEFAULT_CHANNEL:
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

        # 4) NLU – klasyfikacja intencji
        intent, slots, _ = self._classify_intent(msg, lang)
        
        # 4x) Fast-path intents (bez LLM/CRM/KB) – tylko szablony.
        #      Zero hardkodowania: treść kontroluje TemplatesRepo.
        if intent == INTENT_ACK:
            tpl_name = "ack_fallback_text"
            body = self.tpl.render_named(msg.tenant_id, tpl_name, lang, {})
            self._update_conversation_state(msg, lang, intent, slots)
            return [self._reply(msg, lang, body)]

        # 4a) Kontekstowa poprawka: follow-up po FAQ
        # Jeśli poprzednia intencja była INTENT_FAQ, sesja jest ciągle ta sama,
        # a NLU zwróciło INTENT_CLARIFY (bo pytanie jest krótkie, typu "A w sobotę?"),
        # to traktujemy to jako FAQ z kontekstem.
        last_intent = conv.get("last_intent")
        if (
            not is_new_session
            and last_intent == INTENT_FAQ
            and intent == INTENT_CLARIFY
        ):
            intent = INTENT_FAQ
            # Slots zwykle i tak nie są potrzebne dla AI-FAQ,
            # więc nie musimy ich tu ruszać.
            
        # 5) Zapis intentu / stanu
        self._update_conversation_state(msg, lang, intent, slots)

        # 6) Routing po intencji
        # 6.1.a FAQ
        if intent == INTENT_FAQ:
            conv_key = self._conv_key(msg)
            chat_history: list[dict] = []

            # historia potrzebna nam tylko jako fallback do answer_ai
            if not is_new_session and self.messages:

                history_items = self._fetch_history_items(msg.tenant_id, conv_key)
                for item in reversed(history_items):
                    if item.get("direction") != "inbound":
                        continue
                    body_item = (item.get("body") or "").strip()
                    if not body_item:
                        continue
                    chat_history.append({"role": "user", "content": body_item})
                chat_history = chat_history[-FAQ_AI_HISTORY_LIMIT:]

            # 3) Fallback – jeśli NLU nie podało topic albo FAQ nie ma wpisu,
            #    używamy dotychczasowego AI-FAQ (answer_ai) z historią
            ai_body = self.kb.answer_ai(
                question=msg.body,
                tenant_id=msg.tenant_id,
                language_code=lang,
                history=chat_history,
            )

            if ai_body:
                body = self.kb.normalize_ai_answer(ai_body)           
            else:
                # Deterministic fallback (no extra LLM calls).
                body = self.tpl.render_named(msg.tenant_id, "faq_no_info", lang, {})         
            return [self._reply(msg, lang, body)]

        # 6.2 Rezerwacja zajęć
        if intent == INTENT_RESERVE_CLASS:
            class_id = (slots.get("class_id") or "").strip()

            # brak class_id → najpierw lista zajęć
            if not class_id:
                # tu ustawiamy stan ręcznie
                if not self.crm_flow.is_crm_member(msg.tenant_id, msg.from_phone):
                    
                    self._upsert_conv(msg, lang, INTENT_AVAILABLE_CLASSES, STATE_AWAITING_MESSAGE)

                    return self.crm_flow.build_available_classes_response(
                        msg,
                        lang,
                        auto_confirm_single=False,
                        allow_selection=False,
                    )
                
                self._upsert_conv(msg, lang, intent, STATE_AWAITING_CLASS_SELECTION)

                return self.crm_flow.build_available_classes_response(msg, lang, auto_confirm_single=True)

            # class_id to nie ID tylko nazwa typu zajęć (np. 'pilates') → lista z filtrem
            if class_id and not class_id.isdigit():
                if not self.crm_flow.is_crm_member(msg.tenant_id, msg.from_phone):
                    self._upsert_conv(msg, lang, INTENT_AVAILABLE_CLASSES, STATE_AWAITING_MESSAGE)

                    return self.crm_flow.build_available_classes_response(
                        msg,
                        lang,
                        auto_confirm_single=False,
                        class_type_query=class_id,
                        allow_selection=False,
                    )
                self._upsert_conv(msg, lang, intent, STATE_AWAITING_CLASS_SELECTION)

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
                post_intent=INTENT_RESERVE_CLASS,
                post_slots={"class_id": class_id},
            )
            if verify_resp:
                return verify_resp

            member_id = self._require_member_id(msg, conv, lang)
            return self.crm_flow.reserve_class_with_id_core(
                msg,
                lang,
                class_id=class_id,
                member_id=member_id,
            )

        # 6.3a Handover do człowieka
       # if intent == INTENT_HANDOVER - tymczasowo pod ticketing
       
        #6.3b OPT-IN
        if intent == INTENT_MARKETING_OPTIN:
            self._upsert_conv(
                msg,
                lang,
                INTENT_MARKETING_OPTIN,
                STATE_AWAITING_TICKET_COMMENT,
            )

            body = self.tpl.render_named(
                msg.tenant_id,
                "ticket_more_info",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]
            
        # 6.4 Ticket do systemu ticketowego
        # handover, optin/optout - tymczasowo pod ticketing
        if intent in (
            INTENT_TICKET,
            INTENT_HANDOVER,
            INTENT_MARKETING_OPTOUT,
        ):
            verify_resp = self.crm_flow.ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent=INTENT_CRM_MEMBER_BALANCE,
                post_slots=slots,
            )
            if verify_resp:
                return verify_resp

            member_id = conv.get("crm_member_id")
            if member_id:
                self._upsert_conv(msg, lang, INTENT_HANDOVER, STATE_AWAITING_TICKET_COMMENT)
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "ticket_more_info",
                    lang,
                    {},
                )
                return [self._reply(msg, lang, body)]
            body = self.tpl.render_named(msg.tenant_id, "crm_member_not_linked", lang, {})
            return [self._reply(msg, lang, body)]
   
        # 6.5 Lista dostępnych zajęć (bez natychmiastowej rezerwacji)
        if intent == INTENT_AVAILABLE_CLASSES:
            if not self.crm_flow.is_crm_member(msg.tenant_id, msg.from_phone):
                self._upsert_conv(msg, lang, INTENT_AVAILABLE_CLASSES, STATE_AWAITING_MESSAGE)

                return self.crm_flow.build_available_classes_response(
                    msg,
                    lang,
                    auto_confirm_single=False,
                    allow_selection=False,
                )
            self._upsert_conv(msg, lang, intent, STATE_AWAITING_CLASS_SELECTION)

            return self.crm_flow.build_available_classes_response(
                msg,
                lang,
                auto_confirm_single=False,
            )

        # 6.6 Status kontraktu
        if intent == INTENT_CONTRACT_STATUS:
            verify_resp = self.crm_flow.ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent=INTENT_CONTRACT_STATUS,
                post_slots=slots,
            )
            if verify_resp:
                return verify_resp
            member_id = conv.get("crm_member_id")
            if member_id:
                return self.crm_flow.crm_contract_status_core(msg, lang, member_id)
            body = self.tpl.render_named(msg.tenant_id, "crm_member_not_linked", lang, {})
            return [self._reply(msg, lang, body)]

        # 6.7 Saldo członkowskie
        if intent == INTENT_CRM_MEMBER_BALANCE:
            verify_resp = self.crm_flow.ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent=INTENT_CRM_MEMBER_BALANCE,
                post_slots=slots,
            )
            if verify_resp:
                return verify_resp

            member_id = conv.get("crm_member_id")
            if member_id:
                return self.crm_flow.crm_member_balance_core(msg, lang, member_id)
            body = self.tpl.render_named(msg.tenant_id, "crm_member_not_linked", lang, {})
            return [self._reply(msg, lang, body)]
        
        # 6.8 Prośba o weryfikację
        if intent == INTENT_VERIFICATION:
            verify_resp = self.crm_flow.ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent=INTENT_CONTRACT_STATUS,
                post_slots=slots,
            )
            if verify_resp:
                return verify_resp
            member_id = conv.get("crm_member_id")
            if member_id:
                return self.crm_flow.verification_active(msg, lang, member_id)
            body = self.tpl.render_named(msg.tenant_id, "crm_member_not_linked", lang, {})
            return [self._reply(msg, lang, body)]
     
        # 6.10 Domyślny clarify
        body = self.tpl.render_named(
            msg.tenant_id,
            "clarify_generic",
            lang,
            {},
        )
        return [self._reply(msg, lang, body)]
