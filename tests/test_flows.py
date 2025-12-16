import json
import boto3
import pytest
import re


from src.lambdas.outbound_sender import handler as outbound_handler
from src.lambdas.message_router import handler as router_handler
import src.services.template_service as template_service

# --- TABLICA SZABLONÓW W STYLU DDB (klucz = (template_code, language_code)) ---
DUMMY_TEMPLATES = {
    ("handover_to_staff", "pl"): {
        "body": "Łączę Cię z pracownikiem klubu (wkrótce stałe przełączenie).",
        "placeholders": [],
    },
    ("ticket_summary", "pl"): {
        "body": "Zgłoszenie klienta",
        "placeholders": [],
    },
    ("ticket_created_ok", "pl"): {
        "body": "Utworzyłem zgłoszenie. Numer: %{ticket}.",
        "placeholders": ["ticket"],
    },
    ("ticket_created_failed", "pl"): {
        "body": "Nie udało się utworzyć zgłoszenia. Spróbuj później.",
        "placeholders": [],
    },
    ("clarify_generic", "pl"): {
        "body": "Czy możesz doprecyzować, w czym pomóc?",
        "placeholders": [],
    },
    ("crm_available_classes", "pl"): {
        "body": "Najbliższe zajęcia:\n{classes}",
        "placeholders": ["classes"],
    },
    ("crm_available_classes_empty", "pl"): {
        "body": "Aktualnie nie widzę dostępnych zajęć w grafiku.",
        "placeholders": [],
    },
    ("crm_available_classes_capacity_no_limit", "pl"): {
        "body": "bez limitu miejsc",
        "placeholders": [],
    },
    ("crm_available_classes_capacity_full", "pl"): {
        "body": "brak wolnych miejsc (limit {limit})",
        "placeholders": ["limit"],
    },
    ("crm_available_classes_capacity_free", "pl"): {
        "body": "{free} wolnych miejsc (limit {limit})",
        "placeholders": ["free", "limit"],
    },
    ("crm_available_classes_item", "pl"): {
        "body": "{date} {time} – {name} ({capacity})",
        "placeholders": ["date", "time", "name", "capacity"],
    },
    ("crm_challenge_success", "pl"): {
        "body": "Weryfikacja zakończona sukcesem. Możemy kontynuować.",
        "placeholders": [],
    },
    ("crm_contract_ask_email", "pl"): {
        "body": "Podaj proszę adres e-mail użyty w klubie, żebym mógł sprawdzić status Twojej umowy.",
        "placeholders": [],
    },
    ("crm_contract_not_found", "pl"): {
        "body": "Nie widzę żadnej umowy powiązanej z adresem {email} i numerem {phone}. Upewnij się proszę, że dane są zgodne z PerfectGym.",
        "placeholders": ["email", "phone"],
    },
    ("crm_contract_details", "pl"): {
        "body": (
            "Szczegóły Twojej umowy:\n"
            "Plan: {plan_name}\n"
            "Status:\n{status}\n"
            "Aktywna: {is_active, select, true{tak} false{nie}}\n"
            "Start: {start_date}\n"
            "Koniec: {end_date}\n"
            "Opłata członkowska: {membership_fee}"
        ),
        "placeholders": [
            "plan_name",
            "status",
            "is_active",
            "start_date",
            "end_date",
            "membership_fee",
        ],
    },
    ("reserve_class_confirmed", "pl"): {
        "body": "Zarezerwowano zajęcia (ID {class_id}). Do zobaczenia!",
        "placeholders": ["class_id"],
    },
    ("reserve_class_failed", "pl"): {
        "body": "Nie udało się zarezerwować. Spróbuj ponownie później.",
        "placeholders": [],
    },
    ("reserve_class_declined", "pl"): {
        "body": (
            "Anulowano rezerwację. Daj znać, jeżeli będziesz chciał/chciała "
            "zarezerwować inne zajęcia."
        ),
        "placeholders": [],
    },
    ("www_not_verified", "pl"): {
        "body": "Nie znaleziono aktywnej weryfikacji dla tego kodu.",
        "placeholders": [],
    },
    ("www_user_not_found", "pl"): {
        "body": "Nie znaleziono członkostwa powiązanego z tym numerem.",
        "placeholders": [],
    },
    ("www_verified", "pl"): {
        "body": "Twoje konto zostało zweryfikowane. Możesz wrócić do czatu WWW.",
        "placeholders": [],
    },
    ("crm_web_verification_required", "pl"): {
        "body": (
            "Aby kontynuować, musimy potwierdzić Twoją tożsamość.\n\n"
            "Jeśli korzystasz z czatu WWW, kliknij poniższy link, aby otworzyć "
            "WhatsApp i wysłać kod weryfikacyjny.\nJeśli jesteś już w WhatsApp, "
            "wystarczy że wyślesz poniższy kod.\n\n"
            "Kod: {verification_code}\n"
            "Link: {whatsapp_link}\n\n"
            "Po wysłaniu kodu wróć do rozmowy – zweryfikujemy Twoje konto i "
            "odblokujemy dostęp do danych PerfectGym."
        ),
        "placeholders": ["verification_code", "whatsapp_link"],
    },
    ("faq_no_info", "pl"): {
        "body": "Przepraszam, nie mam informacji.",
        "placeholders": [],
    },
    ("reserve_class_confirm", "pl"): {
        "body": "Czy potwierdzasz rezerwację zajęć {class_id}? Odpowiedz: TAK lub NIE.",
        "placeholders": ["class_id"],
    },
    # Tu ważne: traktujemy body jako listę słów rozdzieloną przecinkami,
    # bo _get_words_set pewnie robi split po przecinku / białych znakach
    ("reserve_class_confirm_words", "pl"): {
        "body": "tak, tak., potwierdzam, ok, zgadzam się, oczywiście, pewnie, jasne",
        "placeholders": [],
    },
    ("reserve_class_decline_words", "pl"): {
        "body": "nie, nie., anuluj, rezygnuję, rezygnuje, ne",
        "placeholders": [],
    },
      ("crm_code_via_email", "pl"): {
        "body": (
            "Twój kod weryfikacyjny to: {verification_code}\n\n"
            "Ważny {ttl_minutes} minut."
        ),
        "placeholders": ["verification_code", "ttl_minutes"],
    },
}
class DummyMembersIndex:
    """
    Minimalny fake MembersIndexRepo na potrzeby testów flow:
    zawsze zwraca jednego członka z id '105'.
    """
    def get_member(self, tenant_id, phone):
        return {"id": "105"}

