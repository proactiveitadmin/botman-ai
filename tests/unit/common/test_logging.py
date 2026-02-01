import importlib
import sys
import types


def test_logging_fallback_stdlib_emits_json(caplog, monkeypatch):
    # Force ImportError for aws_lambda_powertools
    monkeypatch.setitem(sys.modules, "aws_lambda_powertools", None)

    import src.common.logging as logging_mod
    importlib.reload(logging_mod)

    # logger should be fallback wrapper with .info()
    caplog.set_level("INFO")

    logging_mod.logger.info({"a": 1, "b": "x"})
    assert any('"a": 1' in r.message for r in caplog.records)
