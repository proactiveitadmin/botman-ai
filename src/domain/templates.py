DEFAULT_FAQ = {
    "hours": "Opening hours not yet provided.",
    "price": "Pricing information has not been uploaded yet.",
    "location": "Location details are missing.",
    "contact": "KContact information has not been added yet.",
}
def render_template(template_str: str, context: dict) -> str:
    out = template_str
    for k, v in (context or {}).items():
        out = out.replace("{"+k+"}", str(v))
    return out
