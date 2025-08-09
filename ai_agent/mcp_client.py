from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class McpTool:
    name: str
    description: str
    input_schema: Dict[str, Any]


class McpHttpClient:
    """Simple HTTP client for MCP servers (limited, no SSE)."""

    def __init__(self, base_url: str, headers: Optional[Dict[str, str]] = None):
        self.base_url = base_url.rstrip('/')
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **self.headers})
        with urllib.request.urlopen(req) as resp:  # nosec - demo only
            content = resp.read().decode("utf-8")
            return json.loads(content)

    async def list_tools(self) -> Any:
        payload = {"id": "1", "method": "tools/list"}
        result = self._post("/rpc", payload)
        tools = result.get("result", [])
        return [McpTool(**t) for t in tools]

    async def call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        payload = {
            "id": "1",
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
        result = self._post("/rpc", payload)
        return result.get("result")


class FakeMcpClient(McpHttpClient):
    """Offline stub for tests."""

    def __init__(self):
        super().__init__("https://fake-mcp")

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        method = payload.get("method")
        if method == "tools/list":
            return {"result": []}
        if method == "tools/call":
            name = payload["params"]["name"]
            if name == "get_user_conversation_summary":
                return {"result": {"summary": "This is a fake summary."}}
            return {"result": {"ok": True}}
        return {"result": None}
