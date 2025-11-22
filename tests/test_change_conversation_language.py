from src.services.routing_service import RoutingService
from src.domain.models import Message


class DummyConversationsRepo:
    def __init__(self):
        self.last_set_language = None

    def set_language(self, tenant_id: str, phone: str, language_code: str):
        # zapamiętujemy wywołanie, żeby test mógł to assercikować
        self.last_set_language = (tenant_id, phone, language_code)
        # opcjonalnie zwracamy coś podobnego do prawdziwego repo
        return {
            "pk": f"conv#{tenant_id}#{phone}",
            "tenant_id": tenant_id,
            "phone": phone,
            "language_code": language_code,
        }

def test_change_conversation_language_calls_repo():
    conv_repo = DummyConversationsRepo()

    svc = RoutingService()
    svc.conv = conv_repo  # podmieniamy repo rozmów na naszego dummya

    msg = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="zmień język na en",
    )

    # UŻYWAMY właściwej metody + właściwej sygnatury
    result = svc.change_conversation_language(msg.tenant_id, msg.from_phone, "en")

    # sprawdzamy, że repo zostało wywołane z odpowiednimi argumentami
    assert conv_repo.last_set_language == (msg.tenant_id, msg.from_phone, "en")