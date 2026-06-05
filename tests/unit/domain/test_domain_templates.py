from src.domain import templates


def test_default_faq_contains_basic_keys():
    faq = templates.DEFAULT_FAQ
    assert "hours" in faq
    assert "price" in faq
    assert "location" in faq
    assert "contact" in faq


def test_render_template_replaces_placeholders():
    s = "Hello {name}, your code is {code}"
    res = templates.render_template(s, {"name": "Alice", "code": 123})
    assert res == "Hello Alice, your code is 123"


def test_render_template_ignores_missing_context_and_extra_fields():
    s = "Hello {name}"
    res = templates.render_template(s, {"name": "Bob", "unused": "x"})
    assert res == "Hello Bob"

    # brak kontekstu -> powinno działać bez wyjątku
    res2 = templates.render_template("Hi!", None)
    assert res2 == "Hi!"


def test_render_template_typed_placeholders_link_and_text():
    s = "Pay here: {payment_link} / Club: {club}"
    res = templates.render_template(
        s,
        {
            "payment_link": {"type": "link", "url": "https://example.com/pay", "text": "Pay"},
            "club": {"type": "text", "value": "Botman Gym"},
        },
    )
    assert res == "Pay here: Pay https://example.com/pay / Club: Botman Gym"
