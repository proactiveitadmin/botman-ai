from __future__ import annotations

import hmac
import re
import time
from datetime import datetime
from typing import Any

from ..common.constants import (
    # intents
    INTENT_AVAILABLE_CLASSES,
    INTENT_CONTRACT_STATUS,
    INTENT_CRM_MEMBER_BALANCE,
    INTENT_MARKETING_OPTIN,
    INTENT_MARKETING_OPTOUT,
    INTENT_RESERVE_CLASS,
    # states
    STATE_AWAITING_CHALLENGE,
    STATE_AWAITING_CONFIRMATION,
    STATE_AWAITING_MESSAGE,
    # params
    AVAILABLE_CLASSES_TOP,
    CLASS_INDEX_REGEX,
    CRM_OTP_RESEND_MIN_SECONDS,
    CRM_VERIFICATION_CODE_MINUTES,
    CRM_VERIFICATION_CODE_SECONDS,
    CRM_VERIFICATION_TTL_SECONDS,
    DATE_SLICE_END,
    DATE_SLICE_START,
    DEFAULT_CHANNEL,
    ENUM_CRM_RETURN_ALREADY_BOOKED,
    ENUM_CRM_RETURN_OK,
    DATE_TIME_REGEX,
    OTP_LENGTH,
    OTP_MAX_ATTEMPTS,
    TIME_SLICE_END,
    TIME_SLICE_START,
    WEB_CHANNEL,
    CRM_CONFIRM_WORDS,
    CRM_REJECT_WORDS,
    CRM_CONFIRMED,
    CRM_REJECTED,
    PENDING_CONFIRMATION_TTL_SECONDS,
)
from ..common.logging import logger
from ..common.security import otp_hash
from ..common.utils import build_reply_action, generate_verification_code, new_id
from ..adapters.email_client import EmailClient
from ..domain.models import Action, Message
from ..repos.conversations_repo import ConversationsRepo
from ..repos.tenants_repo import TenantsRepo
from ..services.crm_service import CRMService
from ..services.template_service import TemplateService
from .clients_factory import ClientsFactory


