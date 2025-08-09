#!/usr/bin/env python3
import argparse
import asyncio
import json
from typing import Any, Dict

from ai_agent.mcp_client import McpHttpClient, FakeMcpClient
from ai_agent.agent import AIRecruiterAgent


def print_event(event: Dict[str, Any]):
    et = event.get("event")
    if et == "tool_called":
        data = event["data"]
        print(f"[Tool] {data['name']} params={data['params']} result={data['result']}")
    elif et == "plan":
        print(f"[Plan] {event['data']}")
    elif et == "task_started":
        print("Task started")
    elif et == "task_finished":
        print("Task finished")
    else:
        print(event)


async def main():
    parser = argparse.ArgumentParser(description="AI agent CLI")
    parser.add_argument("user_id", help="User ID")
    parser.add_argument("--mcp-url", default="https://agentbay.wuying.aliyuncs.com")
    parser.add_argument("--offline", action="store_true", help="use fake MCP client")
    args = parser.parse_args()

    if args.offline:
        client = FakeMcpClient()
    else:
        client = McpHttpClient(args.mcp_url)
    async with client:
        agent = AIRecruiterAgent(client)
        async for event in agent.run(args.user_id):
            print_event(event)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
