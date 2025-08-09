import asyncio
import json
from typing import AsyncGenerator, Dict, Any

from .mcp_client import McpHttpClient
from .context import get_user_conversation_summary
from .llm import build_default_llm
from . import prompts


class AIRecruiterAgent:
    def __init__(self, mcp_client: McpHttpClient):
        self.mcp_client = mcp_client
        self.llm = build_default_llm()

    async def run(self, user_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the agent for the given user_id, yielding events."""
        yield {"event": "task_started"}
        summary = await get_user_conversation_summary(self.mcp_client, user_id)
        yield {
            "event": "tool_called",
            "data": {
                "name": "get_user_conversation_summary",
                "params": {"user_id": user_id},
                "result": summary,
            },
        }
        plan_prompt = f"{prompts.system_prompt}\n\n{prompts.planning_prompt}\n用户历史: {summary}"
        plan_msg = await self.llm.ainvoke(plan_prompt)
        plan = plan_msg.content
        yield {"event": "plan", "data": plan}
        yield {"event": "task_finished", "result": plan}