class DummyCRM:
    """
    Prosty CRM na potrzeby testów flowów:
    - nie gada z PerfectGym,
    - akceptuje DOB challenge dla konkretnej daty,
    - rezerwacja zajęć zawsze się udaje.
    """

    def __init__(self):
        self.reserve_calls: list[dict] = []
        self.verify_calls: list[dict] = []

    def get_available_classes(
        self,
        tenant_id: str,
        club_id: int | None = None,
        from_iso: str | None = None,
        to_iso: str | None = None,
        member_id: int | None = None,
        fields: list[str] | None = None,
        top: int | None = None,
    ) -> dict:
        # Jeśli w danym teście potrzebujesz listy zajęć – możesz tu dorobić logikę.
        # W wielu testach flow i tak idziesz "na skróty" z class_id w slots,
        # więc może w ogóle nie zostać wywołane.
        return {"value": []}

    def reserve_class(
        self,
        tenant_id: str,
        member_id: str,
        class_id: str,
        idempotency_key: str,
    ) -> dict:
        self.reserve_calls.append(
            {
                "tenant_id": tenant_id,
                "member_id": member_id,
                "class_id": class_id,
                "idem": idempotency_key,
            }
        )
        return {"ok": True}

    def get_contracts_by_email_and_phone(
        self,
        tenant_id: str,
        email: str,
        phone_number: str,
    ) -> dict:
        return {"value": []}

    def get_member_balance(
        self,
        tenant_id: str,
        member_id: int,
    ) -> dict:
        return {"balance": 0}

    def verify_member_challenge(
        self,
        tenant_id: str,
        phone: str,
        challenge_type: str,
        answer: str,
    ) -> bool:
        """
        Używane przez CRMFlowService._verify_challenge_answer.

        W testach chcemy, żeby challenge DOB przeszedł, jeśli użytkownik poda
        konkretną datę, np. 01-05-1990 (z różnymi separatorami).
        """
        self.verify_calls.append(
            {
                "tenant_id": tenant_id,
                "phone": phone,
                "challenge_type": challenge_type,
                "answer": answer,
            }
        )

        if challenge_type != "dob":
            return False

        norm = (answer or "").strip().replace(".", "-").replace("/", "-")
        return norm == "01-05-1990"
        
    def get_member_by_phone(self, tenant_id: str, phone: str) -> dict:
        return {"id": "105"}