class CRMFlowService:
    """
    Logika CRM:
    - weryfikacja CRM / OTP,
    - status kontraktu i saldo,
    - lista zajęć, wybór zajęć i rezerwacja,
    - pending confirmations dla rezerwacji, płatności i zgód marketingowych.

    RoutingService powinien jedynie orkiestrwać wywołania tej klasy.
    """

    def __init__(
        self,
        crm: CRMService | None = None,
        _clients_factory: ClientsFactory | None = None,
        tpl: TemplateService | None = None,
        conv: ConversationsRepo | None = None,
        tenants: TenantsRepo | None = None,
        email_client: EmailClient | None = None,
    ) -> None:
        # Poprzednio parametr `_clients_factory` był ignorowany.
        self._clients_factory = _clients_factory or ClientsFactory()
        self.crm = crm or CRMService(clients_factory=self._clients_factory)
        self.tpl = tpl or TemplateService()
        self.conv = conv or ConversationsRepo()
        self.tenants = tenants or TenantsRepo()
        self.email_client = email_client or EmailClient()

        self._words_cache: dict[tuple[str, str, str], set[str]] = {}

    # ------------------------------------------------------------------ #
    # Ogólne helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _now_ts() -> int:
        return int(time.time())

    @staticmethod
    def _pending_key(phone: str) -> str:
        return f"pending#{phone}"

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _channel_ctx(self, msg: Message) -> tuple[str, str]:
        channel = msg.channel or DEFAULT_CHANNEL
        channel_user_id = msg.channel_user_id or msg.from_phone
        return channel, channel_user_id

    def _reply(
        self,
        msg: Message,
        lang: str,
        body: str,
        channel: str | None = None,
        channel_user_id: str | None = None,
    ) -> Action:
        return build_reply_action(msg, lang, body, channel, channel_user_id)

    def _reply_ctx(self, msg: Message, lang: str, body: str) -> Action:
        channel, channel_user_id = self._channel_ctx(msg)
        return self._reply(
            msg,
            lang,
            body,
            channel=channel,
            channel_user_id=channel_user_id,
        )

    def extract_date_time(text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Obsługuje formaty:
        - yyyy-mm-dd
        - dd.mm
        - dd-mm
        - dd.mm hh
        - dd.mm hh:mm
        - dd-mm hh
        - dd-mm hh:mm

        Zwraca:
        - date_str jako yyyy-mm-dd
        - time_str jako HH:MM albo None
        """

        match = DATE_TIME_REGEX.search(text)
        if not match:
            return None, None

        now = datetime.now()

        if match.group("iso_year"):
            year = int(match.group("iso_year"))
            month = int(match.group("iso_month"))
            day = int(match.group("iso_day"))
        else:
            year = now.year
            month = int(match.group("month"))
            day = int(match.group("day"))

        hour_raw = match.group("hour")
        minute_raw = match.group("minute")

        time_str = None

        if hour_raw is not None:
            hour = int(hour_raw)
            minute = int(minute_raw) if minute_raw is not None else 0

            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                return None, None

            time_str = f"{hour:02d}:{minute:02d}"

        try:
            date_str = datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None, None

        return date_str, time_str
    
    def _render(
        self,
        tenant_id: str,
        template_name: str,
        lang: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        return self.tpl.render_named(tenant_id, template_name, lang, context or {})

    def _reply_template(
        self,
        msg: Message,
        lang: str,
        template_name: str,
        context: dict[str, Any] | None = None,
    ) -> list[Action]:
        body = self._render(msg.tenant_id, template_name, lang, context)
        return [self._reply_ctx(msg, lang, body)]

    def _set_message_state(self, msg: Message, lang: str, **extra: Any) -> None:
        channel, channel_user_id = self._channel_ctx(msg)
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            state_machine_status=STATE_AWAITING_MESSAGE,
            language_code=lang,
            **extra,
        )

    def _set_confirmation_state(self, msg: Message, lang: str, intent: str) -> None:
        channel, channel_user_id = self._channel_ctx(msg)
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            last_intent=intent,
            state_machine_status=STATE_AWAITING_CONFIRMATION,
            language_code=lang,
        )

    def _put_pending(self, msg: Message, item: dict[str, Any]) -> None:
        self.conv.put(
            {
                "pk": self._pending_key(msg.from_phone),
                "sk": "pending",
                "created_at": item.get("created_at", self._now_ts()),
                "expires_at": item.get("expires_at", self._now_ts() + PENDING_CONFIRMATION_TTL_SECONDS),
                **item,
            }
        )

    def _delete_pending(self, msg: Message) -> None:
        self.conv.delete(self._pending_key(msg.from_phone), "pending")

    def _missing_member_reply(self, msg: Message, lang: str) -> list[Action]:
        return self._reply_template(msg, lang, "crm_member_not_linked")

    def _cancel_confirmation(self, msg: Message, lang: str) -> list[Action]:
        self._delete_pending(msg)
        return self._reply_template(msg, lang, "system_confirm_cancelled")

    def _get_words_set(
        self,
        tenant_id: str,
        template_name: str,
        lang: str | None = None,
    ) -> set[str]:
        """Wczytuje listę słów z templatek i cache'uje ją per tenant/template/lang."""
        key = (tenant_id, template_name, lang or "")
        if key in self._words_cache:
            return self._words_cache[key]

        raw = self._render(tenant_id, template_name, lang or "", {})
        words = {p.strip().lower() for p in re.split(r"[\s,;]+", raw or "") if p.strip()}
        self._words_cache[key] = words
        return words

    def _render_first(
        self,
        tenant_id: str,
        lang: str,
        template_names: list[str],
        context: dict[str, Any] | None = None,
    ) -> str | None:
        """Renderuje pierwszą dostępną templatkę z listy."""
        for name in template_names:
            try:
                body = self._render(tenant_id, name, lang, context)
            except Exception as exc:
                logger.error(
                    {
                        "sender": "crm_flow",
                        "event": "render_failed",
                        "template": name,
                        "details": str(exc),
                    }
                )
                continue
            if body:
                return body
        return None

    # ------------------------------------------------------------------ #
    # Helpers: klasy / zajęcia
    # ------------------------------------------------------------------ #

    @staticmethod
    def _start_parts(start: str, fallback: str | None = None) -> tuple[str | None, str | None]:
        fallback_value = fallback if fallback is not None else None
        date = start[DATE_SLICE_START:DATE_SLICE_END] if len(start) >= DATE_SLICE_END else fallback_value
        hour = start[TIME_SLICE_START:TIME_SLICE_END] if len(start) >= TIME_SLICE_END else fallback_value
        return date, hour

    @staticmethod
    def _class_type_name(item: dict[str, Any], default: str | None = None) -> str | None:
        class_type = item.get("classType") or {}
        if isinstance(class_type, dict):
            return class_type.get("name") or default
        return default

    def _safe_get_class_details(self, tenant_id: str, class_id: str) -> dict[str, Any]:
        try:
            return self.crm.get_class_by_id(tenant_id=tenant_id, class_id=class_id) or {}
        except Exception as exc:
            logger.warning(
                {
                    "component": "crm_flow_service",
                    "event": "get_class_by_id_failed",
                    "tenant_id": tenant_id,
                    "class_id": class_id,
                    "details": str(exc),
                }
            )
            return {}

    def _class_meta_from_details(
        self,
        details: dict[str, Any],
        class_id: str | None = None,
    ) -> dict[str, Any]:
        start = str(details.get("startDate") or details.get("startdate") or "")
        class_date, class_time = self._start_parts(start)
        return {
            "class_name": self._class_type_name(details, class_id),
            "class_date": class_date,
            "class_time": class_time,
        }

    def _selected_class_from_crm_item(self, item: dict[str, Any], index: int) -> dict[str, Any]:
        start = str(item.get("startDate") or item.get("startdate") or "")
        date, hour = self._start_parts(start, fallback="?")
        return {
            "index": index,
            "class_id": item.get("id"),
            "date": date,
            "time": hour,
            "name": self._class_type_name(item, "Class"),
            "start": start,
        }

    def _capacity_text(self, msg: Message, lang: str, class_item: dict[str, Any]) -> str:
        attendees_count = class_item.get("attendeesCount") or 0
        attendees_limit = class_item.get("attendeesLimit")

        if attendees_limit is None:
            return self._render(msg.tenant_id, "crm_available_classes_capacity_no_limit", lang)

        free = max(attendees_limit - attendees_count, 0)
        if free <= 0:
            return self._render(
                msg.tenant_id,
                "crm_available_classes_capacity_full",
                lang,
                {"limit": attendees_limit},
            )

        return self._render(
            msg.tenant_id,
            "crm_available_classes_capacity_free",
            lang,
            {"free": free, "limit": attendees_limit},
        )

    def _class_line(
        self,
        msg: Message,
        lang: str,
        selected: dict[str, Any],
        capacity: str = "",
    ) -> str:
        return self._render(
            msg.tenant_id,
            "crm_available_classes_item",
            lang,
            {
                "index": selected.get("index"),
                "date": selected.get("date"),
                "time": selected.get("time"),
                "name": selected.get("name"),
                "capacity": capacity,
            },
        )

    def _with_selection_hint(self, msg: Message, lang: str, body: str) -> str:
        try:
            extra = self._render(msg.tenant_id, "crm_available_classes_select_by_number", lang)
        except Exception:
            extra = ""
        return f"{body}\n\n{extra}" if extra else body

    # ------------------------------------------------------------------ #
    # Helpers: CRM verification / OTP
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_strong_verification_active(conv: dict[str, Any], now_ts: int) -> bool:
        crm_level = conv.get("crm_verification_level") or "none"
        crm_until = int(conv.get("crm_verified_until") or 0)
        return crm_level == "strong" and crm_until >= now_ts

    @staticmethod
    def _is_blocked(conv: dict[str, Any], now_ts: int) -> bool:
        blocked_until = int(conv.get("crm_verification_blocked_until") or 0)
        return bool(blocked_until and now_ts < blocked_until)

    def _clear_crm_challenge_state(self, tenant_id: str, channel: str, channel_user_id: str) -> None:
        try:
            self.conv.clear_crm_challenge(tenant_id, channel, channel_user_id)
        except AttributeError:
            # Fallback na starszą implementację repozytorium.
            pass

    def clear_crm_challenge_state(self, tenant_id: str, channel: str, channel_user_id: str) -> None:
        """Publiczny wrapper zachowany dla kompatybilności z istniejącymi wywołaniami."""
        self._clear_crm_challenge_state(tenant_id, channel, channel_user_id)

    def _reset_challenge_to_message_state(
        self,
        msg: Message,
        lang: str,
        *,
        clear_challenge: bool = True,
        **extra: Any,
    ) -> None:
        channel, channel_user_id = self._channel_ctx(msg)
        if clear_challenge:
            self._clear_crm_challenge_state(msg.tenant_id, channel, channel_user_id)
        self._set_message_state(msg, lang, **extra)

    def _challenge_blocked_reply(self, msg: Message, lang: str) -> list[Action]:
        self._reset_challenge_to_message_state(msg, lang)
        return self._reply_template(msg, lang, "crm_challenge_fail_handover")

    def _challenge_expired_reply(self, msg: Message, lang: str) -> list[Action]:
        self._reset_challenge_to_message_state(msg, lang)
        return self._reply_template(msg, lang, "crm_challenge_expired")

    def _block_verification(self, msg: Message, lang: str, now_ts: int) -> list[Action]:
        self._reset_challenge_to_message_state(
            msg,
            lang,
            crm_verification_blocked_until=now_ts + CRM_VERIFICATION_TTL_SECONDS,
        )
        return self._reply_template(msg, lang, "crm_challenge_fail_handover")

    def _send_otp_email(
        self,
        msg: Message,
        lang: str,
        email: str,
        verification_code: str,
    ) -> bool:
        body_email = self._render(
            msg.tenant_id,
            "crm_code_via_email",
            lang,
            {
                "verification_code": verification_code,
                "ttl_minutes": CRM_VERIFICATION_CODE_MINUTES,
            },
        )

        try:
            return bool(
                self.email_client.send_otp(
                    tenant_id=msg.tenant_id,
                    to_email=email,
                    subject="Verification code",
                    body_text=body_email,
                )
            )
        except Exception as exc:
            logger.warning(
                {
                    "component": "crm_flow_service",
                    "event": "send_otp_failed",
                    "tenant_id": msg.tenant_id,
                    "details": str(exc),
                }
            )
            return False

    def ensure_crm_verification(
        self,
        msg: Message,
        conv: dict[str, Any],
        lang: str,
        post_intent: str | None = None,
        post_slots: dict[str, Any] | None = None,
    ) -> list[Action] | None:
        """
        Zwraca None, jeśli można kontynuować operację CRM.
        Zwraca listę akcji, jeśli trzeba przerwać aktualny flow i obsłużyć verification/OTP.
        """
        now_ts = self._now_ts()
        channel, channel_user_id = self._channel_ctx(msg)

        if self._is_blocked(conv, now_ts):
            self._set_message_state(msg, lang)
            return self._reply_template(msg, lang, "crm_challenge_fail_handover")

        if self._is_strong_verification_active(conv, now_ts):
            return None

        if channel == WEB_CHANNEL:
            body = self._render(msg.tenant_id, "web_crm_not_available", lang)
            return [
                self._reply(
                    msg,
                    lang,
                    body,
                    channel=WEB_CHANNEL,
                    channel_user_id=channel_user_id,
                )
            ]

        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            crm_post_intent=post_intent,
            crm_post_slots=post_slots or {},
            language_code=lang,
        )

        email = self.crm.get_email_by_msg(msg.tenant_id, msg)
        if not email:
            self._set_message_state(msg, lang)
            return self._reply_template(msg, lang, "crm_challenge_missing_email")

        last_sent = int(conv.get("crm_otp_last_sent_at") or 0)
        if now_ts - last_sent < CRM_OTP_RESEND_MIN_SECONDS:
            return self._reply_template(msg, lang, "crm_challenge_email_code_already_sent")

        verification_code = generate_verification_code(length=OTP_LENGTH)
        if not self._send_otp_email(msg, lang, email, verification_code):
            self._set_message_state(msg, lang)
            return self._reply_template(msg, lang, "crm_challenge_fail_handover")

        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            crm_challenge_attempts=0,
            crm_otp_hash=otp_hash(msg.tenant_id, "crm_email_otp", verification_code),
            crm_otp_expires_at=now_ts + CRM_VERIFICATION_CODE_SECONDS,
            crm_otp_attempts_left=OTP_MAX_ATTEMPTS,
            crm_otp_last_sent_at=now_ts,
            crm_otp_email=email,
            state_machine_status=STATE_AWAITING_CHALLENGE,
            crm_post_intent=post_intent,
            crm_post_slots=post_slots or {},
            language_code=lang,
        )

        return self._reply_template(
            msg,
            lang,
            "crm_challenge_ask_email_code",
            {"email": email},
        )

    def handle_crm_challenge(
        self,
        msg: Message,
        conv: dict[str, Any],
        lang: str,
    ) -> list[Action]:
        """Obsługuje odpowiedź użytkownika na challenge OTP."""
        now_ts = self._now_ts()

        if self._is_blocked(conv, now_ts):
            return self._challenge_blocked_reply(msg, lang)

        expected_hash = (conv.get("crm_otp_hash") or "").strip()
        if not expected_hash:
            return self._challenge_expired_reply(msg, lang)

        expires_at = int(conv.get("crm_otp_expires_at") or 0)
        if now_ts > expires_at:
            return self._challenge_expired_reply(msg, lang)

        attempts_left = int(conv.get("crm_otp_attempts_left") or 0)
        if attempts_left <= 0:
            return self._block_verification(msg, lang, now_ts)

        normalized_code = (msg.body or "").strip().upper()
        given_hash = otp_hash(msg.tenant_id, "crm_email_otp", normalized_code)
        if not hmac.compare_digest(expected_hash, given_hash):
            return self._handle_invalid_otp(msg, lang, attempts_left, now_ts)

        return self._finalize_crm_verification_success(msg, conv, lang)

    def _handle_invalid_otp(
        self,
        msg: Message,
        lang: str,
        attempts_left: int,
        now_ts: int,
    ) -> list[Action]:
        attempts_left = max(attempts_left - 1, 0)
        channel, channel_user_id = self._channel_ctx(msg)
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            crm_otp_attempts_left=attempts_left,
            language_code=lang,
        )

        if attempts_left <= 0:
            return self._block_verification(msg, lang, now_ts)

        return self._reply_template(
            msg,
            lang,
            "crm_challenge_retry",
            {"attempts_left": attempts_left},
        )

    def _finalize_crm_verification_success(
        self,
        msg: Message,
        conv: dict[str, Any],
        lang: str,
    ) -> list[Action]:
        """Wspólna ścieżka po pozytywnej weryfikacji OTP + dokończenie post_intent."""
        now_ts = self._now_ts()
        channel, channel_user_id = self._channel_ctx(msg)
        post_intent = conv.get("crm_post_intent")
        post_slots = conv.get("crm_post_slots") or {}

        member_id = self.crm.get_member_id_by_msg(msg.tenant_id, msg)
        if not member_id:
            logger.warning(
                {
                    "component": "crm_flow_service",
                    "event": "finalize_crm_verification_success_no_member_id",
                    "tenant_id": msg.tenant_id,
                }
            )
            member_id = None

        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            state_machine_status=STATE_AWAITING_MESSAGE,
            crm_member_id=member_id,
            crm_verification_level="strong",
            crm_verified_until=now_ts + CRM_VERIFICATION_TTL_SECONDS,
            crm_verification_blocked_until=None,
            language_code=lang,
        )
        self._clear_crm_challenge_state(msg.tenant_id, channel, channel_user_id)

        actions = self._reply_template(msg, lang, "crm_challenge_success")
        actions.extend(self._resume_post_verification_intent(msg, lang, post_intent, post_slots, member_id))
        return actions

    def _resume_post_verification_intent(
        self,
        msg: Message,
        lang: str,
        post_intent: str | None,
        post_slots: dict[str, Any],
        member_id: str | None,
    ) -> list[Action]:
        if post_intent == INTENT_CRM_MEMBER_BALANCE:
            return self.crm_member_balance_core(msg, lang, member_id) if member_id else self._missing_member_reply(msg, lang)

        if post_intent == INTENT_CONTRACT_STATUS:
            return self.crm_contract_status_core(msg, lang, member_id) if member_id else self._missing_member_reply(msg, lang)

        if post_intent == INTENT_RESERVE_CLASS:
            class_id = (post_slots or {}).get("class_id")
            if member_id and class_id:
                return self.reserve_class_with_id_core(msg, lang, class_id, member_id)
            return self._missing_member_reply(msg, lang)

        # Zachowujemy dotychczasowe zachowanie dla innych post_intentów: verification kończy się sukcesem,
        # a pozostały flow może zostać obsłużony przez routing/pending przy następnej wiadomości.
        return []

    # ------------------------------------------------------------------ #
    # Flow: saldo / kontrakt / płatności
    # ------------------------------------------------------------------ #

    def _get_payment_url(
        self,
        tenant_id: str,
        member_id: str,
        club_id: str,
        lang: str,
    ) -> str:
        tenant = self.tenants.get(tenant_id) or {}
        return_url = tenant.get("return_url") or None

        try:
            response = self.crm.get_debt_payment_link(
                tenant_id=tenant_id,
                member_id=member_id,
                club_id=club_id,
                return_url=return_url,
            ) or {}
        except Exception as exc:
            logger.warning(
                {
                    "component": "crm_flow_service",
                    "event": "payment_link_generation_failed",
                    "tenant_id": tenant_id,
                    "details": str(exc),
                }
            )
            response = {}

        if response.get("ok") is True and response.get("url"):
            return self._render(
                tenant_id,
                "payment_link_generated",
                lang,
                {"url": response["url"]},
            )

        return self._render(tenant_id, "payment_link_generation_failed", lang)

    def _put_payment_pending(
        self,
        msg: Message,
        lang: str,
        *,
        intent: str,
        member_id: str,
        club_id: str | int | None,
    ) -> None:
        self._put_pending(
            msg,
            {
                "kind": intent,
                "created_at": self._now_ts(),
                "expires_at": (self._now_ts() + PENDING_CONFIRMATION_TTL_SECONDS),
                "member_id": member_id,
                "club_id": club_id,
            },
        )
        self._set_confirmation_state(msg, lang, intent)

    def get_contract_status_context(self, msg: Message, member_id: str, lang: str) -> dict[str, Any]:
        contract = self.crm.get_contract_by_member_id(
            tenant_id=msg.tenant_id,
            member_id=member_id,
        ) or {}

        payment_plan = self.crm.get_paymentplan_by_member_id(
            tenant_id=msg.tenant_id,
            member_id=member_id,
        ) or {}

        balance_resp = self.crm.get_member_balance(
            tenant_id=msg.tenant_id,
            member_id=int(member_id) if str(member_id).isdigit() else member_id,
        ) or {}

        negative_raw = balance_resp.get("negativeBalanceSince")
        context = {
            "plan_name": payment_plan.get("name") or "",
            "club_id": balance_resp.get("club_id"),
            "status": contract.get("status") or "Unknown",
            "start_date": (contract.get("startDate") or "")[DATE_SLICE_START:DATE_SLICE_END],
            "end_date": (contract.get("endDate") or "")[DATE_SLICE_START:DATE_SLICE_END] or "",
            "current_balance": balance_resp.get("currentBalance"),
            "negative_balance_since": negative_raw[DATE_SLICE_START:DATE_SLICE_END] if negative_raw else "",
        }
        logger.info({"component": "crm_flow_service", "event": "contract_status_context", **context})
        return context

    def crm_member_balance_core(self, msg: Message, lang: str, member_id: str | None) -> list[Action]:
        if not member_id:
            return self._missing_member_reply(msg, lang)

        balance_resp = self.crm.get_member_balance(
            tenant_id=msg.tenant_id,
            member_id=member_id,
        ) or {}
        club_id = balance_resp.get("club_id", 0)
        current_balance = balance_resp.get("currentBalance", 0)

        if current_balance is not None and self._safe_float(current_balance) < 0:
            self._put_payment_pending(
                msg,
                lang,
                intent=INTENT_CRM_MEMBER_BALANCE,
                member_id=member_id,
                club_id=club_id,
            )
            return self._reply_template(
                msg,
                lang,
                "crm_member_balance_negative",
                {"current_balance": current_balance},
            )

        return self._reply_template(
            msg,
            lang,
            "crm_member_balance",
            {"current_balance": current_balance},
        )

    def crm_contract_status_core(self, msg: Message, lang: str, member_id: str | None) -> list[Action]:
        if not member_id:
            return self._missing_member_reply(msg, lang)

        context = self.get_contract_status_context(msg, member_id, lang)
        current_balance = context.get("current_balance")

        if current_balance is not None and self._safe_float(current_balance) < 0:
            self._put_payment_pending(
                msg,
                lang,
                intent=INTENT_CONTRACT_STATUS,
                member_id=member_id,
                club_id=context.get("club_id"),
            )
            return self._reply_template(msg, lang, "crm_contract_negative_balance", context)

        return self._reply_template(msg, lang, "crm_contract_details", context)

    def is_crm_member(self, tenant_id: str, phone: str) -> bool:
        member_type = self.crm.get_member_type_by_phone(tenant_id, phone)
        return bool(member_type) and member_type.lower() == "member"

    # ------------------------------------------------------------------ #
    # Flow: zajęcia / rezerwacje
    # ------------------------------------------------------------------ #

    def reserve_class_with_id_core(
        self,
        msg: Message,
        lang: str,
        class_id: str,
        member_id: str,
        class_meta: dict[str, Any] | None = None,
    ) -> list[Action]:
        """Tworzy pending rezerwację i wysyła prośbę o potwierdzenie."""
        if class_meta is None:
            details = self._safe_get_class_details(msg.tenant_id, class_id)
            class_meta = self._class_meta_from_details(details, class_id)

        item = {
            "kind": INTENT_RESERVE_CLASS,
            "class_id": class_id,
            "member_id": member_id,
            "idempotency_key": new_id("idem-"),
            **(class_meta or {}),
        }
        self._put_pending(msg, item)
        self._set_confirmation_state(msg, lang, INTENT_RESERVE_CLASS)

        return self._reply_template(
            msg,
            lang,
            "reserve_class_confirm",
            {
                "class_id": class_id,
                "class_name": item.get("class_name") or class_id,
                "class_date": item.get("class_date"),
                "class_time": item.get("class_time"),
            },
        )

    def build_available_classes_response(
        self,
        msg: Message,
        lang: str,
        *,
        auto_confirm_single: bool = False,
        class_type_query: str | None = None,
        allow_selection: bool = True,
    ) -> list[Action]:
        classes_resp = self.crm.get_available_classes(
            tenant_id=msg.tenant_id,
            top=AVAILABLE_CLASSES_TOP,
            class_type_query=class_type_query,
        ) or {}
        classes = classes_resp.get("value") or []

        if not classes:
            return self._reply_template(msg, lang, "crm_available_classes_empty")

        if not allow_selection:
            auto_confirm_single = False

        if auto_confirm_single and len(classes) == 1:
            try:
                self.conv.delete(self._pending_key(msg.from_phone), "classes")
            except Exception:
                pass
            selected = self._selected_class_from_crm_item(classes[0] or {}, index=1)
            return self._start_reservation_from_selection(msg, lang, selected)

        lines: list[str] = []
        simplified: list[dict[str, Any]] = []
        for index, class_item in enumerate(classes, start=1):
            selected = self._selected_class_from_crm_item(class_item or {}, index=index)
            lines.append(
                self._class_line(
                    msg,
                    lang,
                    selected,
                    capacity=self._capacity_text(msg, lang, class_item or {}),
                )
            )
            simplified.append(selected)

        body = self._render(
            msg.tenant_id,
            INTENT_AVAILABLE_CLASSES,
            lang,
            {"classes": "\n".join(lines)},
        )

        if not allow_selection:
            return [self._reply_ctx(msg, lang, body)]

        self.conv.put(
            {
                "pk": self._pending_key(msg.from_phone),
                "sk": "classes",
                "items": simplified,
            }
        )
        return [self._reply_ctx(msg, lang, self._with_selection_hint(msg, lang, body))]

    def handle_class_selection(self, msg: Message, lang: str) -> list[Action] | None:
        text = (msg.body or "").strip().lower()
        classes_item = self.conv.get(self._pending_key(msg.from_phone), "classes")
        items = (classes_item or {}).get("items") or []
        if not items:
            return None

        if actions := self._handle_class_selection_by_index(msg, lang, text, items):
            return actions

        if actions := self._handle_class_selection_today(msg, lang, text, items):
            return actions

        if actions := self._handle_class_selection_by_date(msg, lang, text, items):
            return actions

        return None

    def _handle_class_selection_by_index_or_date(
        self,
        msg: Message,
        lang: str,
        text: str,
        items: list[dict[str, Any]],
    ) -> list[Action] | None:
        match = re.search(CLASS_INDEX_REGEX, text)
        if match:
            index = int(match.group(1))
            selected = next((item for item in items if item.get("index") == index), None)
            if selected:
                return self._start_reservation_from_selection(msg, lang, selected)
 
        date_str, time_str = extract_date_time(text)

        if date_str:
            same_day = [item for item in items if item.get("date") == date_str]

            if time_str:
                same_day = [
                    item for item in same_day
                    if item.get("time") == time_str
                    or item.get("start_time") == time_str
                    or str(item.get("datetime", "")).endswith(time_str)
                ]

            if not same_day:
                return self._reply_template(
                    msg,
                    lang,
                    "crm_available_classes_no_classes_on_date",
                    {"date": date_str},
                )

            if len(same_day) == 1:
                return self._start_reservation_from_selection(msg, lang, same_day[0])

            body = self._render_class_subset(msg, lang, "crm_available_classes_today", same_day)
            return [self._reply_ctx(msg, lang, self._with_selection_hint(msg, lang, body))]
        return None
        
    def _handle_class_selection_today(
        self,
        msg: Message,
        lang: str,
        text: str,
        items: list[dict[str, Any]],
    ) -> list[Action] | None:
        today_words = self._get_words_set(msg.tenant_id, "today_words", lang)
        if not any(word in text for word in today_words):
            return None

        today = datetime.now().date().isoformat()
        todays = [item for item in items if item.get("date") == today]
        if not todays:
            return self._reply_template(msg, lang, "crm_available_classes_no_today")

        if len(todays) == 1:
            return self._start_reservation_from_selection(msg, lang, todays[0])

        body = self._render_class_subset(msg, lang, "crm_available_classes_today", todays)
        return [self._reply_ctx(msg, lang, body)]

    def _render_class_subset(
        self,
        msg: Message,
        lang: str,
        template_name: str,
        items: list[dict[str, Any]],
    ) -> str:
        lines = [self._class_line(msg, lang, item) for item in items]
        return self._render(
            msg.tenant_id,
            template_name,
            lang,
            {"classes": "\n".join(lines)},
        )

    def _start_reservation_from_selection(
        self,
        msg: Message,
        lang: str,
        selected: dict[str, Any],
    ) -> list[Action]:
        class_id = selected.get("class_id")
        if not class_id:
            return self._reply_template(msg, lang, "reserve_class_missing_id")

        channel, channel_user_id = self._channel_ctx(msg)
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}

        verify_resp = self.ensure_crm_verification(
            msg,
            conv,
            lang,
            post_intent=INTENT_RESERVE_CLASS,
            post_slots={"class_id": class_id},
        )
        if verify_resp:
            return verify_resp

        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}
        member_id = conv.get("crm_member_id")
        if not member_id:
            return self._missing_member_reply(msg, lang)

        return self.reserve_class_with_id_core(
            msg,
            lang,
            class_id=class_id,
            member_id=member_id,
            class_meta={
                "class_name": selected.get("name"),
                "class_date": selected.get("date"),
                "class_time": selected.get("time"),
            },
        )

    # ------------------------------------------------------------------ #
    # Flow: pending confirmations
    # ------------------------------------------------------------------ #

    def set_pending_marketing_consent_change(self, msg: Message, kind: str, member_id: str) -> None:
        self._put_pending(
            msg,
            {
                "kind": kind,
                "created_at": self._now_ts(),
                "expires_at": (self._now_ts() + PENDING_CONFIRMATION_TTL_SECONDS),
                "member_id": member_id,
            },
        )
        
    def _confirmation_decision(self, msg: Message, lang: str) -> str | None:
        text = (msg.body or "").strip().lower()

        confirm_words = self._get_words_set(msg.tenant_id, CRM_CONFIRM_WORDS, lang)
        reject_words = self._get_words_set(msg.tenant_id, CRM_REJECT_WORDS, lang)

        if text in confirm_words:
            return CRM_CONFIRMED
        if text in reject_words:
            return CRM_REJECTED
        return None
        
    def handle_pending_confirmation(self, msg: Message, lang: str) -> list[Action] | None:

        pending = self.conv.get(self._pending_key(msg.from_phone), "pending")
        if not pending:
            return None
       
        expires_at = pending.get("expires_at")
        if expires_at is not None and self._now_ts() > int(expires_at):
            self._delete_pending(msg)
            self._set_message_state(msg, lang)
            return None
            
        decision = self._confirmation_decision(msg, lang)

        if decision is None:
            return None

        is_confirmed = decision == CRM_CONFIRMED
        pending_kind = (pending.get("kind") or "").strip()

        if pending_kind in (INTENT_MARKETING_OPTOUT, INTENT_MARKETING_OPTIN):
            return self._handle_pending_marketing(msg, lang, pending, pending_kind, is_confirmed)

        if pending_kind in (INTENT_CONTRACT_STATUS, INTENT_CRM_MEMBER_BALANCE):
            return self._handle_pending_payment(msg, lang, pending, is_confirmed)

        if pending_kind == INTENT_RESERVE_CLASS:
            return self._handle_pending_reservation(msg, lang, pending, is_confirmed)

        return []

    def _handle_pending_marketing(
        self,
        msg: Message,
        lang: str,
        pending: dict[str, Any],
        pending_kind: str,
        is_confirmed: bool,
    ) -> list[Action]:
        if not is_confirmed:
            return self._cancel_confirmation(msg, lang)

        member_id = pending.get("member_id")
        if pending_kind == INTENT_MARKETING_OPTOUT:
            verification_actions = self._ensure_marketing_optout_verified(msg, lang, pending)
            if verification_actions:
                return verification_actions
            member_id = member_id or self._current_crm_member_id(msg)
            if not member_id:
                self._delete_pending(msg)
                return self._reply_template(msg, lang, "system_marketing_change_failed")

        try:
            if pending_kind == INTENT_MARKETING_OPTOUT:
                self.crm.revoke_marketing_consent_for_member(
                    tenant_id=msg.tenant_id,
                    member_id=member_id,
                    reason="text_command_confirmed",
                )
                template_name = "system_marketing_optout_done"
            else:
                self.crm.grant_marketing_consent(
                    tenant_id=msg.tenant_id,
                    reason="text_command_confirmed",
                )
                template_name = "system_marketing_optin_done"

            self._delete_pending(msg)
            return self._reply_template(msg, lang, template_name)

        except NotImplementedError:
            logger.warning(
                {
                    "component": "crm_flow_service",
                    "tenant_id": msg.tenant_id,
                    "event": "marketing_consent_not_implemented",
                }
            )
        except Exception as exc:
            logger.warning(
                {
                    "component": "crm_flow_service",
                    "tenant_id": msg.tenant_id,
                    "event": "marketing_consent_change_failed",
                    "details": str(exc),
                }
            )

        self._delete_pending(msg)
        return self._reply_template(msg, lang, "system_marketing_change_failed")

    def _ensure_marketing_optout_verified(
        self,
        msg: Message,
        lang: str,
        pending: dict[str, Any],
    ) -> list[Action] | None:
        channel, channel_user_id = self._channel_ctx(msg)
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}
        return self.ensure_crm_verification(
            msg,
            conv,
            lang,
            post_intent=pending.get("kind"),
            post_slots={},
        )

    def _current_crm_member_id(self, msg: Message) -> str | None:
        channel, channel_user_id = self._channel_ctx(msg)
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}
        return conv.get("crm_member_id")

    def _handle_pending_payment(
        self,
        msg: Message,
        lang: str,
        pending: dict[str, Any],
        is_confirmed: bool,
    ) -> list[Action]:
        if not is_confirmed:
            return self._cancel_confirmation(msg, lang)

        member_id = pending.get("member_id")
        club_id = pending.get("club_id")
        self._delete_pending(msg)

        body = self._get_payment_url(
            tenant_id=msg.tenant_id,
            member_id=member_id,
            club_id=club_id,
            lang=lang,
        )
        return [self._reply_ctx(msg, lang, body)]

    def _handle_pending_reservation(
        self,
        msg: Message,
        lang: str,
        pending: dict[str, Any],
        is_confirmed: bool,
    ) -> list[Action]:
        if not is_confirmed:
            self._delete_pending(msg)
            return self._reply_template(msg, lang, "reserve_class_declined")

        class_context = self._complete_pending_class_context(msg, pending)
        result = self.crm.reserve_class(
            tenant_id=msg.tenant_id,
            member_id=pending.get("member_id"),
            class_id=pending.get("class_id"),
            idempotency_key=pending.get("idempotency_key"),
            comments="booked on whatsapp",
        )
        self._delete_pending(msg)

        if result == ENUM_CRM_RETURN_OK:
            return self._reply_template(msg, lang, "reserve_class_confirmed", class_context)

        if result == ENUM_CRM_RETURN_ALREADY_BOOKED:
            return self._reply_template(msg, lang, "reserve_class_already_booked", class_context)

        return self._reply_template(msg, lang, "reserve_class_failed")

    def _complete_pending_class_context(self, msg: Message, pending: dict[str, Any]) -> dict[str, Any]:
        class_id = pending.get("class_id")
        class_name = pending.get("class_name") or class_id
        class_date = pending.get("class_date")
        class_time = pending.get("class_time")

        needs_crm_fallback = (not class_date or not class_time) or class_name == class_id
        if needs_crm_fallback and class_id:
            details = self._safe_get_class_details(msg.tenant_id, class_id)
            meta = self._class_meta_from_details(details, class_id)
            class_name = class_name if class_name != class_id else meta.get("class_name") or class_name
            class_date = class_date or meta.get("class_date")
            class_time = class_time or meta.get("class_time")

        return {
            "class_id": class_id,
            "class_name": class_name,
            "class_date": class_date,
            "class_time": class_time,
        }

    def verification_active(self, msg: Message, lang: str, member_id: str) -> list[Action]:
        return self._reply_template(msg, lang, "crm_verification_active")
