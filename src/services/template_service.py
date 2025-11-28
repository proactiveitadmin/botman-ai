from ..domain.templates import render_template
from ..repos.templates_repo import TemplatesRepo
from ..repos.tenants_repo import TenantsRepo
from ..common.config import settings
from ..common.logging import logger


class TemplateService:
    def __init__(self, repo: TemplatesRepo | None = None) -> None:
        self.repo = repo or TemplatesRepo()
        self.tenants = TenantsRepo()

    def render(self, template: str, context: dict):
        """
        Backward compatible – literal string (np. stare miejsca typu CONFIRM_TEMPLATE).
        Docelowo NIE używamy tego w nowych flow – wszystko przez render_named.
        """
        return render_template(template, context or {})

    def _tenant_default_lang(self, tenant_id: str) -> str:
        tenant = self.tenants.get(tenant_id) or {}
        return tenant.get("language_code") or settings.get_default_language()

    def _try_get_template(self, tenant_id: str, name: str, language_code: str | None):
        if not language_code:
            return None
        return self.repo.get_template(tenant_id, name, language_code)

    def render_named(
        self,
        tenant_id: str,
        name: str,
        language_code: str | None,
        context: dict | None = None,
    ) -> str:
        """
        Główna metoda do wszystkich odpowiedzi bot-a.

        Priorytety:
        1) exact language_code, np. "pl-PL"
        2) base language z prefixu, np. "pl"
        3) default language tenanta
        4) global default (settings.get_default_language)
        Jeśli nic nie ma – zwracamy samą nazwę szablonu (łatwo szukać braków w logach).
        """

        lang_chain: list[str] = []

        if language_code:
            lang_chain.append(language_code)
            if "-" in language_code:
                base = language_code.split("-", 1)[0]
                if base != language_code:
                    lang_chain.append(base)

        tenant_default = self._tenant_default_lang(tenant_id)
        if tenant_default and tenant_default not in lang_chain:
            lang_chain.append(tenant_default)

        global_default = settings.get_default_language()
        if global_default and global_default not in lang_chain:
            lang_chain.append(global_default)

        tpl = None
        for lang in lang_chain:
            tpl = self._try_get_template(tenant_id, name, lang)
            if tpl:
                break

        if not tpl:
            logger.warning(
                {
                    "template_missing": name,
                    "tenant_id": tenant_id,
                    "langs_tried": lang_chain,
                }
            )
            # ŻADNYCH domyślnych tekstów – zwracamy nazwę szablonu
            return name

        template_str = tpl.get("body") or ""
        return render_template(template_str, context or {})
