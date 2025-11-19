from ..domain.templates import render_template
from ..storage.templates_repo import TemplatesRepo

class TemplateService:
    def __init__(self):
        self.repo = TemplatesRepo()

    def render(self, template: str, context: dict):
        # backward compatible – literal string
        return render_template(template, context)

    def render_named(self, tenant_id: str, name: str, language_code: str, context: dict) -> str:
        tpl = self.repo.get_template(tenant_id, name, language_code)
        if not tpl:
            # fallback: możesz np. spróbować bez języka albo zwrócić name
            return name
        template_str = tpl.get("body") or ""
        return render_template(template_str, context)