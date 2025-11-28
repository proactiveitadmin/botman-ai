import base64, requests, json
from ..common.config import settings
from ..common.logging import logger

class JiraClient:
    def __init__(self):
        self.url = settings.jira_url.rstrip("/") if settings.jira_url else ""
        self.project = settings.jira_project_key
        self.issue_type_name = settings.jira_default_issue_type

    def _auth_header(self):
        if ":" in settings.jira_token:
            token = base64.b64encode(settings.jira_token.encode()).decode()
            return {"Authorization": f"Basic {token}"}
        return {}
        
    def _build_description_adf(self, description: str) -> dict:
        """
        Zamienia zwykły tekst na Atlassian Document Format (ADF),
        jeden paragraf na każdą linię.
        """
        if description is None:
            description = ""

        lines = description.splitlines() or [""]

        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": line,
                        }
                    ],
                }
                for line in lines
            ],
        }

    def create_ticket(
        self,
        summary: str,
        description: str,
        tenant_id: str,
        meta: dict | None = None,
    ) -> dict:
        if not self.url:
            logger.info({"jira": "dev", "summary": summary, "meta": meta or {}})
            return {"ok": True, "ticket": "JIRA-DEV"}

        # meta jako sekcja na początku opisu
        meta_lines = []
        if meta:
            for k, v in meta.items():
                meta_lines.append(f"{k}: {v}")
        full_description = ""
        if meta_lines:
            full_description += "[META]\n" + "\n".join(meta_lines) + "\n\n"
        full_description += description or ""

        description_adf = self._build_description_adf(full_description)

        payload = {
            "fields": {
                "project": {"key": self.project},
                "summary": f"[{tenant_id}] {summary}",
                "description": description_adf,
                "issuetype": {"name": self.issue_type_name},
            }
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self._auth_header(),
        }
        r = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=10)
        
        if not r.ok:
            print("Jira error status:", r.status_code)
            print("Jira error body:", r.text)
        
        r.raise_for_status()
        data = r.json()
        return {"ok": True, "ticket": data.get("key", "JIRA-UNK")}
