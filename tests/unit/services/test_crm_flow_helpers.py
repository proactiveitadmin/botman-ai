import src.services.crm_flow_service as cfs


class FakeTpl:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def render_named(self, tenant_id, template_name, lang, context):
        self.calls.append((tenant_id, template_name, lang))
        return self.mapping.get((tenant_id, template_name, lang), "")


class FakeCRM:
    pass


class FakeConv:
    pass


class FakeMembersIndex:
    pass


def test_get_words_set_splits_and_caches(monkeypatch):
    # Avoid instantiating real ClientsFactory (would pull AWS deps in unit tests).
    monkeypatch.setattr(cfs, "ClientsFactory", lambda *a, **k: object())
    tpl = FakeTpl({("t1", "yes_words", "pl"): "TAK,  yes ; ok"})
    svc = cfs.CRMFlowService(crm=FakeCRM(), tpl=tpl, conv=FakeConv(), members_index=FakeMembersIndex())

    words1 = svc._get_words_set("t1", "yes_words", "pl")
    assert words1 == {"tak", "yes", "ok"}

    words2 = svc._get_words_set("t1", "yes_words", "pl")
    assert words2 == words1
    # Second call should hit cache.
    assert tpl.calls.count(("t1", "yes_words", "pl")) == 1


def test_generate_verification_code_length(monkeypatch):
    monkeypatch.setattr(cfs, "ClientsFactory", lambda *a, **k: object())
    svc = cfs.CRMFlowService(crm=FakeCRM(), tpl=FakeTpl({}), conv=FakeConv(), members_index=FakeMembersIndex())

    # Make generation deterministic.
    import secrets
    monkeypatch.setattr(secrets, "choice", lambda _alphabet: "A")
    assert svc._generate_verification_code(8) == "A" * 8
