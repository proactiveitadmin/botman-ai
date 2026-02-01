from ..domain.templates import render_template
from ..repos.templates_repo import TemplatesRepo
from ..repos.tenants_repo import TenantsRepo
from ..common.config import settings
from ..common.logging import logger
import time


class TemplateService:
    def __init__(self, repo: TemplatesRepo | None = None) -> None:
        self.repo = repo or TemplatesRepo()
        self.tenants = TenantsRepo()
        # Prosty cache w pamięci procesu Lambdy.
        # Znacząco redukuje liczbę zapytań do DDB na ścieżce krytycznej latency.
        self._cache: dict[tuple[str, str, str], tuple[dict, float]] = {}
        self._cache_ttl_s = int(getattr(settings, "template_cache_ttl_s", 300) or 300)

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
        key = (tenant_id, name, language_code)
        now = time.time()
        cached = self._cache.get(key)
        if cached:
            item, ts = cached
            if now - ts <= self._cache_ttl_s:
                return item
            self._cache.pop(key, None)

        item = self.repo.get_template(tenant_id, name, language_code)
        if item:
            self._cache[key] = (item, now)
        return item

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

        body = tpl.get("body")

        if isinstance(body, list):
            seed = f"{tenant_id}:{name}:{lang}"
            template_str = self._pick_variant(
                [str(x) for x in body if x],
                seed,
            )
        else:
            template_str = str(body or "")

        return render_template(template_str, context or {})
