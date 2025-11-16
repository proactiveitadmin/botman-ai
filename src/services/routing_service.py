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
from ..common.utils import new_id

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

        # >>> TO MUSI TU BYĆ <<<
        from ..services.metrics_service import MetricsService
        self.metrics = MetricsService()

        # Jeśli używasz MembersIndexRepo i JiraClient:
        from ..adapters.jira_client import JiraClient
        from ..storage.ddb import MembersIndexRepo
        self.jira = JiraClient()
        self.members_index = MembersIndexRepo()


    def _pending_key(self, phone: str) -> str:
        """
        Buduje klucz pod którym trzymamy w DDB oczekującą rezerwację dla danego numeru telefonu.
        """
        return f"pending#{phone}"

    def handle(self, msg: Message) -> List[Action]:
        """
        Przetwarza pojedynczą wiadomość biznesową i zwraca listę akcji do wykonania.

        Zwraca zwykle jedną akcję typu "reply", ale architektura pozwala na wiele akcji w przyszłości.
        """
        text = (msg.body or "").strip().lower()

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
        nlu = self.nlu.classify_intent(msg.body, lang="pl")
        intent = nlu.get("intent", "clarify")
        slots = nlu.get("slots", {}) or {}

        self.metrics.incr("intent_detected", intent=intent, tenant=msg.tenant_id)

        # --- 3. FAQ ---
        if intent == "faq":
            topic = slots.get("topic", "hours")
            answer = (
                self.kb.answer(topic, tenant_id=msg.tenant_id)
                or "Przepraszam, nie mam informacji."
            )
            return [Action("reply", {"to": msg.from_phone, "body": answer})]

        # --- 4. Rezerwacja zajęć ---
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
            return [Action("reply", {"to": msg.from_phone, "body": body})]


        # --- 5. Handover do człowieka ---
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
            
        # --- 5. Ticket do systemu ticketowego(Jira) ---   
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
            
        # --- 6. Domyślny clarify ---
        return [
            Action(
                "reply",
                {
                    "to": msg.from_phone,
                    "body": "Czy możesz doprecyzować, w czym pomóc?",
                },
            )
        ]
