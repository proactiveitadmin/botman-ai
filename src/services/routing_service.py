"""
Główny serwis routujący wiadomości użytkowników.

Na podstawie wyniku NLU decyduje, czy:
- odpowiedzieć z FAQ,
- zaproponować rezerwację zajęć,
- przekazać sprawę do człowieka (handover),
- dopytać użytkownika (clarify).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from ..common.config import settings
from ..common.constants import (
    # STATES
    STATE_AWAITING_CHALLENGE,
    STATE_AWAITING_CLASS_SELECTION,
    STATE_AWAITING_CONFIRMATION,
    STATE_AWAITING_MESSAGE,
    STATE_AWAITING_TICKET_CONFIRMATION,
    STATE_AWAITING_TICKET_COMMENT,
    # INTENTS
    INTENT_ACK,
    INTENT_AVAILABLE_CLASSES,
    INTENT_CLARIFY,
    INTENT_CONTRACT_STATUS,
    INTENT_CRM_MEMBER_BALANCE,
    INTENT_FAQ,
    INTENT_HANDOVER,
    INTENT_MARKETING_OPTIN,
    INTENT_MARKETING_OPTOUT,
    INTENT_RESERVE_CLASS,
    INTENT_TICKET,
    INTENT_VERIFICATION,
    # PARAMS
    DEFAULT_CHANNEL,
    DEFAULT_NLU_CONFIDENCE,
    FAQ_AI_HISTORY_LIMIT,
    HISTORY_FETCH_LIMIT,
    SESSION_TIMEOUT_SECONDS,
    CRM_CONFIRM_WORDS,
    CRM_REJECT_WORDS,
)
from ..common.logging import logger
from ..common.logging_utils import mask_phone
from ..common.security import conversation_key
from ..common.utils import build_reply_action, new_id
from ..domain.models import Action, Message
from ..repos.conversations_repo import ConversationsRepo
from ..repos.messages_repo import MessagesRepo
from ..repos.tenants_repo import TenantsRepo
from ..services.crm_flow_service import CRMFlowService
from ..services.crm_service import CRMService
from ..services.kb_service import KBService
from ..services.language_service import LanguageService
from ..services.metrics_service import MetricsService
from ..services.nlu_service import NLUService
from ..services.template_service import TemplateService
from ..services.ticketing_service import TicketingService
from .clients_factory import ClientsFactory


TICKET_LIKE_INTENTS = frozenset(
    {
        INTENT_TICKET,
        INTENT_HANDOVER,
        INTENT_MARKETING_OPTOUT,
        INTENT_MARKETING_OPTIN,
    }
)


@dataclass(frozen=True)
class RoutingContext:
    """Dane wyliczone raz na początku obsługi wiadomości."""

    msg: Message
    safe_msg: Message
    lang: str
    channel: str
    channel_user_id: str
    conv: dict[str, Any]
    state: str | None
    intent: str
    slots: dict[str, Any]
    confidence: float
    sensitive_data: dict[str, Any]
    is_new_session: bool


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

    # ---------------------------------------------------------------------
    # API publiczne
    # ---------------------------------------------------------------------

    def handle(self, msg: Message) -> list[Action]:
        """Przetwarza pojedynczą wiadomość biznesową i zwraca akcje do wykonania."""
        ctx = self._build_context(msg)

        state_response = self._handle_stateful_flow(ctx)
        if state_response is not None:
            return state_response

        pending_response = self.crm_flow.handle_pending_confirmation(ctx.msg, ctx.lang)
        if pending_response is not None:
            return pending_response

        if ctx.intent == INTENT_ACK:
            return self._handle_ack(ctx)

        ctx = self._apply_contextual_faq_followup(ctx)
        self._update_conversation_state(ctx.msg, ctx.lang, ctx.intent, ctx.slots)

        return self._dispatch_intent(ctx)

    # ---------------------------------------------------------------------
    # Budowanie kontekstu wejściowego
    # ---------------------------------------------------------------------

    def _build_context(self, msg: Message) -> RoutingContext:
        lang = self.language.resolve_and_persist_language(msg)
        channel = msg.channel or DEFAULT_CHANNEL
        channel_user_id = msg.channel_user_id or msg.from_phone
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}

        intent, slots, confidence, sensitive_data, redacted_message = self._classify_intent(
            msg,
            lang,
        )
        safe_msg = replace(msg, body=redacted_message)
        self._log_message(msg, safe_msg.body, lang)

        return RoutingContext(
            msg=msg,
            safe_msg=safe_msg,
            lang=lang,
            channel=channel,
            channel_user_id=channel_user_id,
            conv=conv,
            state=conv.get("state_machine_status"),
            intent=intent,
            slots=slots,
            confidence=confidence,
            sensitive_data=sensitive_data,
            is_new_session=self._is_new_session(conv),
        )

    def _is_new_session(self, conv: dict[str, Any]) -> bool:
        last_ts = int(conv.get("updated_at") or 0)
        if last_ts == 0:
            return True
        return int(time.time()) - last_ts > SESSION_TIMEOUT_SECONDS

    # ---------------------------------------------------------------------
    # Helpers ogólne
    # ---------------------------------------------------------------------

    def _reply(
        self,
        msg: Message,
        lang: str,
        body: str,
        channel: str | None = None,
        channel_user_id: str | None = None,
    ) -> Action:
        return build_reply_action(msg, lang, body, channel, channel_user_id)

    def _template_reply(
        self,
        msg: Message,
        lang: str,
        template_name: str,
        params: dict[str, Any] | None = None,
    ) -> list[Action]:
        body = self.tpl.render_named(msg.tenant_id, template_name, lang, params or {})
        return [self._reply(msg, lang, body)]

    def _conv_key(self, msg: Message) -> str:
        return conversation_key(
            msg.tenant_id,
            msg.channel or DEFAULT_CHANNEL,
            msg.channel_user_id or msg.from_phone,
            msg.conversation_id,
        )

    def _member_not_linked_reply(self, ctx: RoutingContext) -> list[Action]:
        return self._template_reply(ctx.msg, ctx.lang, "crm_member_not_linked")

    # ---------------------------------------------------------------------
    # Logowanie i historia
    # ---------------------------------------------------------------------

    def _log_message(self, msg: Message, body_for_log: str, lang: str) -> None:
        """Loguje inbound. Błąd logowania nie może zatrzymać routingu."""
        try:
            self.messages.log_message(
                tenant_id=msg.tenant_id,
                conversation_id=self._conv_key(msg),
                msg_id=new_id("in-"),
                direction="inbound",
                body=body_for_log or "",
                from_phone=msg.from_phone,
                to_phone=msg.to_phone,
                channel=msg.channel or DEFAULT_CHANNEL,
                channel_user_id=msg.channel_user_id or msg.from_phone,
                language_code=lang,
            )
            logger.info(
                {
                    "component": "routing_service",
                    "event": "received",
                    "from": mask_phone(msg.from_phone),
                    "to": mask_phone(msg.to_phone),
                    "body": body_for_log,
                    "tenant_id": msg.tenant_id,
                    "channel": msg.channel or DEFAULT_CHANNEL,
                }
            )
        except Exception:
            logger.warning(
                {
                    "component": "routing_service",
                    "event": "message_log_failed",
                    "tenant_id": msg.tenant_id,
                }
            )

    def _fetch_history_items(self, tenant_id: str, conv_key: str) -> list[dict[str, Any]]:
        try:
            return self.messages.get_last_messages(
                tenant_id=tenant_id,
                conv_key=conv_key,
                limit=HISTORY_FETCH_LIMIT,
            ) or []
        except Exception:
            logger.warning(
                {
                    "component": "routing_service",
                    "event": "history_fetch_failed",
                    "tenant_id": tenant_id,
                }
            )
            return []

    @staticmethod
    def _history_for_ticket_description(items: list[dict[str, Any]]) -> str:
        return "\n".join(
            f'{item.get("direction", "?")}: {item.get("body", "")}'
            for item in reversed(items)
        )

    def _faq_chat_history(self, ctx: RoutingContext) -> list[dict[str, str]]:
        if ctx.is_new_session or not self.messages:
            return []

        history_items = self._fetch_history_items(ctx.msg.tenant_id, self._conv_key(ctx.msg))
        chat_history = [
            {"role": "user", "content": body}
            for item in reversed(history_items)
            if item.get("direction") == "inbound"
            for body in [(item.get("body") or "").strip()]
            if body
        ]
        return chat_history[-FAQ_AI_HISTORY_LIMIT:]

    # ---------------------------------------------------------------------
    # NLU + zapis intentu/stanu
    # ---------------------------------------------------------------------

    def _classify_intent(
        self,
        msg: Message,
        lang: str,
    ) -> tuple[str, dict[str, Any], float, dict[str, Any], str]:
        """
        Opakowanie NLU.

        Gdy `msg.intent` jest już ustawiony, używamy go jako źródła prawdy,
        ale nadal próbujemy wywołać NLU, żeby uzyskać redacted_message do logów.
        """
        fallback_sensitive_data = {"present": False, "categories": []}
        fallback_body = msg.body or ""

        if msg.intent:
            redacted_message = self._try_redact_message(msg, lang, fallback_body)
            return (
                msg.intent,
                msg.slots or {},
                DEFAULT_NLU_CONFIDENCE,
                fallback_sensitive_data,
                redacted_message,
            )

        try:
            nlu = self.nlu.classify_intent(msg.body, lang)
        except Exception:
            logger.warning(
                {
                    "component": "routing_service",
                    "event": "nlu_classification_failed",
                    "tenant_id": msg.tenant_id,
                }
            )
            return INTENT_CLARIFY, {}, 0.0, fallback_sensitive_data, fallback_body

        intent, slots, confidence, sensitive_data, redacted_message = self._parse_nlu_result(
            nlu,
            fallback_body=fallback_body,
            fallback_sensitive_data=fallback_sensitive_data,
        )
        if intent != INTENT_CLARIFY and confidence < self._nlu_min_confidence():
            intent = INTENT_CLARIFY

        return intent, slots, confidence, sensitive_data, redacted_message

    def _try_redact_message(self, msg: Message, lang: str, fallback_body: str) -> str:
        try:
            nlu = self.nlu.classify_intent(msg.body, lang)
            if isinstance(nlu, dict):
                return nlu.get("redacted_message") or fallback_body
            return getattr(nlu, "redacted_message", fallback_body) or fallback_body
        except Exception:
            logger.warning(
                {
                    "component": "routing_service",
                    "event": "redaction_failed",
                    "tenant_id": msg.tenant_id,
                }
            )
            return fallback_body

    @staticmethod
    def _parse_nlu_result(
        nlu: Any,
        fallback_body: str,
        fallback_sensitive_data: dict[str, Any],
    ) -> tuple[str, dict[str, Any], float, dict[str, Any], str]:
        if isinstance(nlu, dict):
            return (
                nlu.get("intent", INTENT_CLARIFY),
                nlu.get("slots") or {},
                float(nlu.get("confidence", 1.0)),
                nlu.get("sensitive_data") or fallback_sensitive_data,
                nlu.get("redacted_message") or fallback_body,
            )

        return (
            getattr(nlu, "intent", INTENT_CLARIFY),
            getattr(nlu, "slots", {}) or {},
            float(getattr(nlu, "confidence", 1.0)),
            getattr(nlu, "sensitive_data", fallback_sensitive_data) or fallback_sensitive_data,
            getattr(nlu, "redacted_message", fallback_body) or fallback_body,
        )

    @staticmethod
    def _nlu_min_confidence() -> float:
        return float(getattr(settings, "nlu_min_confidence", 0.3))

    def _upsert_conv(
        self,
        msg: Message,
        lang: str,
        last_intent: str,
        sm_state: str | None,
    ) -> None:
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
        slots: dict[str, Any],
    ) -> None:
        """Ustawia last_intent + ewentualny stan maszyny."""
        sm_state = self._state_for_intent(intent, slots)
        logger.info(
            {
                "component": "routing_service",
                "event": "update_conversation_state",
                "sm_state": sm_state,
            }
        )
        self._upsert_conv(msg, lang, intent, sm_state)

    @staticmethod
    def _state_for_intent(intent: str, slots: dict[str, Any]) -> str | None:
        if intent == INTENT_RESERVE_CLASS:
            class_id = (slots.get("class_id") or "").strip()
            if class_id.isdigit():
                return STATE_AWAITING_CONFIRMATION
            if class_id:
                return STATE_AWAITING_CLASS_SELECTION
        if intent == INTENT_AVAILABLE_CLASSES:
            return STATE_AWAITING_CLASS_SELECTION
        return None

    def _apply_contextual_faq_followup(self, ctx: RoutingContext) -> RoutingContext:
        if (
            not ctx.is_new_session
            and ctx.conv.get("last_intent") == INTENT_FAQ
            and ctx.intent == INTENT_CLARIFY
        ):
            return replace(ctx, intent=INTENT_FAQ)
        return ctx

    # ---------------------------------------------------------------------
    # Routing stanów rozmowy
    # ---------------------------------------------------------------------

    def _handle_stateful_flow(self, ctx: RoutingContext) -> list[Action] | None:
        if ctx.state == STATE_AWAITING_TICKET_CONFIRMATION:
            return self._handle_awaiting_ticket_confirmation(ctx)
            
        if ctx.state == STATE_AWAITING_TICKET_COMMENT:
            return self._handle_awaiting_ticket_comment(ctx)

        if ctx.state == STATE_AWAITING_CHALLENGE and ctx.channel == DEFAULT_CHANNEL:
            return self.crm_flow.handle_crm_challenge(ctx.msg, ctx.conv, ctx.lang)

        if ctx.state == STATE_AWAITING_CLASS_SELECTION:
            selection_response = self.crm_flow.handle_class_selection(ctx.msg, ctx.lang)
            if selection_response is not None:
                return selection_response
                
        return None

    def _handle_awaiting_ticket_confirmation(self, ctx: RoutingContext) -> list[Action] | None:
        text = (ctx.msg.body or "").strip().lower()

        confirm_words = self.crm_flow._get_words_set(
            ctx.msg.tenant_id,
            CRM_CONFIRM_WORDS,
            ctx.lang,
        )
        reject_words = self.crm_flow._get_words_set(
            ctx.msg.tenant_id,
            CRM_REJECT_WORDS,
            ctx.lang,
        )

        logger.info({
            "event": "ticket_confirmation_words_debug",
            "text": text,
            "reject_words": list(reject_words),
            "confirm_words": list(confirm_words),
        })
        if text in reject_words:
            self._upsert_conv(
                ctx.msg,
                ctx.lang,
                ctx.intent,
                STATE_AWAITING_MESSAGE,
            )
            return self._template_reply(ctx.msg, ctx.lang, "ticket_cancelled")

        if text in confirm_words:
            self._upsert_conv(
                ctx.msg,
                ctx.lang,
                ctx.intent,
                STATE_AWAITING_TICKET_COMMENT,
            )
            return self._template_reply(ctx.msg, ctx.lang, "ticket_more_info")

        return None
        
    def _handle_awaiting_ticket_comment(self, ctx: RoutingContext) -> list[Action]:
        conv_key = self._conv_key(ctx.msg)
        history_items = self._fetch_history_items(ctx.msg.tenant_id, conv_key) if self.messages else []
        history_block = self._history_for_ticket_description(history_items)

        result = self.ticketing.create_data_and_ticket(
            ctx.safe_msg,
            ctx.lang,
            conv_key,
            history_block,
        )
        self._upsert_conv(
            ctx.msg,
            ctx.lang,
            ctx.intent,
            STATE_AWAITING_MESSAGE,
        )

        ticket_id = self._ticket_id_from_result(result)
        if ticket_id:
            return self._template_reply(
                ctx.msg,
                ctx.lang,
                "ticket_created_ok",
                {INTENT_TICKET: ticket_id},
            )
        return self._template_reply(ctx.msg, ctx.lang, "ticket_created_failed")

    @staticmethod
    def _ticket_id_from_result(result: Any) -> str | None:
        if not isinstance(result, dict):
            return None
        return result.get(INTENT_TICKET) or result.get("key")

    # ---------------------------------------------------------------------
    # Routing intencji
    # ---------------------------------------------------------------------

    def _dispatch_intent(self, ctx: RoutingContext) -> list[Action]:
        if ctx.intent == INTENT_FAQ:
            return self._handle_faq(ctx)
        if ctx.intent == INTENT_RESERVE_CLASS:
            return self._handle_reserve_class(ctx)
        if ctx.intent in TICKET_LIKE_INTENTS:
            return self._handle_ticket_like(ctx)
        if ctx.intent == INTENT_AVAILABLE_CLASSES:
            return self._handle_available_classes(ctx)
        if ctx.intent == INTENT_CONTRACT_STATUS:
            return self._handle_contract_status(ctx)
        if ctx.intent == INTENT_CRM_MEMBER_BALANCE:
            return self._handle_member_balance(ctx)
        if ctx.intent == INTENT_VERIFICATION:
            return self._handle_verification(ctx)
        return self._template_reply(ctx.msg, ctx.lang, "clarify_generic")

    def _handle_ack(self, ctx: RoutingContext) -> list[Action]:
        self._update_conversation_state(ctx.msg, ctx.lang, ctx.intent, ctx.slots)
        return self._template_reply(ctx.msg, ctx.lang, "ack_fallback_text")

    def _handle_faq(self, ctx: RoutingContext) -> list[Action]:
        ai_body = self.kb.answer_ai(
            question=ctx.safe_msg.body,
            tenant_id=ctx.msg.tenant_id,
            language_code=ctx.lang,
            history=self._faq_chat_history(ctx),
        )
        body = (
            self.kb.normalize_ai_answer(ai_body)
            if ai_body
            else self.tpl.render_named(ctx.msg.tenant_id, "faq_no_info", ctx.lang, {})
        )
        return [self._reply(ctx.msg, ctx.lang, body)]

    def _handle_reserve_class(self, ctx: RoutingContext) -> list[Action]:
        class_id = (ctx.slots.get("class_id") or "").strip()

        if not class_id:
            return self._available_classes_response(
                ctx,
                member_last_intent=INTENT_RESERVE_CLASS,
                auto_confirm_single=True,
            )

        if not class_id.isdigit():
            return self._available_classes_response(
                ctx,
                member_last_intent=INTENT_RESERVE_CLASS,
                auto_confirm_single=True,
                class_type_query=class_id,
            )

        verify_resp = self.crm_flow.ensure_crm_verification(
            ctx.msg,
            ctx.conv,
            ctx.lang,
            post_intent=INTENT_RESERVE_CLASS,
            post_slots={"class_id": class_id},
        )
        if verify_resp:
            return verify_resp

        member_id = ctx.conv.get("crm_member_id")
        if not member_id:
            return self._member_not_linked_reply(ctx)

        return self.crm_flow.reserve_class_with_id_core(
            ctx.msg,
            ctx.lang,
            class_id=class_id,
            member_id=member_id,
        )

    def _handle_ticket_like(self, ctx: RoutingContext) -> list[Action]:
        self._upsert_conv(ctx.msg, ctx.lang, ctx.intent, STATE_AWAITING_TICKET_CONFIRMATION)
        return self._template_reply(ctx.msg, ctx.lang, "ticket_confirm_create")

    def _handle_available_classes(self, ctx: RoutingContext) -> list[Action]:
        return self._available_classes_response(
            ctx,
            member_last_intent=INTENT_AVAILABLE_CLASSES,
            auto_confirm_single=False,
        )

    def _available_classes_response(
        self,
        ctx: RoutingContext,
        *,
        member_last_intent: str,
        auto_confirm_single: bool,
        class_type_query: str | None = None,
    ) -> list[Action]:
        if not self.crm_flow.is_crm_member(ctx.msg.tenant_id, ctx.msg.from_phone):
            self._upsert_conv(ctx.msg, ctx.lang, INTENT_AVAILABLE_CLASSES, STATE_AWAITING_MESSAGE)
            return self.crm_flow.build_available_classes_response(
                ctx.msg,
                ctx.lang,
                auto_confirm_single=False,
                class_type_query=class_type_query,
                allow_selection=False,
            )

        self._upsert_conv(ctx.msg, ctx.lang, member_last_intent, STATE_AWAITING_CLASS_SELECTION)
        return self.crm_flow.build_available_classes_response(
            ctx.msg,
            ctx.lang,
            auto_confirm_single=auto_confirm_single,
            class_type_query=class_type_query,
        )

    def _handle_contract_status(self, ctx: RoutingContext) -> list[Action]:
        return self._handle_verified_member_action(
            ctx,
            post_intent=INTENT_CONTRACT_STATUS,
            action=lambda member_id: self.crm_flow.crm_contract_status_core(
                ctx.msg,
                ctx.lang,
                member_id,
            ),
        )

    def _handle_member_balance(self, ctx: RoutingContext) -> list[Action]:
        return self._handle_verified_member_action(
            ctx,
            post_intent=INTENT_CRM_MEMBER_BALANCE,
            action=lambda member_id: self.crm_flow.crm_member_balance_core(
                ctx.msg,
                ctx.lang,
                member_id,
            ),
        )

    def _handle_verification(self, ctx: RoutingContext) -> list[Action]:
        return self._handle_verified_member_action(
            ctx,
            post_intent=INTENT_CONTRACT_STATUS,
            action=lambda member_id: self.crm_flow.verification_active(
                ctx.msg,
                ctx.lang,
                member_id,
            ),
        )

    def _handle_verified_member_action(
        self,
        ctx: RoutingContext,
        *,
        post_intent: str,
        action: Callable[[str], list[Action]],
    ) -> list[Action]:
        verify_resp = self.crm_flow.ensure_crm_verification(
            ctx.msg,
            ctx.conv,
            ctx.lang,
            post_intent=post_intent,
            post_slots=ctx.slots,
        )
        if verify_resp:
            return verify_resp

        member_id = ctx.conv.get("crm_member_id")
        if not member_id:
            return self._member_not_linked_reply(ctx)

        return action(member_id)
