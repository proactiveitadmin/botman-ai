import importlib


def _reload_http_client(monkeypatch, **env):
    """Reload module and optionally set env vars."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))

    mod = importlib.import_module('src.common.http_client')
    return importlib.reload(mod)


def test_get_session_is_singleton(monkeypatch):
    mod = _reload_http_client(monkeypatch, HTTP_POOL_CONN=None, HTTP_POOL_MAX=None)

    s1 = mod.get_session()
    s2 = mod.get_session()

    assert s1 is s2


def test_get_session_uses_env_pool_sizes(monkeypatch):
    # Force module reload to rebuild the session with our env vars.
    mod = _reload_http_client(monkeypatch, HTTP_POOL_CONN=7, HTTP_POOL_MAX=9)

    s = mod.get_session()

    https_adapter = s.adapters.get('https://')
    assert https_adapter is not None
    # The adapter keeps pool settings in private attrs; these are stable enough for unit tests.
    assert getattr(https_adapter, '_pool_connections') == 7
    assert getattr(https_adapter, '_pool_maxsize') == 9
