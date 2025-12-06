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
from datetime import datetime
from typing import List, Optional

from ..domain.models import Message, Action
from ..common.utils import new_id
from ..common.config import settings
from ..services.nlu_service import NLUService
from ..services.kb_service import KBService
from ..services.template_service import TemplateService
from ..services.crm_service import CRMService
from ..services.ticketing_service import TicketingService
from ..services.metrics_service import MetricsService
from ..repos.conversations_repo import ConversationsRepo
from ..repos.tenants_repo import TenantsRepo
from ..repos.messages_repo import MessagesRepo
from ..repos.members_index_repo import MembersIndexRepo

STATE_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATE_AWAITING_VERIFICATION = "awaiting_verification"
STATE_AWAITING_CHALLENGE = "awaiting_challenge"
STATE_AWAITING_CLASS_SELECTION = "awaiting_class_selection"
STATE_AWAITING_MESSAGE = "awaiting_message"

SESSION_TIMEOUT_SECONDS = 120


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
        crm: CRMService | None = None,
        ticketing: TicketingService | None = None,
        conv: ConversationsRepo | None = None,
        tenants: TenantsRepo | None = None,
        messages: MessagesRepo | None = None,
        members_index: MembersIndexRepo | None = None,
    ) -> None:
        self.nlu = nlu or NLUService()
        self.kb = kb or KBService()
        self.tpl = tpl or TemplateService()
        self.metrics = metrics or MetricsService()
        self.crm = crm or CRMService()
        self.ticketing = ticketing or TicketingService()
        self.conv = conv or ConversationsRepo()
        self.tenants = tenants or TenantsRepo()
        self.messages = messages or MessagesRepo()
        self.members_index = members_index or MembersIndexRepo()

        # cache na słowa typu TAK / NIE z templatek
        self._words_cache: dict[tuple[str, str, str], set[str]] = {}

    # -------------------------------------------------------------------------
    #  Helpers ogólne
    # -------------------------------------------------------------------------

    def _reply(
        self,
        msg: Message,
        lang: str,
        body: str,
        channel: Optional[str] = None,
        channel_user_id: Optional[str] = None,
    ) -> Action:
        """Mały helper do budowania akcji reply."""
        return Action(
            "reply",
            {
                "to": msg.from_phone,
                "body": body,
                "tenant_id": msg.tenant_id,
                "channel": channel or msg.channel,
                "channel_user_id": channel_user_id or msg.channel_user_id,
                "language_code": lang,
            },
        )
   
    def _generate_verification_code(self, length: int = 6) -> str:
        """Generuje prosty kod weryfikacyjny używany w flow WWW -> WhatsApp."""
        import secrets
        import string

        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def _whatsapp_wa_me_link(self, code: str) -> str:
        """Buduje link wa.me z predefiniowaną treścią zawierającą kod weryfikacyjny."""
        raw = settings.twilio_whatsapp_number  # np. "whatsapp:+48000000000"
        phone = raw.replace("whatsapp:", "") if raw else ""
        return f"https://wa.me/{phone}?text=KOD:{code}"

    def _pending_key(self, phone: str) -> str:
        """
        Buduje klucz pod którym trzymamy w DDB oczekującą rezerwację
        lub listę zajęć dla danego numeru telefonu.
        """
        return f"pending#{phone}"

    def _get_words_set(
        self,
        tenant_id: str,
        template_name: str,
        lang: str | None = None,
    ) -> set[str]:
        """
        Wczytuje listę słów (np. TAK / NIE) z Templates (per tenant + język)
        i zwraca jako zbiór lowercase stringów.
        """
        key = (tenant_id, template_name, lang or "")
        if key in self._words_cache:
            return self._words_cache[key]

        raw = self.tpl.render_named(tenant_id, template_name, lang, {})

        if not raw:
            words: set[str] = set()
            self._words_cache[key] = words
            return words

        parts = re.split(r"[\s,;]+", raw)
        words = {p.strip().lower() for p in parts if p.strip()}
        self._words_cache[key] = words
        return words

    def _resolve_and_persist_language(self, msg: Message) -> str:
        """
        Ustala język konwersacji (z wiadomości, z rozmowy, z tenant) i zapisuje go.
        """
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        if getattr(msg, "language_code", None):
            lang = msg.language_code
            self.conv.upsert_conversation(
                msg.tenant_id,
                channel,
                channel_user_id,
                language_code=lang,
                last_intent=None,
                state_machine_status=STATE_AWAITING_MESSAGE,
            )
            return lang

        existing = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id)
        if existing and existing.get("language_code"):
            return existing["language_code"]

        tenant = self.tenants.get(msg.tenant_id) or {}
        lang = tenant.get("language_code") or settings.get_default_language()

        self.conv.upsert_conversation(
            msg.tenant_id,
            channel,
            channel_user_id,
            language_code=lang,
            last_intent=None,
            state_machine_status=STATE_AWAITING_MESSAGE,
        )
        return lang

    def change_conversation_language(
        self, tenant_id: str, phone: str, new_lang: str
    ) -> dict:
        """Metoda użyteczna na przyszłość (panel konsultanta)."""
        return self.conv.set_language(tenant_id, phone, new_lang)

    # -------------------------------------------------------------------------
    #  Weryfikacja PerfectGym – wspólny helper
    # -------------------------------------------------------------------------

    def _ensure_crm_verification(
        self,
        msg: Message,
        conv: dict,
        lang: str,
        post_intent: str | None = None,
        post_slots: dict | None = None,
    ) -> Optional[List[Action]]:
        """
        Sprawdza, czy użytkownik ma ważną strong-verification dla PerfectGym.
        Jeśli nie:
         - na WWW: flow z kodem i linkiem wa.me (awaiting_verification),
         - na WhatsApp: flow challenge PG (awaiting_challenge).

        Zwraca:
         - None, jeśli wszystko OK i można kontynuować operację PG,
         - listę akcji (reply/handover), jeśli flow weryfikacji został
           zainicjowany/obsłużony i dalsze przetwarzanie należy wstrzymać.
        """
        now_ts = int(time.time())
        pg_level = conv.get("pg_verification_level") or "none"
        pg_until = conv.get("pg_verified_until") or 0

        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        # 1) strong + nieprzeterminowane → OK
        if pg_level == "strong" and pg_until >= now_ts:
            return None

        # 2) Kanał WWW → flow: kod + WhatsApp
        if channel == "web":
            verification_code = self._generate_verification_code()
            wa_link = self._whatsapp_wa_me_link(verification_code)

            self.conv.upsert_conversation(
                tenant_id=msg.tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                verification_code=verification_code,
                pg_member_id=None,
                pg_verification_level="none",
                pg_verified_until=None,
                state_machine_status=STATE_AWAITING_VERIFICATION,
                pg_post_intent=post_intent,
                pg_post_slots=post_slots or {},
            )

            body = self.tpl.render_named(
                msg.tenant_id,
                "pg_web_verification_required",
                lang,
                {
                    "verification_code": verification_code,
                    "whatsapp_link": wa_link,
                },
            )

            return [
                self._reply(
                    msg,
                    lang,
                    body,
                    channel="web",
                    channel_user_id=channel_user_id,
                )
            ]

        # 3) Kanał WhatsApp → flow challenge PG (np. DOB/email)
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            state_machine_status=STATE_AWAITING_CHALLENGE,
            pg_challenge_type="dob",  # domyślnie DOB (można rozszerzyć o email itd.)
            pg_challenge_attempts=0,
            pg_post_intent=post_intent,
            pg_post_slots=post_slots or {},
        )

        body = self.tpl.render_named(
            msg.tenant_id,
            "pg_challenge_ask_dob",
            lang,
            {},
        )

        return [
            self._reply(
                msg,
                lang,
                body,
                channel="whatsapp",
                channel_user_id=msg.channel_user_id,
            )
        ]

    # -------------------------------------------------------------------------
    #  Operacje PerfectGym – core
    # -------------------------------------------------------------------------

    def _pg_member_balance_core(
        self, msg: Message, lang: str, member_id: str
    ) -> List[Action]:
        balance_resp = self.crm.get_member_balance(
            tenant_id=msg.tenant_id,
            member_id=member_id,
        )
        balance = balance_resp.get("balance", 0)

        body = self.tpl.render_named(
            msg.tenant_id,
            "pg_member_balance",
            lang,
            {"balance": balance},
        )
        return [self._reply(msg, lang, body)]

    def _pg_contract_status_core(
        self, msg: Message, lang: str, member_id: str
    ) -> List[Action]:
        """
        Zwraca status kontraktu na podstawie member_id z PerfectGym.
        Zakładamy, że wcześniej przeszedł `_ensure_crm_verification`
        i w rozmowie mamy poprawne pg_member_id.
        """
        if not member_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "pg_member_not_linked",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        contracts_resp = self.crm.get_contracts_by_member_id(
            tenant_id=msg.tenant_id,
            member_id=member_id,
        )
        contracts = contracts_resp.get("value", []) or []

        if not contracts:
            body = self.tpl.render_named(
                msg.tenant_id,
                "pg_contract_not_found",
                lang,
                {
                    "email": slots.get("email", ""),
                    "phone": slots.get("phone", ""),
                },
            )
            return [self._reply(msg, lang, body)]

        current = next(
            (c for c in contracts if c.get("status") == "Current"),
            contracts[0],
        )

        status = current.get("status") or "Unknown"
        is_active = bool(current.get("isActive"))
        start_date = (current.get("startDate") or "")[:10]
        end_date_raw = current.get("endDate")
        end_date = (end_date_raw or "")[:10] if end_date_raw else ""

        payment_plan = current.get("paymentPlan") or {}
        plan_name = payment_plan.get("name") or ""
        membership_fee = payment_plan.get("membershipFee") or {}
        membership_fee_gross = membership_fee.get("gross")
        balance_resp = self.crm.get_member_balance(
            tenant_id=msg.tenant_id,
            member_id=int(member_id) if str(member_id).isdigit() else member_id,
        )
        current_balance = balance_resp.get("currentBalance")
        prepaid_balance = balance_resp.get("prepaidBalance")
        prepaid_bonus_balance = balance_resp.get("prepaidBonusBalance")
        negative_since = balance_resp.get("negativeBalanceSince")

        context = {
            "plan_name": plan_name,
            "status": status,
            "is_active": is_active,
            "start_date": start_date,
            "end_date": end_date or "",
            "membership_fee": membership_fee_gross,
            "current_balance": current_balance,
            "prepaid_balance": prepaid_balance,
            "prepaid_bonus_balance": prepaid_bonus_balance,
            "negative_balance_since": negative_since
        }

        body = self.tpl.render_named(
            msg.tenant_id,
            "pg_contract_details",
            lang,
            context,
        )

        return [self._reply(msg, lang, body)]
        
    def _reserve_class_with_id_core(
        self,
        msg: Message,
        lang: str,
        class_id: str,
        member_id: str,
        class_meta: Optional[dict] = None,
    ) -> List[Action]:
        """
        Tworzy pending rezerwację i wysyła prośbę o potwierdzenie.
        class_meta – opcjonalnie: name, date, time.
        """
        idem = new_id("idem-")

        item = {
            "pk": self._pending_key(msg.from_phone),
            "sk": "pending",
            "class_id": class_id,
            "member_id": member_id,
            "idempotency_key": idem,
        }
        if class_meta:
            # spodziewane pola: class_name, class_date, class_time
            item.update(class_meta)

        self.conv.put(item)

        # ustaw stan na oczekiwanie potwierdzenia
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=msg.channel or "whatsapp",
            channel_user_id=msg.channel_user_id or msg.from_phone,
            last_intent="reserve_class",
            state_machine_status=STATE_AWAITING_CONFIRMATION,
            language_code=lang,
        )

        body = self.tpl.render_named(
            msg.tenant_id,
            "reserve_class_confirm",
            lang,
            {"class_id": class_id},
        )
        return [self._reply(msg, lang, body)]

    # -------------------------------------------------------------------------
    #  Weryfikacja challenge PG – prawdziwa implementacja (bez MVP bool(text))
    # -------------------------------------------------------------------------

    def _verify_challenge_answer(
        self,
        tenant_id: str,
        phone: str,
        challenge_type: str,
        answer: str,
    ) -> bool:
        """
        Weryfikacja odpowiedzi na challenge PG.

        Docelowo logika powinna siedzieć w CRMService (odpytywanie PerfectGym
        / wewnętrznego indeksu członków). Tutaj delegujemy do metody
        crm.verify_member_challenge.

        Zwraca True/False.
        """
        answer = (answer or "").strip()
        if not answer:
            return False

        try:
            return bool(
                self.crm.verify_member_challenge(
                    tenant_id=tenant_id,
                    phone=phone,
                    challenge_type=challenge_type,
                    answer=answer,
                )
            )
        except Exception:
            # W razie błędu po stronie integracji traktujemy jako niepowodzenie.
            return False

    def _clear_pg_challenge_state(
        self, tenant_id: str, channel: str, channel_user_id: str
    ) -> None:
        """
        Czyści wszystkie pola związane z challenge PG i post-intent.

        Wymaga dodania odpowiedniej metody w ConversationsRepo
        (np. update z REMOVE pg_challenge_type, pg_challenge_attempts,
        pg_post_intent, pg_post_slots).
        """
        try:
            self.conv.clear_pg_challenge(tenant_id, channel, channel_user_id)
        except AttributeError:
            # fallback – jeśli clear_pg_challenge nie jest jeszcze zaimplementowane,
            # nic nie robimy (ale warto je dopisać).
            pass

    def _handle_crm_challenge(
        self, msg: Message, conv: dict, lang: str
    ) -> List[Action]:
        """
        Użytkownik jest w stanie awaiting_challenge – traktujemy wiadomość
        jako odpowiedź na challenge PG (np. data urodzenia / e-mail).
        """
        text = (msg.body or "").strip()
        tenant_id = msg.tenant_id
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        challenge_type = conv.get("pg_challenge_type") or "dob"
        attempts = int(conv.get("pg_challenge_attempts") or 0)

        is_correct = self._verify_challenge_answer(
            tenant_id=tenant_id,
            phone=msg.from_phone,
            challenge_type=challenge_type,
            answer=text,
        )

        if is_correct:
            now_ts = int(time.time())
            ttl = now_ts + 15 * 60  # 15 minut ważności weryfikacji

            post_intent = conv.get("pg_post_intent")
            post_slots = conv.get("pg_post_slots") or {}

            # 1) spróbuj pobrać membera z PerfectGym po numerze telefonu
            member_id: str | None = None
            try:
                members_resp = self.crm.get_member_by_phone(tenant_id, msg.from_phone)
                items = (members_resp or {}).get("value") or []
                if items:
                    # PerfectGym zwykle używa pola 'id' lub 'Id'
                    member_id = str(items[0].get("id") or items[0].get("Id"))
            except Exception:
                member_id = None

            # 2) fallback na MembersIndex, jeśli PG nic nie zwróci
            if not member_id and self.members_index:
                try:
                    member = self.members_index.get_member(tenant_id, msg.from_phone)
                    if member:
                        member_id = str(
                            member.get("id") or member.get("member_id")
                        )
                except Exception:
                    member_id = None

            # aktualizacja rozmowy – wychodzimy ze stanu challenge
            self.conv.upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
                pg_member_id=member_id,
                pg_verification_level="strong",
                pg_verified_until=ttl,
            )

            self._clear_pg_challenge_state(tenant_id, channel, channel_user_id)

            success_body = self.tpl.render_named(
                tenant_id,
                "pg_challenge_success",
                lang,
                {},
            )

            actions: List[Action] = [
                self._reply(
                    msg,
                    lang,
                    success_body,
                    channel=msg.channel,
                    channel_user_id=msg.channel_user_id,
                )
            ]


            # 2) automatyczne dokończenie pierwotnej operacji PG
            if post_intent == "pg_member_balance":
                if member_id:
                    actions.extend(
                        self._pg_member_balance_core(msg, lang, member_id)
                    )
                else:
                    body = self.tpl.render_named(
                        tenant_id,
                        "pg_member_not_linked",
                        lang,
                        {},
                    )
                    actions.append(self._reply(msg, lang, body))

            elif post_intent == "pg_contract_status":
                if member_id:
                    actions.extend(
                        self._pg_contract_status_core(msg, lang, member_id)
                    )
                else:
                    body = self.tpl.render_named(
                        tenant_id,
                        "pg_member_not_linked",
                        lang,
                        {},
                    )
                    actions.append(self._reply(msg, lang, body))

            elif post_intent == "reserve_class":
                post_class_id = (post_slots or {}).get("class_id")
                if member_id and post_class_id:
                    actions.extend(
                        self._reserve_class_with_id_core(
                            msg,
                            lang,
                            post_class_id,
                            member_id,
                        )
                    )
                else:
                    body = self.tpl.render_named(
                        tenant_id,
                        "pg_member_not_linked",
                        lang,
                        {},
                    )
                    actions.append(self._reply(msg, lang, body))

            return actions

        # Zła odpowiedź – zwiększamy licznik prób
        attempts += 1
        self.conv.upsert_conversation(
            tenant_id=tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            pg_challenge_attempts=attempts,
        )

        if attempts >= 3:
            # Po 3 próbach – blokujemy i przekazujemy do człowieka
            self.conv.upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=STATE_AWAITING_MESSAGE,
            )

            body = self.tpl.render_named(
                tenant_id,
                "pg_challenge_fail_handover",
                lang,
                {},
            )
            return [
                self._reply(msg, lang, body),
                Action(
                    "handover",
                    {
                        "tenant_id": tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                ),
            ]

        # Mniej niż 3 próby – poproś o kolejną próbę
        body = self.tpl.render_named(
            tenant_id,
            "pg_challenge_retry",
            lang,
            {"attempts_left": 3 - attempts},
        )
        return [self._reply(msg, lang, body)]

    # -------------------------------------------------------------------------
    #  Obsługa wyboru zajęć z listy
    # -------------------------------------------------------------------------

    def _handle_class_selection(
        self, msg: Message, lang: str
    ) -> Optional[List[Action]]:
        """
        Obsługa stanu STATE_AWAITING_CLASS_SELECTION – użytkownik wybiera
        zajęcia z wcześniej pokazanej listy.
        """
        text = (msg.body or "").strip().lower()

        classes_item = self.conv.get(self._pending_key(msg.from_phone), "classes")
        if not classes_item:
            return None

        items = classes_item.get("items") or []
        if not items:
            return None

        # 1) Użytkownik podał numer (np. "1", "nr 2")
        m = re.search(r"\b(\d{1,2})\b", text)
        if m:
            idx = int(m.group(1))
            selected = next((c for c in items if c.get("index") == idx), None)
            if not selected:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_available_classes_invalid_index",
                    lang,
                    {"max_index": len(items)},
                )
                return [self._reply(msg, lang, body)]
            return self._start_reservation_from_selection(msg, lang, selected)

        # 2) "dzisiaj"/"today" – filtrujemy po dzisiejszej dacie
        today = datetime.now().date().isoformat()  # "YYYY-MM-DD"
        if any(w in text for w in ["dzis", "dziś", "dzisiaj", "today"]):
            todays = [c for c in items if c.get("date") == today]
            if not todays:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_available_classes_no_today",
                    lang,
                    {},
                )
                return [self._reply(msg, lang, body)]

            if len(todays) == 1:
                return self._start_reservation_from_selection(msg, lang, todays[0])

            # kilka klas dzisiaj – pokaż ponumerowaną listę
            lines: list[str] = []
            for c in todays:
                line = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_available_classes_item",
                    lang,
                    {
                        "index": c["index"],
                        "date": c["date"],
                        "time": c["time"],
                        "name": c["name"],
                        "capacity": "",
                    },
                )
                lines.append(line)

            body = self.tpl.render_named(
                msg.tenant_id,
                "pg_available_classes_today",
                lang,
                {"classes": "\n".join(lines)},
            )
            return [self._reply(msg, lang, body)]

        # 3) Użytkownik podał konkretną datę (ISO YYYY-MM-DD)
        iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if iso_match:
            date_str = iso_match.group(1)
            same_day = [c for c in items if c.get("date") == date_str]
            if not same_day:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_available_classes_no_classes_on_date",
                    lang,
                    {"date": date_str},
                )
                return [self._reply(msg, lang, body)]

            if len(same_day) == 1:
                return self._start_reservation_from_selection(msg, lang, same_day[0])

            lines: list[str] = []
            for c in same_day:
                line = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_available_classes_item",
                    lang,
                    {
                        "index": c["index"],
                        "date": c["date"],
                        "time": c["time"],
                        "name": c["name"],
                        "capacity": "",
                    },
                )
                lines.append(line)

            body = self.tpl.render_named(
                msg.tenant_id,
                "pg_available_classes_today",
                lang,
                {"classes": "\n".join(lines)},
            )
            extra = self.tpl.render_named(
                msg.tenant_id,
                "pg_available_classes_select_by_number",
                lang,
                {},
            )
            full_body = f"{body}\n\n{extra}"

            return [self._reply(msg, lang, full_body)]

        # 4) Nic nie wybraliśmy – oddaj dalej do NLU / clarify
        return None

    def _start_reservation_from_selection(
        self, msg: Message, lang: str, selected: dict
    ) -> List[Action]:
        """
        Użytkownik wybrał konkretną klasę z listy.
        Tutaj pilnujemy:
        - że mamy class_id,
        - że użytkownik jest zweryfikowany w PG (w razie potrzeby wywołujemy challenge),
        - że pending rezerwacja używa prawdziwego member_id z PG.
        """
        class_id = selected.get("class_id")
        if not class_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "reserve_class_missing_id",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}

        # 1) Weryfikacja PG – jeśli potrzeba, zainicjuje challenge
        verify_resp = self._ensure_crm_verification(
            msg,
            conv,
            lang,
            post_intent="reserve_class",
            post_slots={"class_id": class_id},
        )
        if verify_resp:
            # tutaj kończymy – challenge / WWW verification przejmie flow
            return verify_resp

        # 2) Po weryfikacji PG oczekujemy pg_member_id w rozmowie
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}
        member_id = conv.get("pg_member_id")
        if not member_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "pg_member_not_linked",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        class_meta = {
            "class_name": selected.get("name"),
            "class_date": selected.get("date"),
            "class_time": selected.get("time"),
        }

        return self._reserve_class_with_id_core(
            msg,
            lang,
            class_id=class_id,
            member_id=member_id,
            class_meta=class_meta,
        )

    # -------------------------------------------------------------------------
    #  Pending rezerwacja – obsługa TAK/NIE
    # -------------------------------------------------------------------------

    def _handle_pending_reservation_confirmation(
        self, msg: Message, lang: str
    ) -> Optional[List[Action]]:
        """
        Sprawdza, czy istnieje pending rezerwacja i obsługuje odpowiedź TAK/NIE.
        """
        text_raw = (msg.body or "").strip()
        text_lower = text_raw.lower()

        pending = self.conv.get(self._pending_key(msg.from_phone), "pending")
        if not pending:
            return None

        confirm_words = self._get_words_set(
            msg.tenant_id,
            "reserve_class_confirm_words",
            lang,
        )
        decline_words = self._get_words_set(
            msg.tenant_id,
            "reserve_class_decline_words",
            lang,
        )

        if text_lower in confirm_words:
            class_id = pending.get("class_id")
            member_id = pending.get("member_id")
            idem = pending.get("idempotency_key")
            class_name = pending.get("class_name") or class_id
            class_date = pending.get("class_date")
            class_time = pending.get("class_time")

            res = self.crm.reserve_class(
                tenant_id=msg.tenant_id,
                member_id=member_id,
                class_id=class_id,
                idempotency_key=idem,
                comments="booked on whatsapp",
            )

            self.conv.delete(self._pending_key(msg.from_phone), "pending")

            if (res or {}).get("ok", True):
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "reserve_class_confirmed",
                    lang,
                    {
                        "class_id": class_id,
                        "class_name": class_name,
                        "class_date": class_date,
                        "class_time": class_time,
                    },
                )
                return [self._reply(msg, lang, body)]

            body = self.tpl.render_named(
                msg.tenant_id,
                "reserve_class_failed",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        if text_lower in decline_words:
            self.conv.delete(self._pending_key(msg.from_phone), "pending")
            body = self.tpl.render_named(
                msg.tenant_id,
                "reserve_class_declined",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        return None

    # -------------------------------------------------------------------------
    #  WWW <-> WhatsApp: mapowanie kodu weryfikacyjnego
    # -------------------------------------------------------------------------

    def _handle_whatsapp_verification_code_linking(
        self, msg: Message, lang: str
    ) -> Optional[List[Action]]:
        """
        Obsługa wiadomości WhatsApp rozpoczynających się od "KOD:" –
        mapowanie kodu z WWW na rozmowę WhatsApp + przypięcie membera PG.
        """
        text = (msg.body or "").strip()
        text_upper = text.upper()

        if msg.channel != "whatsapp" or not text_upper.startswith("KOD:"):
            return None

        code = text_upper.replace("KOD:", "").strip()

        web_conv = self.conv.find_by_verification_code(
            tenant_id=msg.tenant_id,
            verification_code=code,
        )
        if not web_conv:
            body = self.tpl.render_named(
                msg.tenant_id,
                "www_not_verified",
                lang,
                {},
            )
            return [
                self._reply(
                    msg,
                    lang,
                    body,
                    channel="whatsapp",
                    channel_user_id=msg.from_phone,
                )
            ]

        member_id = None

        # member pobierany z PG
        resp = self.crm.get_member_by_phone(msg.tenant_id, msg.from_phone)
        items = (resp or {}).get("value") or []
        if items:
            member_id = str(items[0].get("id") or items[0].get("Id"))

        # fallback
        if not member_id and self.members_index:
            member = self.members_index.get_member(msg.tenant_id, msg.from_phone)
            if member:
                member_id = str(member.get("id") or member.get("member_id"))

        if not member_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "www_user_not_found",
                lang,
                {},
            )
            return [
                self._reply(
                    msg,
                    lang,
                    body,
                    channel="whatsapp",
                    channel_user_id=msg.from_phone,
                )
            ]

        member_id = member["id"]
        now_ts = int(time.time())
        ttl = now_ts + 30 * 60  # 30 minut weryfikacji dla WWW

        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=web_conv["channel"],
            channel_user_id=web_conv["channel_user_id"],
            pg_member_id=member_id,
            pg_verification_level="strong",
            pg_verified_until=ttl,
            verification_code=None,
            state_machine_status=STATE_AWAITING_MESSAGE,
        )

        body = self.tpl.render_named(
            msg.tenant_id,
            "www_verified",
            lang,
            {},
        )
        return [
            self._reply(
                msg,
                lang,
                body,
                channel="whatsapp",
                channel_user_id=msg.from_phone,
            )
        ]

    # -------------------------------------------------------------------------
    #  Lista zajęć – wspólny helper dla intentów
    # -------------------------------------------------------------------------

    def _build_available_classes_response(
        self, msg: Message, lang: str
    ) -> List[Action]:
        """
        Pobiera listę dostępnych zajęć z PG, buduje listę tekstową
        + zapisuje uproszczone dane w DDB (do późniejszego wyboru).
        """
        classes_resp = self.crm.get_available_classes(
            tenant_id=msg.tenant_id,
            top=10,
        )
        classes = classes_resp.get("value") or []

        if not classes:
            body = self.tpl.render_named(
                msg.tenant_id,
                "pg_available_classes_empty",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        lines: list[str] = []
        simplified: list[dict] = []

        for idx, c in enumerate(classes, start=1):
            start = str(c.get("startDate") or c.get("startdate") or "")
            date_str = start[:10] if len(start) >= 10 else "?"
            time_str = start[11:16] if len(start) >= 16 else "?"
            class_type = (c.get("classType") or {}).get("name") or "Class"

            attendees_count = c.get("attendeesCount") or 0
            attendees_limit = c.get("attendeesLimit")

            if attendees_limit is None:
                capacity_info = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_available_classes_capacity_no_limit",
                    lang,
                    {},
                )
            else:
                free = max(attendees_limit - attendees_count, 0)
                if free <= 0:
                    capacity_info = self.tpl.render_named(
                        msg.tenant_id,
                        "pg_available_classes_capacity_full",
                        lang,
                        {"limit": attendees_limit},
                    )
                else:
                    capacity_info = self.tpl.render_named(
                        msg.tenant_id,
                        "pg_available_classes_capacity_free",
                        lang,
                        {"free": free, "limit": attendees_limit},
                    )

            line = self.tpl.render_named(
                msg.tenant_id,
                "pg_available_classes_item",
                lang,
                {
                    "index": idx,
                    "date": date_str,
                    "time": time_str,
                    "name": class_type,
                    "capacity": capacity_info,
                },
            )
            lines.append(line)

            simplified.append(
                {
                    "index": idx,
                    "class_id": c.get("id"),
                    "date": date_str,
                    "time": time_str,
                    "name": class_type,
                    "start": start,
                }
            )

        body = self.tpl.render_named(
            msg.tenant_id,
            "pg_available_classes",
            lang,
            {"classes": "\n".join(lines)},
        )

        # zapis listy klas do późniejszego wyboru
        self.conv.put(
            {
                "pk": self._pending_key(msg.from_phone),
                "sk": "classes",
                "items": simplified,
            }
        )

        return [self._reply(msg, lang, body)]

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

        if intent not in ("clarify", "greeting") and confidence < 0.3:
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
        if intent == "reserve_class" and (slots.get("class_id") or "").strip():
            sm_state = STATE_AWAITING_CONFIRMATION
        elif intent == "pg_available_classes":
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
        lang = self._resolve_and_persist_language(msg)

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
            return self._handle_crm_challenge(msg, conv, lang)

        # 3b) Użytkownik wybiera zajęcia z listy
        if state == STATE_AWAITING_CLASS_SELECTION:
            selection_response = self._handle_class_selection(msg, lang)
            if selection_response is not None:
                return selection_response

        # 3c) Pending rezerwacja – TAK/NIE
        pending_response = self._handle_pending_reservation_confirmation(msg, lang)
        if pending_response is not None:
            return pending_response

        # 3d) KOD:... z WhatsApp (powiązanie z WWW)
        code_response = self._handle_whatsapp_verification_code_linking(msg, lang)
        if code_response is not None:
            return code_response

        # 4) NLU – klasyfikacja intencji
        intent, slots, _ = self._classify_intent(msg, lang)

        # 5) Zapis intentu / stanu
        self._update_conversation_state(msg, lang, intent, slots)

        # 6) Routing po intencji

        # 6.1 Powitanie
        if intent == "greeting":
            body = self.tpl.render_named(
                msg.tenant_id,
                "greeting",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        # 6.2 FAQ
        if intent == "faq":
            conv_key = msg.conversation_id or (msg.channel_user_id or msg.from_phone)
            chat_history: list[dict] = []

            if not is_new_session and self.messages:
                try:
                    history_items = self.messages.get_last_messages(
                        tenant_id=msg.tenant_id,
                        conv_key=conv_key,
                        limit=10,
                    ) or []
                except Exception:
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

            ai_body = self.kb.answer_ai(
                question=msg.body,
                tenant_id=msg.tenant_id,
                language_code=lang,
                history=chat_history,
            )

            if ai_body:
                body = ai_body
            else:
                topic = slots.get("topic", "hours")
                body = (
                    self.kb.answer(
                        topic, tenant_id=msg.tenant_id, language_code=lang
                    )
                    or self.tpl.render_named(
                        msg.tenant_id,
                        "faq_no_info",
                        lang,
                        {},
                    )
                )

            return [self._reply(msg, lang, body)]

        # 6.3 Rezerwacja zajęć
        if intent == "reserve_class":
            class_id = (slots.get("class_id") or "").strip()

            # brak class_id → najpierw lista zajęć
            if not class_id:
                # tu ustawiamy stan ręcznie
                self.conv.upsert_conversation(
                    tenant_id=msg.tenant_id,
                    channel=msg.channel or "whatsapp",
                    channel_user_id=msg.channel_user_id or msg.from_phone,
                    last_intent=intent,
                    state_machine_status=STATE_AWAITING_CLASS_SELECTION,
                    language_code=lang,
                )
                return self._build_available_classes_response(msg, lang)

            # mamy class_id → standardowy flow z weryfikacją PG i pending
            verify_resp = self._ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent="reserve_class",
                post_slots={"class_id": class_id},
            )
            if verify_resp:
                return verify_resp

            member_id = conv.get("pg_member_id")
            if not member_id:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_member_not_linked",
                    lang,
                    {},
                )
                return [self._reply(msg, lang, body)]

            return self._reserve_class_with_id_core(
                msg,
                lang,
                class_id=class_id,
                member_id=member_id,
            )

        # 6.4 Handover do człowieka
        if intent == "handover":
            self.conv.assign_agent(
                tenant_id=msg.tenant_id,
                channel=msg.channel or "whatsapp",
                channel_user_id=msg.channel_user_id or msg.from_phone,
                agent_id=slots.get("agent_id", "UNKNOWN"),
            )
            body = self.tpl.render_named(
                msg.tenant_id,
                "handover_to_staff",
                lang,
                {},
            )
            return [self._reply(msg, lang, body)]

        # 6.5 Ticket do systemu ticketowego
        if intent == "ticket":
            conv_key = msg.conversation_id or (msg.channel_user_id or msg.from_phone)

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
                or f"Zgłoszenie z chatu.\n\nOstatnia wiadomość:\n{msg.body}\n\nHistoria:\n{history_block}"
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

        # 6.6 Lista dostępnych zajęć (bez natychmiastowej rezerwacji)
        if intent == "pg_available_classes":
            return self._build_available_classes_response(msg, lang)

        # 6.7 Status kontraktu
        if intent == "pg_contract_status":
            verify_resp = self._ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent="pg_contract_status",
                post_slots=slots,
            )
            if verify_resp:
                return verify_resp

            member_id = conv.get("pg_member_id")
            if not member_id:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_member_not_linked",
                    lang,
                    {},
                )
                return [self._reply(msg, lang, body)]

            return self._pg_contract_status_core(msg, lang, member_id)

        # 6.8 Saldo członkowskie
        if intent == "pg_member_balance":
            verify_resp = self._ensure_crm_verification(
                msg,
                conv,
                lang,
                post_intent="pg_member_balance",
                post_slots=slots,
            )
            if verify_resp:
                return verify_resp

            member_id = conv.get("pg_member_id")
            if not member_id:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_member_not_linked",
                    lang,
                    {},
                )
                return [self._reply(msg, lang, body)]

            return self._pg_member_balance_core(msg, lang, member_id)

        # 6.9 Domyślny clarify
        body = self.tpl.render_named(
            msg.tenant_id,
            "clarify_generic",
            lang,
            {},
        )
        return [self._reply(msg, lang, body)]