class DummyTemplatesRepo:
    """
    Zgodne z TemplatesRepo, ale w pełni in-memory i deterministyczne.
    """

    def get_template(self, tenant_id, template_code, language_code):
        return DUMMY_TEMPLATES.get((template_code, language_code))


# --- patch TemplatesRepo w template_service ---
@pytest.fixture(autouse=True)
def patch_templates_repo(monkeypatch):
    monkeypatch.setattr(template_service, "TemplatesRepo", lambda: DummyTemplatesRepo())

@pytest.fixture
def router(monkeypatch):
    """
    Import ROUTER dopiero tutaj + podmień TemplatesRepo
    """

    dummy_repo = DummyTemplatesRepo()

    for tpl in (router_handler.ROUTER.tpl, router_handler.ROUTER.crm_flow.tpl):
        for attr in ("repo", "_repo", "templates_repo"):
            if hasattr(tpl, attr):
                monkeypatch.setattr(tpl, attr, dummy_repo, raising=False)

    return router_handler
    
def _read_all_messages(queue_url: str, max_msgs: int = 10):
    """
    Pomocniczo – czytamy wiadomości z kolejki (Moto SQS).
    Uwaga: WaitTimeSeconds=0 żeby nie blokować testów.
    """
    sqs = boto3.client("sqs", region_name="eu-central-1")
    resp = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max_msgs,
        WaitTimeSeconds=0,
    )
    return resp.get("Messages", [])

@pytest.fixture(autouse=True)
def purge_queues_before_flow_tests(aws_stack):
    """
    Czyścimy outbound (i ewentualnie inbound) przed każdym testem flow,
    żeby nie widzieć wiadomości z innych testów.
    """
    sqs = boto3.client("sqs", region_name="eu-central-1")
    for url in aws_stack.values():
        sqs.purge_queue(QueueUrl=url)
        
def test_faq_flow_to_outbound_queue(aws_stack, mock_ai, monkeypatch):
    
    outbound_url = aws_stack["outbound"]

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-1",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "Godziny otwarcia",
                        "tenant_id": "default",
                    }
                )
            }
        ]
    }

    router_handler.lambda_handler(event, None)

    msgs = _read_all_messages(outbound_url)
    assert len(msgs) >= 1  # może być więcej, bo inne testy też mogły coś dodać

    payloads = [json.loads(m["Body"]) for m in msgs]

    faq_msgs = [
        p
        for p in payloads
        if p.get("to") == "whatsapp:+48123123123"
        and (
            "godzin" in p.get("body", "").lower()
            or "otwar" in p.get("body", "").lower()
            or "opening hours" in p.get("body", "").lower()
            or "not yet provided" in p.get("body", "").lower()
        )
    ]

    assert faq_msgs, (
        "Nie znaleziono odpowiedzi FAQ w wiadomościach: "
        f"{[p.get('body') for p in payloads]}"
    )
  
def test_ticket_flow_sends_confirmation_to_outbound_queue(aws_stack, monkeypatch):
    """
    Sprawdzamy, że przy intencie 'ticket' bot:
    - woła JiraClient.create_ticket,
    - wysyła do użytkownika odpowiedź z szablonu 'ticket_created_ok'.
    """
    outbound_url = aws_stack["outbound"]


    class DummyTicketing:
        def __init__(self):
            self.calls = []

        def create_ticket(self, tenant_id, summary, description, meta=None):
            self.calls.append(
                {
                    "tenant_id": tenant_id,
                    "summary": summary,
                    "description": description,
                    "meta": meta or {},
                }
            )
            # RoutingService oczekuje dict-a z kluczem 'ticket' lub 'key'
            return {"ticket": "ABC-123"}

    dummy_ticketing = DummyTicketing()
    router_handler.ROUTER.ticketing = dummy_ticketing

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-ticket-1",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "Chcę zgłosić problem z karnetem",
                        "tenant_id": "default",
                        # ustawiamy intent 'ticket', żeby pominąć NLU
                        "intent": "ticket",
                        "slots": {
                            "summary": "Problem z karnetem",
                            # description zostawiamy routerowi – on umie zbudować z historii
                        },
                    }
                )
            }
        ]
    }

    # Uruchamiamy router
    router_handler.lambda_handler(event, None)

    # Sprawdzamy, że TicketingService zostało zawołane
    assert dummy_ticketing.calls, "TicketingService.create_ticket powinno zostać wywołane"

    # Czytamy wiadomości z kolejki outbound
    msgs = _read_all_messages(outbound_url, max_msgs=10)
    assert msgs, "Brak jakichkolwiek wiadomości w kolejce outbound po utworzeniu ticketa"

    payloads = [json.loads(m["Body"]) for m in msgs]

    # Szukamy odpowiedzi do użytkownika z numerem ticketa
    ticket_msgs = [
        p
        for p in payloads
        if p.get("to") == "whatsapp:+48123123123"
        and (
            "utworzyłem zgłoszenie" in (p.get("body") or "").lower()
            or "numer: " in (p.get("body") or "").lower()
            or "ticket_created_ok" in (p.get("body") or "")
        )
    ]

    assert ticket_msgs, (
        "Nie znaleziono wiadomości potwierdzającej utworzenie zgłoszenia.\n"
        f"Wiadomości w kolejce: {[p.get('body') for p in payloads]}"
    )

    # Dla pewności – sprawdzamy, że numer ticketa (ABC-123) pojawił się w treści
    assert any("ABC-123" in (p.get("body") or "") for p in ticket_msgs)


