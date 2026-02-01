import src.services.tenant_config_service as tcs


class FakeRepo:
    def __init__(self, item):
        self._item = item
        self.calls = 0

    def get(self, tenant_id: str):
        self.calls += 1
        return self._item


class FakeSSM:
    def __init__(self):
        self.calls = []

    def get_parameter(self, Name, WithDecryption):
        self.calls.append((Name, WithDecryption))
        return {"Parameter": {"Value": f"val:{Name}"}}


def test_tenant_config_expands_ssm_and_caches(monkeypatch):
    repo = FakeRepo({
        "tenant_id": "t1",
        "twilio": {"account_sid_param": "/tw/ac", "auth_token_param": "/tw/tok"},
        "jira": {"token_param": "/jira/tok"},
    })

    fake_ssm = FakeSSM()
    monkeypatch.setattr(tcs, "ssm_client", lambda: fake_ssm)

    svc = tcs.TenantConfigService(repo=repo, ttl_seconds=120)

    cfg1 = svc.get("t1")
    assert cfg1["twilio"]["account_sid"] == "val:/tw/ac"
    assert cfg1["twilio"]["auth_token"] == "val:/tw/tok"
    assert cfg1["jira"]["token"] == "val:/jira/tok"
    assert len(fake_ssm.calls) == 3

    # second call should hit cache (no extra SSM calls, no extra repo calls)
    cfg2 = svc.get("t1")
    assert cfg2["jira"]["token"] == "val:/jira/tok"
    assert len(fake_ssm.calls) == 3
    assert repo.calls == 1
