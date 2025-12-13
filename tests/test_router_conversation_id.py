import types
import pytest


def test_router_przekazuje_do_routingservice_conversation_id_z_body(monkeypatch):
    """
    Router powinien zbudować obiekt Message tak, aby:
    - jeżeli w payloadzie jest conversation_id -> trafia ono do Message.conversation_id
    - NIE podmieniać conversation_id na event_id, jeśli conversation_id jest obecne

    Test patchuje:
    - ROUTER.handle(...) -> przechwytujemy przekazany Message
    - _publish_actions(...) -> żeby nie wysyłać nic do SQS
    - MESSAGES.table.get_item/put_item -> żeby ominąć dynamo/idempotencję
    - MESSAGES.log_message -> żeby nic nie pisać do repo
    """
    from src.lambdas.message_router import handler as h

    captured = {}

    # 1) Patch: idempotencja w Dynamo (get_item/put_item) ma nie blokować testu
    monkeypatch.setattr(h.MESSAGES, "table", types.SimpleNamespace(
        get_item=lambda **kwargs: {},   # brak Item => "nie było jeszcze"
        put_item=lambda **kwargs: None, # no-op
    ))

    # 2) Patch: logowanie historii do MessagesRepo (no-op)
    monkeypatch.setattr(h.MESSAGES, "log_message", lambda **kwargs: None)

    # 3) Patch: _publish_actions (no-op), żeby nie wołać SQS
    monkeypatch.setattr(h, "_publish_actions", lambda actions, original_body: None)

    # 4) Patch: RoutingService.handle – przechwytujemy Message, nic nie robimy dalej
    def fake_handle(msg):
        captured["conversation_id"] = msg.conversation_id
        captured["tenant_id"] = msg.tenant_id
        captured["from_phone"] = msg.from_phone
        captured["channel_user_id"] = msg.channel_user_id
        return []  # brak akcji => nic nie pójdzie outbound

    monkeypatch.setattr(h.ROUTER, "handle", fake_handle)

    # Event jak z SQS (Records[*].body)
    event = {
        "Records": [
            {
                "body": (
                    '{"event_id":"evt-1",'
                    '"conversation_id":"conv#web#u1",'
                    '"tenant_id":"t1",'
                    '"from":"+48111111111",'
                    '"to":"+48222222222",'
                    '"body":"hej",'
                    '"channel":"web",'
                    '"channel_user_id":"u1"}'
                )
            }
        ]
    }

    resp = h.lambda_handler(event, context=types.SimpleNamespace())
    assert resp["statusCode"] == 200

    # Kluczowa asercja: conversation_id z payloadu musi przejść dalej 1:1
    assert captured["conversation_id"] == "conv#web#u1"
