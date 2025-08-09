from typing import Any, Dict

from .mcp_client import McpHttpClient


async def get_user_conversation_summary(client: McpHttpClient, user_id: str) -> Dict[str, Any]:
    """Fetch user conversation summary via MCP tool.

    The remote MCP server is expected to expose a tool named
    ``get_user_conversation_summary`` that accepts ``user_id``.
    """
    return await client.call_tool("get_user_conversation_summary", {"user_id": user_id})
