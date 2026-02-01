import src.services.clients_factory as cf


class FakeTenantCfg:
    def __init__(self, cfg):
        self.cfg = cfg
        self.calls = []

    def get(self, tenant_id: str):
        self.calls.append(tenant_id)
        return self.cfg.get(tenant_id, {})


class FakeTwilio:
    def __init__(self, enabled=True):
        self.enabled = enabled

    @classmethod
    def from_tenant_config(cls, cfg):
        return cls(enabled=True)


class FakeCloud:
    def __init__(self, enabled=True):
        self.enabled = enabled

    @classmethod
    def from_tenant_config(cls, cfg):
        # enable if token present
        return cls(enabled=bool(cfg.get("cloud")))


def test_whatsapp_sender_selection_and_caching(monkeypatch):
    monkeypatch.setattr(cf, "TwilioClient", FakeTwilio)
    monkeypatch.setattr(cf, "WhatsAppCloudClient", FakeCloud)

    tenant_cfg = FakeTenantCfg({
        "t1": {"whatsapp_provider": "cloud", "cloud": True},
        "t2": {"cloud": True},  # provider empty -> choose cloud if enabled
        "t3": {"cloud": False},  # fallback -> twilio
    })

    f = cf.ClientsFactory(tenant_cfg=tenant_cfg)

    assert isinstance(f.whatsapp("t1"), FakeCloud)
    assert isinstance(f.whatsapp("t2"), FakeCloud)
    assert isinstance(f.whatsapp("t3"), FakeTwilio)

    # cached: second call doesn't call tenant_cfg.get again
    calls_before = len(tenant_cfg.calls)
    _ = f.whatsapp("t1")
    assert len(tenant_cfg.calls) == calls_before


def test_twilio_cached(monkeypatch):
    monkeypatch.setattr(cf, "TwilioClient", FakeTwilio)
    tenant_cfg = FakeTenantCfg({"t1": {}})
    f = cf.ClientsFactory(tenant_cfg=tenant_cfg)
    a = f.twilio("t1")
    b = f.twilio("t1")
    assert a is b