from ..domain.templates import render_template
from ..storage.templates_repo import TemplatesRepo

class TemplateService:
    def __init__(self, repo: TemplatesRepo | None = None) -> None:
        self.repo = repo or TemplatesRepo()

    def render(self, template: str, context: dict):
        # backward compatible – literal string
        return render_template(template, context)

    def render_named(
        self,
        tenant_id: str,
        name: str,
        language_code: str,
        context: dict,
    ) -> str:
        # 1. Spróbuj w żądanym języku
        tpl = self.repo.get_template(tenant_id, name, language_code)

        # 2. Jeśli nie ma i język nie jest EN – spróbuj EN jako fallback
        if not tpl and language_code != "en":
            tpl = self.repo.get_template(tenant_id, name, "en")

        # 3. Jeśli dalej nie ma – twardy fallback tylko dla clarify_generic
        if not tpl:
            if name == "clarify_generic":
                # domyślny, zawsze dostępny tekst po angielsku
                return "Could you clarify what you mean?"

            # dla innych szablonów nie kombinujemy,
            # zwracamy nazwę (łatwo znaleźć brakujący template w logach)
            return name

        template_str = tpl.get("body") or ""
        return render_template(template_str, context or {})
        


    
