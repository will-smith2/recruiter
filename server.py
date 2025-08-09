import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from ai_agent.mcp_client import McpHttpClient
from ai_agent.agent import AIRecruiterAgent

app = FastAPI()


@app.post("/agent")
async def run_agent(payload: dict):
    user_id = payload.get("user_id")
    mcp_url = payload.get("mcp_url", "https://agentbay.wuying.aliyuncs.com/sse?APIKEY=demo&IMAGEID=browser_latest")
    headers = {"Content-Type": "application/x-ndjson"}

    async def generator():
        async with McpHttpClient(mcp_url) as client:
            agent = AIRecruiterAgent(client)
            async for event in agent.run(user_id):
                yield (json.dumps(event) + "\n").encode("utf-8")

    return StreamingResponse(generator(), headers=headers)


@app.on_event("shutdown")
async def shutdown_event():
    pass
