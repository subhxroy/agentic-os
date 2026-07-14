"""AgentOS Python SDK — typed HTTP client."""

import json
from typing import Optional, Dict, Any, List
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from .types import (
    AgentResponse, Session, Memory, Document,
    SearchResult, UsageAnalytics, App, APIKey, Plugin,
)


class AgentOSClientError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"AgentOS API error {status}: {message}")


class AgentOS:
    """AgentOS API client.

    Usage:
        client = AgentOS(base_url="http://localhost:8000", token="your-jwt-token")
        response = client.chat("What is 2 + 2?")
        print(response.response)
    """

    def __init__(self, base_url: str = "http://localhost:8000", token: str = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._session_id = None

    def _request(self, method: str, path: str, data: dict = None, params: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
            if qs:
                url += f"?{qs}"

        body = json.dumps(data).encode() if data else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body).get("error", body)
            except Exception:
                msg = body
            raise AgentOSClientError(e.code, msg)

    # ---- Auth ----

    def register(self, email: str, password: str, name: str = None) -> dict:
        result = self._request("POST", "/api/auth/register",
                               {"email": email, "password": password, "name": name})
        self.token = result.get("token")
        return result

    def login(self, email: str, password: str) -> dict:
        result = self._request("POST", "/api/auth/login",
                               {"email": email, "password": password})
        self.token = result.get("token")
        return result

    # ---- Chat ----

    def chat(self, message: str, session_id: str = None) -> AgentResponse:
        sid = session_id or self._session_id
        result = self._request("POST", "/api/chat",
                               {"message": message, "session_id": sid})
        if not self._session_id and result.get("session_id"):
            self._session_id = result["session_id"]
        return AgentResponse(
            response=result.get("response", ""),
            tool_calls=result.get("tool_calls", []),
            session_id=result.get("session_id"),
            tokens_used=result.get("tokens_used", 0),
            model=result.get("model", ""),
        )

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    # ---- Sessions ----

    def list_sessions(self) -> List[Session]:
        data = self._request("GET", "/api/sessions")
        return [Session(**s) for s in data]

    # ---- Memory ----

    def list_memories(self) -> List[Memory]:
        data = self._request("GET", "/api/memory")
        return [Memory(**m) for m in data]

    def create_memory(self, content: str) -> Memory:
        data = self._request("POST", "/api/memory", {"content": content})
        return Memory(**data)

    # ---- Knowledge ----

    def upload_document(self, filepath: str) -> Document:
        import os
        filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            content = f.read()
        url = f"{self.base_url}/api/knowledge/upload"
        from urllib.request import Request, urlopen
        import uuid as _uuid
        boundary = _uuid.uuid4().hex
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode())
        return Document(**data)

    def search_knowledge(self, query: str, limit: int = 5) -> List[SearchResult]:
        data = self._request("POST", "/api/knowledge/search",
                             {"query": query, "limit": limit})
        return [SearchResult(**r) for r in data.get("results", [])]

    # ---- Developer ----

    def create_app(self, name: str, description: str = None, scopes: list = None) -> App:
        data = self._request("POST", "/api/developer/apps",
                             {"name": name, "description": description, "scopes": scopes})
        return App(**data)

    def list_apps(self) -> List[App]:
        data = self._request("GET", "/api/developer/apps")
        return [App(**a) for a in data]

    def create_api_key(self, name: str = None, app_id: str = None) -> APIKey:
        data = self._request("POST", "/api/developer/keys",
                             {"name": name, "app_id": app_id})
        return APIKey(**data)

    def list_api_keys(self) -> List[APIKey]:
        data = self._request("GET", "/api/developer/keys")
        return [APIKey(**k) for k in data]

    def get_usage(self, days: int = 30) -> UsageAnalytics:
        data = self._request("GET", "/api/developer/usage", params={"days": days})
        return UsageAnalytics(**data)

    def list_plugins(self, status: str = "published") -> List[Plugin]:
        data = self._request("GET", "/api/developer/plugins", params={"status": status})
        return [Plugin(**p) for p in data]

    def create_plugin(self, name: str, display_name: str, description: str = None) -> Plugin:
        data = self._request("POST", "/api/developer/plugins",
                             {"name": name, "display_name": display_name, "description": description})
        return Plugin(**data)

    def install_plugin(self, plugin_id: str, config: dict = None) -> dict:
        return self._request("POST", f"/api/developer/plugins/{plugin_id}/install",
                             {"config": config or {}})

    # ---- Org ----

    def create_org(self, name: str) -> dict:
        return self._request("POST", "/api/orgs", {"name": name})

    # ---- GDPR ----

    def request_data_export(self) -> dict:
        return self._request("POST", "/api/gdpr/export")

    def request_data_deletion(self) -> dict:
        return self._request("POST", "/api/gdpr/delete")

    # ---- Status ----

    def status(self) -> dict:
        return self._request("GET", "/api/developer/status")

    def changelog(self) -> list:
        return self._request("GET", "/api/developer/changelog")
