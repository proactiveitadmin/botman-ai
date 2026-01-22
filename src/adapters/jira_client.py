import base64, requests, json
from ..common.logging import logger
from ..common.config import settings

class JiraClient:
    def __init__(
        self,
        *,
        url: str | None = None,
        token: str | None = None,
        project_key: str | None = None,
        issue_type_name: str | None = None,
    ):
        self.issue_type_name = (issue_type_name or settings.jira_default_issue_type or "").strip() or "Task"
        self.url = (url or "").rstrip("/")
        self.project = (project_key or "").strip()
        self.token = (token or "").strip()

    @classmethod
    def from_tenant_config(cls, tenant_cfg: dict) -> "JiraClient":
        j = (tenant_cfg or {}).get("jira") or {}
        if not isinstance(j, dict):
            j = {}
            logger.warning({"msg": "jira_config_missing_or_invalid"})
        return cls(
            url=j.get("url"),
            token=j.get("token"),
            project_key=j.get("project_key"),
            issue_type_name=j.get("issue_type_name") or j.get("issue_type"),
        )


    def _auth_header(self):
        # Jira Cloud commonly uses Basic auth: email:api_token
        if self.token and ":" in self.token:
            token = base64.b64encode(self.token.encode()).decode()
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
            logger.warning({"jira": "dev", "summary": summary, "meta": meta or {}})
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
           
        endpoint = f"{self.url}/rest/api/3/issue"
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
            try:
                payload_json = r.json()
            except Exception:
                payload_json = {}
            key = (payload_json or {}).get("key") or "JIRA-ERR"

            print(f"Jira error status: {r.status_code}")
            print(f"Jira error body: {r.text}")
            
            logger.error({
                "msg": "Jira creation failed",
                "Jira error status": r.status_code,
                "Jira error body": r.text,
                "tenant_id": tenant_id,
            })
            return {"ok": True, "ticket": key}
        
        r.raise_for_status()
        data = r.json()
        return {"ok": True, "ticket": data.get("key", "JIRA-UNK")}
