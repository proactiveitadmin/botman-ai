def test_app_prints_message(monkeypatch):
    printed = []

    def fake_print(*args, **kwargs):
        printed.append(" ".join(str(a) for a in args))

    monkeypatch.setattr("builtins.print", fake_print)

    # import src.app -> wykonuje się kod z modułu
    import src.app as app  # noqa: F401

    assert any("Use SAM to run locally" in line for line in printed)
