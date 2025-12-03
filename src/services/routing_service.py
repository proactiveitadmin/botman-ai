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
from ..services.nlu_service import NLUService
from ..services.kb_service import KBService
from ..services.template_service import TemplateService
from ..adapters.perfectgym_client import PerfectGymClient
from ..repos.conversations_repo import ConversationsRepo
from ..repos.tenants_repo import TenantsRepo
from ..repos.messages_repo import MessagesRepo
from ..common.utils import new_id
from ..services.metrics_service import MetricsService        
from ..adapters.jira_client import JiraClient
from ..repos.members_index_repo import MembersIndexRepo
from ..common.config import settings

STATE_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATE_AWAITING_VERIFICATION = "awaiting_verification"
STATE_AWAITING_CHALLENGE = "awaiting_challenge"
STATE_AWAITING_CLASS_SELECTION = "awaiting_class_selection"

class RoutingService:
    """
    Serwis łączący NLU, KB i integracje zewnętrzne tak, by obsłużyć pełen flow rozmowy.
    """
    def __init__(
        self,
        nlu: NLUService | None = None,
        kb: KBService | None = None,
        tpl: TemplateService | None = None,
        pg: PerfectGymClient | None = None,
        conv: ConversationsRepo | None = None,
        tenants: TenantsRepo | None = None,
        messages: MessagesRepo | None = None,
        metrics: MetricsService | None = None,
        jira: JiraClient | None = None,
        members_index: MembersIndexRepo | None = None,
    ) -> None:
        self.nlu = nlu or NLUService()
        self.kb = kb or KBService()
        self.tpl = tpl or TemplateService()
        self.pg = pg or PerfectGymClient()
        self.conv = conv or ConversationsRepo()
        self.tenants = tenants or TenantsRepo()
        self.messages = messages or MessagesRepo()
        self.metrics = metrics or MetricsService()
        self.jira = jira or JiraClient()
        self.members_index = members_index or MembersIndexRepo()
        self._words_cache: dict[tuple[str, str, str], set[str]] = {}

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
        Buduje klucz pod którym trzymamy w DDB oczekującą rezerwację dla danego numeru telefonu.
        """
        return f"pending#{phone}"

    def _get_words_set(self, 
        tenant_id: str, 
        template_name: str, 
        lang: str | None = None,
    ) -> set[str]:
        """
        Wczytuje listę słów (np. TAK / NIE) z Templates (per tenant + język)
        i zwraca jako zbiór lowercase stringów.

        Szablon może zawierać:
        - słowa rozdzielone przecinkiem,
        - średniki,
        - nowe linie, itp.
        Np. "tak, tak., potwierdzam, ok"
        """
        key = (tenant_id, template_name, lang or "")
        if key in self._words_cache:
            return self._words_cache[key]

        raw = self.tpl.render_named(tenant_id, template_name, lang, {})
        
        if not raw:
            words: set[str] = set()
            self._words_cache[key] = words
            return words

        import re

        parts = re.split(r"[\s,;]+", raw)
        words = {p.strip().lower() for p in parts if p.strip()}
        self._words_cache[key] = words
        return words

    def _resolve_and_persist_language(self, msg: Message) -> str:
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone

        # 0. Jeśli Message już ma język (np. z frontu WWW) – używamy tego
        if getattr(msg, "language_code", None):
            lang = msg.language_code
            self.conv.upsert_conversation(
                msg.tenant_id,
                channel,
                channel_user_id,
                language_code=lang,
                last_intent=None,
                state_machine_status=None,
            )
            return lang

        # 1. Istniejąca rozmowa
        existing = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id)
        if existing and existing.get("language_code"):
            return existing["language_code"]

        # 2. Tenant
        tenant = self.tenants.get(msg.tenant_id) or {}
        lang = tenant.get("language_code") or settings.get_default_language()

        # 3. Zapis/aktualizacja rozmowy
        self.conv.upsert_conversation(
            msg.tenant_id,
            channel,
            channel_user_id,
            language_code=lang,
            last_intent=None,
            state_machine_status=None,
        )
        return lang

    def change_conversation_language(self, tenant_id: str, phone: str, new_lang: str) -> dict:
        """Metoda użyteczna na przyszłość (panel konsultanta)."""
        return self.conv.set_language(tenant_id, phone, new_lang)
 
    # --- Helper: wspólna weryfikacja PG (WhatsApp + WWW) ---
    def _ensure_pg_verification(
        self, msg: Message, conv: dict, lang: str
    ) -> Optional[List[Action]]:
        """
        Sprawdza, czy użytkownik ma ważną strong-verification dla PerfectGym.
        Jeśli nie:
         - na WWW: flow z kodem i linkiem wa.me (awaiting_verification),
         - na WhatsApp: flow challenge PG (awaiting_challenge).

        Zwraca:
         - None, jeśli wszystko OK i można kontynuować operację PG,
         - listę akcji (reply/handover), jeśli flow weryfikacji został zainicjowany/obsłużony.
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
                Action(
                    "reply",
                    {
                        "to": channel_user_id,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": "web",
                        "channel_user_id": channel_user_id,
                    },
                )
            ]

        # 3) Kanał WhatsApp → flow challenge PG (np. DOB/email)
        self.conv.upsert_conversation(
            tenant_id=msg.tenant_id,
            channel=channel,
            channel_user_id=channel_user_id,
            state_machine_status=STATE_AWAITING_CHALLENGE,
            pg_challenge_type="dob",  # na razie domyślnie DOB
            pg_challenge_attempts=0,
        )

        body = self.tpl.render_named(
            msg.tenant_id,
            "pg_challenge_ask_dob",
            lang,
            {},
        )

        return [
            Action(
                "reply",
                {
                    "to": msg.from_phone,
                    "body": body,
                    "tenant_id": msg.tenant_id,
                    "channel": "whatsapp",
                    "channel_user_id": msg.channel_user_id,
                },
            )
        ]

    def _handle_pg_challenge(self, msg: Message, conv: dict, lang: str) -> List[Action]:
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

        # TODO: Prawdziwa implementacja powinna sprawdzić odpowiedź w PerfectGym/MembersIndex.
        # Tu: uproszczone MVP – wszystko, co niepuste, traktujemy jako poprawne.
        is_correct = bool(text)

        if is_correct:
            now_ts = int(time.time())
            ttl = now_ts + 15 * 60  # 15 minut ważności weryfikacji

            member = self.members_index.get_member(tenant_id, msg.from_phone)
            member_id = member["id"] if member else None

            self.conv.upsert_conversation(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                state_machine_status=None,
                pg_member_id=member_id,
                pg_verification_level="strong",
                pg_verified_until=ttl,
                pg_challenge_type=None,
                pg_challenge_attempts=None,
            )

            body = self.tpl.render_named(
                tenant_id,
                "pg_challenge_success",
                lang,
                {},
            )
            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                )
            ]

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
                state_machine_status=None,
            )

            body = self.tpl.render_named(
                tenant_id,
                "pg_challenge_fail_handover",
                lang,
                {},
            )
            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                ),
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
        return [
            Action(
                "reply",
                {
                    "to": msg.from_phone,
                    "body": body,
                    "tenant_id": tenant_id,
                    "channel": msg.channel,
                    "channel_user_id": msg.channel_user_id,
                },
            )
        ]
    def _handle_class_selection(self, msg: Message, lang: str) -> Optional[List[Action]]:
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
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]
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
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]

            if len(todays) == 1:
                # jedna klasa dzisiaj – od razu przechodzimy do potwierdzenia
                return self._start_reservation_from_selection(msg, lang, todays[0])

            # kilka klas dzisiaj – pokaż ponumerowaną listę i poproś o numer
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
            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                )
            ]

        # 3) Użytkownik podał konkretną datę (np. "2025-12-03") – prosty parser ISO
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
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]

            if len(same_day) == 1:
                return self._start_reservation_from_selection(msg, lang, same_day[0])

            # kilka zajęć danego dnia – pokaż listę + prośba o numer
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
                "pg_available_classes_today",  # możesz zrobić osobny template na "on_date"
                lang,
                {"classes": "\n".join(lines)},
            )
            # dodatkowa, jasna prośba o numer (osobny template)
            extra = self.tpl.render_named(
                msg.tenant_id,
                "pg_available_classes_select_by_number",
                lang,
                {},
            )

            full_body = f"{body}\n\n{extra}"

            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": full_body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                        },
                    )
            ]

        # 4) Nic nie wybraliśmy – oddaj dalej do NLU / clarify
        return None
    
    def _start_reservation_from_selection(self, msg: Message, lang: str, selected: dict) -> List[Action]:
        class_id = selected.get("class_id")
        if not class_id:
            body = self.tpl.render_named(
                msg.tenant_id,
                "reserve_class_missing_id",
                lang,
                {},
            )
            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                )
            ]

        # TODO: podłącz realny member_id (z PG / z profilu)
        member_id = "105"
        idem = new_id("idem-")

        self.conv.put(
            {
                "pk": self._pending_key(msg.from_phone),
                "sk": "pending",
                "class_id": class_id,
                "member_id": member_id,
                "idempotency_key": idem,
            }
        )

        # czyścimy listę zajęć, przechodzimy do potwierdzenia
        self.conv.delete(self._pending_key(msg.from_phone), "classes")
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
        return [
            Action(
                "reply",
                {
                    "to": msg.from_phone,
                    "body": body,
                    "tenant_id": msg.tenant_id,
                    "channel": msg.channel,
                    "channel_user_id": msg.channel_user_id,
                },
            )
        ]

    def handle(self, msg: Message) -> List[Action]:
        """
        Przetwarza pojedynczą wiadomość biznesową i zwraca listę akcji do wykonania.

        Zwraca zwykle jedną akcję typu "reply", ale architektura pozwala na wiele akcji w przyszłości.
        """
        text_raw = (msg.body or "").strip()
        text_lower = text_raw.lower()

        # 1) Język
        lang = self._resolve_and_persist_language(msg)

        # 2) Wczytaj rozmowę + stan maszyny
        channel = msg.channel or "whatsapp"
        channel_user_id = msg.channel_user_id or msg.from_phone
        conv = self.conv.get_conversation(msg.tenant_id, channel, channel_user_id) or {}
        state = conv.get("state_machine_status")
     
        # --- 0. Obsługa stanu awaiting_challenge (challenge PG na WhatsApp) ---
        if state == STATE_AWAITING_CHALLENGE and channel == "whatsapp":
            return self._handle_pg_challenge(msg, conv, lang)
        
        # --- 0b. Użytkownik wybiera zajęcia z listy ---
        if state == STATE_AWAITING_CLASS_SELECTION:
            selection_response = self._handle_class_selection(msg, lang)
            if selection_response is not None:
                return selection_response

        
        # --- 1. Obsługa oczekującej rezerwacji (TAK/NIE) ---
        pending = self.conv.get(self._pending_key(msg.from_phone), "pending")
        if pending:
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

                res = self.pg.reserve_class(
                    member_id=member_id,
                    class_id=class_id,
                    idempotency_key=idem,
                )
                self.conv.delete(self._pending_key(msg.from_phone), "pending")

                if (res or {}).get("ok", True):
                    body = self.tpl.render_named(
                        msg.tenant_id,
                        "reserve_class_confirmed",
                        lang,
                        {
                            "class_id": class_id,
                            "class_name": name,
                        },
                    
                    )

                    return [
                        Action(
                            "reply",
                            {
                                "to": msg.from_phone,
                                "body": body,
                                "tenant_id": msg.tenant_id,
                                "channel": msg.channel,
                                "channel_user_id": msg.channel_user_id,
                            },
                        )
                    ]
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "reserve_class_failed",
                    lang,
                    {},
                )
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]

            if text_lower in decline_words:
                # użytkownik odrzucił rezerwację
                self.conv.delete(self._pending_key(msg.from_phone), "pending")
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "reserve_class_declined",
                    lang,
                    {},
                )
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]
        text = (msg.body or "").strip()
        text_upper = text.upper()

        # 1) KOD:ABC123 z WhatsApp → mapowanie do konwersacji WWW
        if msg.channel == "whatsapp" and text_upper.startswith("KOD:"):
            code = text_upper.replace("KOD:", "").strip()

            # znajdź konwersację WWW z tym kodem
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
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": "whatsapp",
                            "channel_user_id": msg.from_phone,
                        },
                    )
                ]

            # wyszukaj członka w MembersIndex po numerze z WhatsApp
            member = self.members_index.get_member(msg.tenant_id, msg.from_phone)
            if not member:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "www_user_not_found",
                    lang,
                    {},
                )
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": "whatsapp",
                            "channel_user_id": msg.from_phone,
                        },
                    )
                ]

            member_id = member["id"]  # dopasuj do faktycznej struktury MembersIndex

            now_ts = int(time.time())
            ttl = now_ts + 30 * 60  # 30 minut weryfikacji dla WWW

            # update konwersacji WWW – podpinamy użytkownika PG
            self.conv.upsert_conversation(
                tenant_id=msg.tenant_id,
                channel=web_conv["channel"],
                channel_user_id=web_conv["channel_user_id"],
                pg_member_id=member_id,
                pg_verification_level="strong",
                pg_verified_until=ttl,
                verification_code=None,  # czyścimy kod
                state_machine_status=None,
            )

            body = self.tpl.render_named(
                msg.tenant_id,
                "www_verified",
                lang,
                {},
            )
            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": "whatsapp",
                        "channel_user_id": msg.from_phone,
                    },
                )
            ]

        # --- 2. Klasyfikacja intencji ---
        if msg.intent:
            # precomputed intent → pomijamy NLU, pewność "na sztywno"
            intent = msg.intent
            slots = msg.slots or {}
            confidence = 1.0
        else:
            nlu = self.nlu.classify_intent(msg.body, lang)
            
            # wynik NLU może być dict albo obiektem z atrybutami
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

        # --- 3. Zapisz info o rozmowie (intent, stan, język) ---
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
        
        # --- 4. Intent: greeting (powitanie) ---
        if intent == "greeting":
            body = self.tpl.render_named(
                msg.tenant_id,
                "greeting",
                lang,
                {},
            )
            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                )
            ]

        # --- 5. FAQ ---
        
        if intent == "faq":
            # 1) Pierwszy wybór: AI generuje odpowiedź na podstawie FAQ
            ai_body = self.kb.answer_ai(
                question=msg.body,
                tenant_id=msg.tenant_id,
                language_code=lang,
            )

            if ai_body:
                body = ai_body
            else:
                # 2) Fallback – stary mechanizm po topic
                topic = slots.get("topic", "hours")
                body = (
                    self.kb.answer(topic, tenant_id=msg.tenant_id, language_code=lang)
                    or self.tpl.render_named(
                        msg.tenant_id,
                        "faq_no_info",
                        lang,
                        {},
                    )
                )

            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                )
            ]

        # --- 6. Rezerwacja zajęć (PerfectGym) ---
        if intent == "reserve_class":
            class_id = (slots.get("class_id") or "").strip()
            member_id = (slots.get("member_id") or "").strip()

            # 5a) Brak class_id → pokaż listę zajęć z numerkami + zapisz do DDB
            if not class_id:
                pg = PerfectGymClient()
                classes_resp = pg.get_available_classes(top=10)
                classes = classes_resp.get("value") or []

                if not classes:
                    body = self.tpl.render_named(
                        msg.tenant_id,
                        "pg_available_classes_empty",
                        lang,
                        {},
                    )
                    return [
                        Action(
                            "reply",
                            {
                                "to": msg.from_phone,
                                "body": body,
                                "tenant_id": msg.tenant_id,
                                "channel": msg.channel,
                                "channel_user_id": msg.channel_user_id,
                            },
                        )
                    ]

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
                                {
                                    "free": free,
                                    "limit": attendees_limit,
                                },
                            )

                    # TU dodajemy index do szablonu, więc {index} w template się poprawnie zrenderuje
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

                # Zapis listy klas do późniejszego wyboru typu "1", "2", ...
                self.conv.put(
                    {
                        "pk": self._pending_key(msg.from_phone),
                        "sk": "classes",
                        "items": simplified,
                    }
                )

                # Ustawiamy stan, żeby następna wiadomość poleciała do _handle_class_selection
                self.conv.upsert_conversation(
                    tenant_id=msg.tenant_id,
                    channel=msg.channel or "whatsapp",
                    channel_user_id=msg.channel_user_id or msg.from_phone,
                    last_intent="pg_available_classes",
                    state_machine_status=STATE_AWAITING_CLASS_SELECTION,
                    language_code=lang,
                )

                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]


            # 6b) Mamy już class_id → standardowy flow z potwierdzeniem
            verify_resp = self._ensure_pg_verification(msg, conv, lang)
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
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]


            idem = new_id("idem-")
            self.conv.put(
                {
                    "pk": self._pending_key(msg.from_phone),
                    "sk": "pending",
                    "class_id": class_id,
                    "member_id": member_id,
                    "idempotency_key": idem,
                }
            )
            body = self.tpl.render_named(
                msg.tenant_id,
                "reserve_class_confirm",
                lang,
                {"class_id": class_id},
            )

            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                )
            ]



        # --- 7. Handover do człowieka ---
        if intent == "handover":
            self.conv.assign_agent(
                tenant_id=msg.tenant_id,
                channel=msg.channel or "whatsapp",
                channel_user_id=msg.channel_user_id or msg.from_phone,
                agent_id=slots.get("agent_id", "UNKNOWN"),   # np. przekazane w slots
            )
            body = self.tpl.render_named(
                msg.tenant_id,
                "handover_to_staff",
                lang,
                {},
            )
            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                        "language_code": lang,
                    },
                )
            ]
             
        # --- 8. Ticket do systemu ticketowego (Jira) ---
        if intent == "ticket":
            conv_key = msg.conversation_id or (msg.channel_user_id or msg.from_phone)

            history_items: list[dict] = []
            if hasattr(self, "messages") and self.messages:
                try:
                    history_items = self.messages.get_last_messages(
                        tenant_id=msg.tenant_id,
                        conv_key=conv_key,
                        limit=10,
                    ) or []
                except Exception:
                    history_items = []

            # zbuduj prosty tekst z historii
            history_lines = []
            for item in reversed(history_items):  # od najstarszych do najnowszych
                direction = item.get("direction", "?")
                body_item = item.get("body", "")
                history_lines.append(f"{direction}: {body_item}")

            history_block = "\n".join(history_lines) if history_lines else "(brak historii)"

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

            # KLUCZOWE: wywołujemy Jirę
            res = self.jira.create_ticket(
                summary=summary,
                description=description,
                tenant_id=msg.tenant_id,
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

            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                        "language_code": lang,
                    },
                )
            ]

        
        # --- 9. Lista dostępnych zajęć (PerfectGym) ---
        if intent == "pg_available_classes":
            pg = PerfectGymClient()
            classes_resp = pg.get_available_classes(top=10)
            classes = classes_resp.get("value") or []

            if not classes:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_available_classes_empty",
                    lang,
                    {},
                )
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]

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

            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                )
            ]

        # --- 10. Status kontraktu (PerfectGym) ---
        if intent == "pg_contract_status":
            verify_resp = self._ensure_pg_verification(msg, conv, lang)
            if verify_resp:
                return verify_resp

            email = (slots.get("email") or "").strip()
            if not email:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_contract_ask_email",
                    lang,
                    {},
                )
                return [
                     Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]

            # Numer telefonu z WhatsAppa (format 'whatsapp:+9665...')
            phone = msg.from_phone
            if phone.startswith("whatsapp:"):
                phone = phone.split(":", 1)[1]

            pg = PerfectGymClient()
            contracts_resp = pg.get_contracts_by_email_and_phone(
                email=email,
                phone_number=phone,
            )
            contracts = contracts_resp.get("value", []) or []

            if not contracts:
                body = self.tpl.render_named(
                    msg.tenant_id,
                    "pg_contract_not_found",
                    lang,
                    {
                        "email": email,
                        "phone": phone,
                    },
                )
                return [
                     Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]

            # Preferujemy bieżący kontrakt; jeśli brak – bierzemy pierwszy z listy.
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

            context = {
                "plan_name": plan_name,
                "status": status,
                # bool – template w danym języku sam decyduje jak go pokazać
                "is_active": is_active,
                "start_date": start_date,
                "end_date": end_date or "",
            }
            if membership_fee_gross is not None:
                context["membership_fee"] = membership_fee_gross


            body = self.tpl.render_named(
                msg.tenant_id,
                "pg_contract_details",
                lang,
                context,
            )

            return [
                 Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                )
            ]
        # --- 11. Saldo członkowskie (PerfectGym) ---
        if intent == "pg_member_balance":
            verify_resp = self._ensure_pg_verification(msg, conv, lang)
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
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": body,
                            "tenant_id": msg.tenant_id,
                            "channel": msg.channel,
                            "channel_user_id": msg.channel_user_id,
                        },
                    )
                ]

            pg = PerfectGymClient()
            balance_resp = pg.get_member_balance(member_id=member_id)
            balance = balance_resp.get("balance", 0)

            body = self.tpl.render_named(
                msg.tenant_id,
                "pg_member_balance",
                lang,
                {"balance": balance},
            )

            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": body,
                        "tenant_id": msg.tenant_id,
                        "channel": msg.channel,
                        "channel_user_id": msg.channel_user_id,
                    },
                )
            ]
        # --- 12. Domyślny clarify ---
        body = self.tpl.render_named(
            msg.tenant_id,
            "clarify_generic",
            lang,
            {},
        )
        return [
             Action(
                "reply",
                {
                    "to": msg.from_phone,
                    "body": body,
                    "tenant_id": msg.tenant_id,
                    "channel": msg.channel,
                    "channel_user_id": msg.channel_user_id,
                },
            )
        ]