def test_reservation_flow_with_email_otp(aws_stack, mock_ai, mock_pg, monkeypatch, router):
    outbound_url = aws_stack["outbound"]
    router_handler = router  # fixture z poprawnym repo templates

    # CRM z emailem
    class DummyCRMWithEmail:
        def get_member_by_phone(self, tenant_id, phone):
            return {"value": [{"id": "123", "email": "user@example.com"}]}

        def verify_member_challenge(self, *args, **kwargs):
            return True

    monkeypatch.setattr(router_handler.ROUTER.crm_flow, "crm", DummyCRMWithEmail(), raising=False)
    monkeypatch.setattr(router_handler.ROUTER.language, "_detect_language", lambda text: "pl")

    # przechwyt maila i wyciągnij 6 cyfr
    sent = {"to": None, "subject": None, "body": None, "code": None}

    def fake_send_otp(self, *args, **kwargs):
        to_email = kwargs.get("to_email") or (args[0] if len(args) > 0 else None)
        subject = kwargs.get("subject") or (args[1] if len(args) > 1 else None)
        body_text = kwargs.get("body_text") or (args[2] if len(args) > 2 else "")

        sent["to"] = to_email
        sent["subject"] = subject
        sent["body"] = body_text or ""

        m = re.search(r"\b([A-Z0-9]{6})\b", sent["body"])
        assert m, f"Nie znaleziono 6-cyfrowego kodu w body email:\n{sent['body']}"
        sent["code"] = m.group(1)
        return True

    monkeypatch.setattr("src.services.crm_flow_service.EmailClient.send_otp", fake_send_otp, raising=True)

    # 1) start flow
    event1 = {
        "Records": [
            {"body": json.dumps({
                "event_id": "evt-2",
                "from": "whatsapp:+48123123123",
                "to": "whatsapp:+48000000000",
                "body": "Chcę się zapisać na zajęcia",
                "tenant_id": "default",
            })}
        ]
    }
    router_handler.lambda_handler(event1, None)

    assert sent["to"] == "user@example.com"
    assert sent["code"], "Nie przechwycono kodu OTP z emaila"

    msgs_1 = _read_all_messages(outbound_url, max_msgs=10)
    payloads_1 = [json.loads(m["Body"]) for m in msgs_1]
    assert any(
        p.get("to") == "whatsapp:+48123123123" and
        ("kod" in (p.get("body") or "").lower() or "crm_challenge_ask_email_code" in (p.get("body") or ""))
        for p in payloads_1
    ), f"Brak prośby o kod. Outbound: {[p.get('body') for p in payloads_1]}"

    # 2) user wpisuje kod
    event2 = {
        "Records": [
            {"body": json.dumps({
                "event_id": "evt-3",
                "from": "whatsapp:+48123123123",
                "to": "whatsapp:+48000000000",
                "body": sent["code"],
                "tenant_id": "default",
            })}
        ]
    }
    router_handler.lambda_handler(event2, None)

    msgs_2 = _read_all_messages(outbound_url, max_msgs=10)
    payloads_2 = [json.loads(m["Body"]) for m in msgs_2]
    assert any(
        p.get("to") == "whatsapp:+48123123123" and
        ("crm_challenge_success" in (p.get("body") or "") or "weryfikacj" in (p.get("body") or "").lower())
        for p in payloads_2
    ), f"Brak sukcesu. Outbound: {[p.get('body') for p in payloads_2]}"
