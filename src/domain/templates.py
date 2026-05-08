DEFAULT_FAQ = {
    "hours": "Opening hours not yet provided.",
    "price": "Pricing information has not been uploaded yet.",
    "location": "Location details are missing.",
    "contact": "Contact information has not been added yet.",
}


def _render_placeholder_value(v) -> str:
    """Render a single placeholder value.

    Supported:
      - plain values: str/int/... -> str(v)
      - typed placeholders:
          {"type": "text", "value": "..."}
          {"type": "link", "url": "https://...", "text": "..."}

    Output is channel-neutral (WhatsApp/SMS/email). For links we output
    a plain URL (optionally preceded by link text) so clients can auto-link.
    """
    if isinstance(v, dict):
        t = (v.get("type") or "").strip().lower()
        if t == "text":
            return str(v.get("value") or "")
        if t == "link":
            url = str(v.get("url") or "").strip()
            text = str(v.get("text") or "").strip()
            # lightweight URL sanity check
            if url and not (url.startswith("http://") or url.startswith("https://")):
                return ""
            if text and url:
                return f"{text} {url}".strip()
            return url
    return str(v)


def render_template(template_str: str, context: dict | None) -> str:
    out = str(template_str or "")
    for k, v in (context or {}).items():
        out = out.replace("{" + str(k) + "}", _render_placeholder_value(v))
    return out
