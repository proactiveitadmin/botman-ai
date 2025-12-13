import re

from src.common import utils
from src.common.config import settings


def test_to_json_compact():
    payload = {"a": 1, "b": "żółć"}
    s = utils.to_json(payload)
    # bez spacji po przecinkach/ dwukropkach
    assert s == '{"a":1,"b":"żółć"}'


def test_new_id_prefix_and_uniqueness():
    id1 = utils.new_id("abc_")
    id2 = utils.new_id("abc_")
    assert id1.startswith("abc_")
    assert id2.startswith("abc_")
    assert id1 != id2


def test_generate_verification_code_format():
    code = utils.generate_verification_code(8)
    assert len(code) == 8
    assert re.fullmatch(r"[A-Z0-9]{8}", code)


def test_whatsapp_wa_me_link(monkeypatch):
    monkeypatch.setattr(
        settings, "twilio_whatsapp_number", "whatsapp:+48123123123", raising=False
    )
    link = utils.whatsapp_wa_me_link("XYZ123")
    assert link == "https://wa.me/+48123123123?text=KOD:XYZ123"
