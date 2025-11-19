"""
Główny serwis routujący wiadomości użytkowników.

Na podstawie wyniku NLU decyduje, czy:
- odpowiedzieć z FAQ,
- zaproponować rezerwację zajęć,
- przekazać sprawę do człowieka (handover),
- dopytać użytkownika (clarify).
"""

from typing import List

from ..domain.models import Message, Action
from ..services.nlu_service import NLUService
from ..services.kb_service import KBService
from ..services.template_service import TemplateService
from ..adapters.perfectgym_client import PerfectGymClient
from ..storage.ddb import ConversationsRepo
from ..storage.tenants_repo import TenantsRepo
from ..common.utils import new_id
from ..services.metrics_service import MetricsService        
from ..adapters.jira_client import JiraClient
from ..storage.ddb import MembersIndexRepo
from ..common.config import settings

# Zestaw słów oznaczających potwierdzenie rezerwacji.
CONFIRM_WORDS = {"tak", "tak.", "potwierdzam", "ok"}

# Zestaw słów oznaczających odrzucenie rezerwacji.
DECLINE_WORDS = {"nie", "nie.", "anuluj", "rezygnuję", "rezygnuje"}

CONFIRM_TEMPLATE = "Czy potwierdzasz rezerwację zajęć {class_id}? Odpowiedz: TAK lub NIE."

class RoutingService:
    """
    Serwis łączący NLU, KB i integracje zewnętrzne tak, by obsłużyć pełen flow rozmowy.
    """
    def __init__(self) -> None:
        self.nlu = NLUService()
        self.kb = KBService()
        self.tpl = TemplateService()
        self.pg = PerfectGymClient()
        self.conv = ConversationsRepo()
        self.tenants = TenantsRepo()
        self.metrics = MetricsService()
        self.jira = JiraClient()
        self.members_index = MembersIndexRepo()


    def _pending_key(self, phone: str) -> str:
        """
        Buduje klucz pod którym trzymamy w DDB oczekującą rezerwację dla danego numeru telefonu.
        """
        return f"pending#{phone}"

    def _resolve_and_persist_language(self, msg: Message) -> str:
        # 1. Czy mamy już conversation z językiem?
        existing = self.conv.get_conversation(msg.tenant_id, msg.from_phone)
        if existing and existing.get("language_code"):
            return existing["language_code"]

        # 2. Tenant
        tenant = self.tenants.get(msg.tenant_id) or {}
        lang = tenant.get("language_code") or settings.get_default_language()

        # 3. Zapis/aktualizacja rozmowy
        self.conv.upsert_conversation(
            msg.tenant_id,
            msg.from_phone,
            language_code=lang,
            last_intent=None,
            state_machine_status=None,
        )
        return lang

    def change_conversation_language(self, tenant_id: str, phone: str, new_lang: str) -> dict:
        """Metoda użyteczna na przyszłość (panel konsultanta)."""
        return self.conv.set_language(tenant_id, phone, new_lang)

    def handle(self, msg: Message) -> List[Action]:
        """
        Przetwarza pojedynczą wiadomość biznesową i zwraca listę akcji do wykonania.

        Zwraca zwykle jedną akcję typu "reply", ale architektura pozwala na wiele akcji w przyszłości.
        """
        text = (msg.body or "").strip().lower()
        # --- ustalenie języka rozmowy ---
        lang = self._resolve_and_persist_language(msg)

        # --- 1. Obsługa oczekującej rezerwacji (TAK/NIE) ---
        pending = self.conv.get(self._pending_key(msg.from_phone))
        if pending:
            if text in CONFIRM_WORDS:
                class_id = pending.get("class_id")
                member_id = pending.get("member_id")
                idem = pending.get("idempotency_key")

                res = self.pg.reserve_class(
                    member_id=member_id,
                    class_id=class_id,
                    idempotency_key=idem,
                )
                self.conv.delete(self._pending_key(msg.from_phone))

                if (res or {}).get("ok", True):
                    return [
                        Action(
                            "reply",
                            {
                                "to": msg.from_phone,
                                "body": f"Zarezerwowano zajęcia (ID {class_id}). Do zobaczenia!",
                            },
                        )
                    ]
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": "Nie udało się zarezerwować. Spróbuj ponownie później.",
                        },
                    )
                ]

            if text in DECLINE_WORDS:
                # użytkownik odrzucił rezerwację
                self.conv.delete(self._pending_key(msg.from_phone))
                return [
                    Action(
                        "reply",
                        {
                            "to": msg.from_phone,
                            "body": (
                                "Anulowano rezerwację. Daj znać, jeżeli będziesz chciał/chciała "
                                "zarezerwować inne zajęcia."
                            ),
                        },
                    )
                ]
            # Jeżeli jest pending, ale wiadomość nie jest ani TAK ani NIE –
            # traktujemy ją jako nowe zapytanie i NIE kasujemy pending.

        # --- 2. Klasyfikacja intencji ---
        nlu = self.nlu.classify_intent(msg.body, lang=lang)
        intent = nlu.get("intent", "clarify")
        slots = nlu.get("slots", {}) or {}

        self.metrics.incr("intent_detected", intent=intent, tenant=msg.tenant_id)
        
        # --- 3. Zapisz info o rozmowie (intent, stan, język) ---
        self.conv.upsert_conversation(
            msg.tenant_id,
            msg.from_phone,
            last_intent=intent,
            state_machine_status=(
                "awaiting_confirmation" 
                if intent == "reserve_class" 
                else None
            ),
            language_code=lang,
        )
        
        # --- 4. FAQ ---
        if intent == "faq":
            topic = slots.get("topic", "hours")
            answer = (
                self.kb.answer(topic, tenant_id=msg.tenant_id, language_code=lang)
                or "Przepraszam, nie mam informacji."
            )
            return [Action("reply", {"to": msg.from_phone, "body": answer})]

        # --- 5. Rezerwacja zajęć ---
        if intent == "reserve_class":
            class_id = slots.get("class_id", "101")
            member_id = slots.get("member_id", "105")
            idem = new_id("idem-")
            self.conv.put(
                {
                    "pk": self._pending_key(msg.from_phone),
                    "class_id": class_id,
                    "member_id": member_id,
                    "idempotency_key": idem,
                }
            )
            body = self.tpl.render(CONFIRM_TEMPLATE, {"class_id": class_id})
            # w przyszłości -> self.tpl.render_named(msg.tenant_id, "reserve_confirm", lang, {...})
            return [Action("reply", {"to": msg.from_phone, "body": body})]


        # --- 6. Handover do człowieka ---
        if intent == "handover":
            return [
                Action(
                    "reply",
                    {
                        "to": msg.from_phone,
                        "body": "Łączę Cię z pracownikiem klubu (wkrótce stałe przełączenie).",
                    },
                )
            ]
            
        # --- 7. Ticket do systemu ticketowego(Jira) ---   
        if intent == "ticket":
            res = self.jira.create_ticket(
                summary=slots.get("summary") or "Zgłoszenie klienta",
                description=slots.get("description") or msg.body,
                tenant_id=msg.tenant_id
            )
            if res.get("ok"):
                body = f"Utworzyłem zgłoszenie. Numer: {res['ticket']}."
            else:
                body = "Nie udało się utworzyć zgłoszenia. Spróbuj później."
            return [Action("reply", {"to": msg.from_phone, "body": body})]
            
        # --- 8. Domyślny clarify ---
        return [
            Action(
                "reply",
                {
                    "to": msg.from_phone,
                    "body": "Czy możesz doprecyzować, w czym pomóc?",
                },
            )
        ]
