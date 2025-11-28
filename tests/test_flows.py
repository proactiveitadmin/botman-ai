import json
import boto3
import pytest

from src.lambdas.message_router import handler as router_handler
from src.lambdas.outbound_sender import handler as outbound_handler
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
    ("pg_available_classes", "pl"): {
        "body": "Najbliższe zajęcia:\n{classes}",
        "placeholders": ["classes"],
    },
    ("pg_available_classes_empty", "pl"): {
        "body": "Aktualnie nie widzę dostępnych zajęć w grafiku.",
        "placeholders": [],
    },
    ("pg_available_classes_capacity_no_limit", "pl"): {
        "body": "bez limitu miejsc",
        "placeholders": [],
    },
    ("pg_available_classes_capacity_full", "pl"): {
        "body": "brak wolnych miejsc (limit {limit})",
        "placeholders": ["limit"],
    },
    ("pg_available_classes_capacity_free", "pl"): {
        "body": "{free} wolnych miejsc (limit {limit})",
        "placeholders": ["free", "limit"],
    },
    ("pg_available_classes_item", "pl"): {
        "body": "{date} {time} – {name} ({capacity})",
        "placeholders": ["date", "time", "name", "capacity"],
    },
    ("pg_contract_ask_email", "pl"): {
        "body": "Podaj proszę adres e-mail użyty w klubie, żebym mógł sprawdzić status Twojej umowy.",
        "placeholders": [],
    },
    ("pg_contract_not_found", "pl"): {
        "body": "Nie widzę żadnej umowy powiązanej z adresem {email} i numerem {phone}. Upewnij się proszę, że dane są zgodne z PerfectGym.",
        "placeholders": ["email", "phone"],
    },
    ("pg_contract_details", "pl"): {
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
    ("pg_web_verification_required", "pl"): {
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
}



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


@pytest.fixture(autouse=True)
def patch_templates_repo(monkeypatch):
    monkeypatch.setattr(template_service, "TemplatesRepo", lambda: DummyTemplatesRepo())

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

def test_reservation_flow_with_confirmation(aws_stack, mock_ai, mock_pg, monkeypatch):
    outbound_url = aws_stack["outbound"]

    # 1. Wiadomość "chcę się zapisać"
    event1 = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-2",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "Chcę się zapisać na zajęcia",
                        "tenant_id": "default",
                    }
                )
            }
        ]
    }
    router_handler.lambda_handler(event1, None)

    # Czytamy z kolejki – może być więcej wiadomości, więc filtrujemy
    msgs_1 = _read_all_messages(outbound_url, max_msgs=10)
    assert msgs_1, "Brak jakichkolwiek wiadomości po pierwszym kroku rezerwacji"

    payloads_1 = [json.loads(m["Body"]) for m in msgs_1]

    confirm_msgs = [
        p
        for p in payloads_1
        if p.get("to") == "whatsapp:+48123123123"
        and (
            "potwierdzasz rezerwacj" in p.get("body", "").lower()
            or "reserve_class_confirm" in p.get("body", "")
        )
    ]

    assert confirm_msgs, (
        "Nie znaleziono wiadomości z prośbą o potwierdzenie rezerwacji.\n"
        f"Wiadomości w kolejce: {[p.get('body') for p in payloads_1]}"
    )


    # 2. Potwierdzenie "TAK"
    event2 = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-3",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "tak",
                        "tenant_id": "default",
                    }
                )
            }
        ]
    }
    router_handler.lambda_handler(event2, None)

    msgs_2 = _read_all_messages(outbound_url, max_msgs=10)
    assert msgs_2, "Brak jakichkolwiek wiadomości po potwierdzeniu rezerwacji"

    payloads_2 = [json.loads(m["Body"]) for m in msgs_2]
    confirm_ok_msgs = [
        p
        for p in payloads_2
        if p.get("to") == "whatsapp:+48123123123"
        and (
            "zarezerwowa" in p.get("body", "").lower()
            or "rezerwacja potwierdzona" in p.get("body", "").lower()
            or "reserve_class_confirmed" in p.get("body", "")   # <- nowy wariant
        )
    ]

    assert confirm_ok_msgs, (
        "Nie znaleziono wiadomości potwierdzającej rezerwację.\n"
        f"Wiadomości w kolejce: {[p.get('body') for p in payloads_2]}"
    )

def test_clarify_flow_when_intent_unknown(aws_stack, mock_ai, monkeypatch):
    outbound_url = aws_stack["outbound"]

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-4",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "asdfasdfasdf",  # przypadkowy tekst → intent=clarify
                        "tenant_id": "default",
                    }
                )
            }
        ]
    }

    # Uruchamiamy router
    router_handler.lambda_handler(event, None)

    # Czytamy wiadomości z kolejki (może być ich kilka!)
    msgs = _read_all_messages(outbound_url, max_msgs=10)
    assert msgs, f"Brak jakichkolwiek wiadomości w kolejce outbound: {msgs}"

    payloads = [json.loads(m["Body"]) for m in msgs]

    # Szukamy odpowiedzi clarify
    clarify = [
        p for p in payloads
        if "doprec" in p.get("body", "").lower()  # obsługuje doprecyzuj / doprecyzować
        and p.get("to") == "whatsapp:+48123123123"
    ]

    clarify = [
        p for p in payloads
        if "clarify" in p.get("body", "").lower()
        and p.get("to") == "whatsapp:+48123123123"
    ]




def test_outbound_sender_uses_twilio_client(mock_twilio):
    event = {
        "Records": [
            {"body": json.dumps({"to": "whatsapp:+48123123123", "body": "Hej z testu!"})}
        ]
    }

    outbound_handler.lambda_handler(event, None)

    assert len(mock_twilio) == 1
    assert mock_twilio[0]["to"] == "whatsapp:+48123123123"
    assert "Hej z testu!" in mock_twilio[0]["body"]
