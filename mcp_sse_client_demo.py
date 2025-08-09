#!/usr/bin/env python3
"""
MCP SSE 客户端演示
演示如何连接到使用 Server-Sent Events (SSE) 传输的 MCP 服务器

基于 Model Context Protocol (MCP) 规范实现
"""

import json
import asyncio
import aiohttp
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import uuid

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class McpMessageType(Enum):
    """MCP 消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"

@dataclass
class McpTool:
    """MCP 工具信息"""
    name: str
    description: str
    input_schema: Dict[str, Any]

@dataclass
class McpResource:
    """MCP 资源信息"""
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None

class McpSseClient:
    """MCP SSE 客户端"""
    
    def __init__(self, sse_url: str, headers: Optional[Dict[str, str]] = None):
        self.base_url = sse_url.split('?')[0].rstrip('/')
        self.sse_url = sse_url
        self.headers = headers or {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_id = 0
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.event_source: Optional[aiohttp.ClientResponse] = None
        self.is_connected = False
        self.post_url: Optional[str] = None
        self.post_url_ready = asyncio.Event()
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()
        if self.session:
            await self.session.close()
    
    def _get_next_request_id(self) -> str:
        """获取下一个请求ID"""
        self.request_id += 1
        return str(self.request_id)
    
    async def connect(self):
        """连接到 SSE 端点"""
        if not self.session:
            raise RuntimeError("Client session not initialized")
        
        logger.info(f"连接到 SSE 端点: {self.sse_url}")
        
        try:
            # 建立 SSE 连接
            self.event_source = await self.session.get(
                self.sse_url,
                headers={
                    **self.headers,
                    'Accept': 'text/event-stream',
                    'Cache-Control': 'no-cache'
                }
            )
            
            if self.event_source.status != 200:
                raise Exception(f"SSE 连接失败: {self.event_source.status} - {await self.event_source.text()}")
            
            self.is_connected = True
            logger.info("SSE 连接建立成功")
            
            # 启动消息处理任务
            asyncio.create_task(self._process_sse_messages())
            
        except Exception as e:
            logger.error(f"SSE 连接失败: {e}")
            raise
    
    async def disconnect(self):
        """断开连接"""
        self.is_connected = False
        if self.event_source:
            self.event_source.close()
            self.event_source = None
        logger.info("SSE 连接已断开")
    
    async def _process_sse_messages(self):
        """处理 SSE 消息流"""
        if not self.event_source:
            return
        
        try:
            async for line in self.event_source.content:
                if not self.is_connected:
                    break
                
                line_str = line.decode('utf-8').strip()
                if not line_str:
                    continue
                
                # 解析 SSE 消息格式
                if line_str.startswith('data: '):
                    data_str = line_str[6:]  # 移除 'data: ' 前缀
                    
                    try:
                        # 检查是否是特殊的回调地址消息
                        if data_str.startswith('/message?sessionId='):
                            self.post_url = f"{self.base_url.replace('/sse', '')}{data_str}"
                            logger.info(f"收到回调地址，新的请求地址为: {self.post_url}")
                            self.post_url_ready.set()
                        else:
                            message = json.loads(data_str)
                            await self._handle_message(message)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON 解析失败: {e}, 数据: {data_str}")
                
        except Exception as e:
            logger.error(f"SSE 消息处理失败: {e}")
            self.is_connected = False
    
    async def _handle_message(self, message: Dict[str, Any]):
        """处理接收到的消息"""
        logger.debug(f"收到消息: {json.dumps(message, indent=2)}")
        
        # 处理响应消息
        if 'id' in message and str(message['id']) in self.pending_requests:
            request_id = str(message['id'])
            future = self.pending_requests.pop(request_id)
            
            if 'error' in message:
                error = message['error']
                future.set_exception(Exception(f"MCP 错误 {error.get('code', 'unknown')}: {error.get('message', 'Unknown error')}"))
            else:
                future.set_result(message.get('result', {}))
        
        # 处理通知消息
        elif message.get('method'):
            logger.info(f"收到通知: {message.get('method')}")
    
    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """发送 MCP 请求"""
        if not self.is_connected:
            raise RuntimeError("未连接到 SSE 端点")
        
        # 等待回调地址就绪
        try:
            await asyncio.wait_for(self.post_url_ready.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            raise Exception("等待回调地址超时")

        if not self.post_url:
            raise RuntimeError("无法获取请求的回调地址")
            
        request_id = self._get_next_request_id()
        
        # 构建 MCP 请求消息
        request_data = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method
        }
        
        if params:
            request_data["params"] = params
        
        logger.info(f"发送请求: {method}")
        logger.debug(f"请求数据: {json.dumps(request_data, indent=2)}")
        
        # 创建等待响应的 Future
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        try:
            # 通过 POST 发送请求到回调地址
            async with self.session.post(
                self.post_url,
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status not in [200, 202]:
                    raise Exception(f"请求失败: {response.status} - {await response.text()}")
            
            # 等待响应
            try:
                result = await asyncio.wait_for(future, timeout=30.0)
                return result
            except asyncio.TimeoutError:
                self.pending_requests.pop(request_id, None)
                raise Exception("请求超时")
                
        except Exception as e:
            self.pending_requests.pop(request_id, None)
            logger.error(f"请求发送失败: {e}")
            raise
    
    async def initialize(self) -> Dict[str, Any]:
        """初始化 MCP 连接"""
        logger.info("初始化 MCP 连接...")
        
        # 首先建立 SSE 连接
        await self.connect()
        
        # 等待回调地址就绪
        try:
            await asyncio.wait_for(self.post_url_ready.wait(), timeout=10.0)
            logger.info("回调地址已就绪，发送初始化请求...")
        except asyncio.TimeoutError:
            # 如果超时，可能服务器不需要显式初始化，直接尝试后续操作
            logger.warning("等待回调地址超时，可能不需要初始化。")
            return {"serverInfo": {"name": "Unknown (No Init)", "version": "Unknown"}}
        
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {
                    "listChanged": True
                },
                "sampling": {}
            },
            "clientInfo": {
                "name": "MCP-SSE-Client-Demo",
                "version": "1.0.0"
            }
        }
        
        try:
            result = await self._send_request("initialize", params)
            logger.info("MCP 连接初始化成功")
            return result
        except Exception as e:
            logger.error(f"MCP 初始化失败: {e}")
            # 对于某些 SSE 服务器，可能不需要显式初始化
            logger.info("尝试跳过初始化，直接获取工具列表...")
            return {"serverInfo": {"name": "Unknown (Init Failed)", "version": "Unknown"}}
    
    async def list_tools(self) -> List[McpTool]:
        """获取可用工具列表"""
        logger.info("获取工具列表...")
        
        try:
            result = await self._send_request("tools/list")
            tools = []
            
            for tool_data in result.get("tools", []):
                tool = McpTool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {})
                )
                tools.append(tool)
                
            logger.info(f"找到 {len(tools)} 个工具")
            return tools
        except Exception as e:
            logger.error(f"获取工具列表失败: {e}")
            return []
    
    async def list_resources(self) -> List[McpResource]:
        """获取可用资源列表"""
        logger.info("获取资源列表...")
        
        try:
            result = await self._send_request("resources/list")
            resources = []
            
            for resource_data in result.get("resources", []):
                resource = McpResource(
                    uri=resource_data["uri"],
                    name=resource_data["name"],
                    description=resource_data.get("description"),
                    mime_type=resource_data.get("mimeType")
                )
                resources.append(resource)
                
            logger.info(f"找到 {len(resources)} 个资源")
            return resources
        except Exception as e:
            logger.error(f"获取资源列表失败: {e}")
            return []
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        logger.info(f"调用工具: {tool_name}")
        
        params = {
            "name": tool_name,
            "arguments": arguments
        }
        
        result = await self._send_request("tools/call", params)
        logger.info(f"工具 {tool_name} 执行完成")
        return result

def print_tools(tools: List[McpTool]):
    """打印工具列表"""
    if not tools:
        print("❌ 没有找到可用工具")
        return
    
    print(f"\n🔧 找到 {len(tools)} 个可用工具:")
    print("=" * 60)
    
    for i, tool in enumerate(tools, 1):
        print(f"\n{i}. 工具名称: {tool.name}")
        print(f"   描述: {tool.description}")
        
        # 打印输入参数
        if tool.input_schema and "properties" in tool.input_schema:
            print("   参数:")
            properties = tool.input_schema["properties"]
            required = tool.input_schema.get("required", [])
            
            for param_name, param_info in properties.items():
                required_mark = " (必需)" if param_name in required else " (可选)"
                param_type = param_info.get("type", "unknown")
                param_desc = param_info.get("description", "无描述")
                print(f"     - {param_name}{required_mark}: {param_type} - {param_desc}")
        else:
            print("   参数: 无")

async def demo_sse_client(server_url: str, headers: Optional[Dict[str, str]] = None):
    """演示 SSE MCP 客户端使用"""
    print(f"🚀 连接到 SSE MCP 服务器: {server_url}")
    
    try:
        async with McpSseClient(server_url, headers) as client:
            # 1. 初始化连接
            init_result = await client.initialize()
            print(f"✅ 连接成功! 服务器信息:")
            server_info = init_result.get("serverInfo", {})
            print(f"   名称: {server_info.get('name', 'Unknown')}")
            print(f"   版本: {server_info.get('version', 'Unknown')}")
            
            # 2. 获取工具列表
            tools = await client.list_tools()
            print_tools(tools)
            
            # 3. 获取资源列表
            try:
                resources = await client.list_resources()
                if resources:
                    print(f"\n📁 找到 {len(resources)} 个可用资源:")
                    for resource in resources:
                        print(f"   - {resource.name}: {resource.uri}")
            except Exception as e:
                print(f"⚠️  获取资源列表失败: {e}")
            
            # 4. 演示工具调用（如果有工具的话）
            if tools:
                print(f"\n🔧 演示调用第一个工具: {tools[0].name}")
                try:
                    # 构造简单的测试参数
                    test_args = {}
                    schema = tools[0].input_schema
                    
                    if "properties" in schema:
                        required = schema.get("required", [])
                        for param_name in required[:1]:  # 只填充第一个必需参数作为测试
                            param_info = schema["properties"][param_name]
                            param_type = param_info.get("type", "string")
                            
                            if param_type == "string":
                                test_args[param_name] = "test"
                            elif param_type == "number":
                                test_args[param_name] = 1
                            elif param_type == "boolean":
                                test_args[param_name] = True
                    
                    if test_args:
                        result = await client.call_tool(tools[0].name, test_args)
                        print(f"✅ 工具调用成功:")
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                    else:
                        print("⚠️  跳过工具调用 - 无法构造测试参数")
                        
                except Exception as e:
                    print(f"❌ 工具调用失败: {e}")
            
            # 保持连接一段时间以接收可能的通知
            print("\n⏳ 保持连接 5 秒以接收通知...")
            await asyncio.sleep(5)
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        logger.error(f"连接失败: {e}")

async def main():
    """主函数"""
    print("🎯 MCP SSE 客户端演示")
    print("=" * 50)
    
    # 使用您提供的服务器配置
    server_config = {
        "name": "wuying_mcp_server",
        "url": "https://agentbay.wuying.aliyuncs.com/sse?APIKEY=akm-9f50aa3e-3d9f-4b69-8219-f72d6eefdae7&IMAGEID=browser_latest",
        "headers": {}
    }
    
    print(f"\n🔗 测试服务器: {server_config['name']}")
    await demo_sse_client(server_config["url"], server_config.get("headers"))

if __name__ == "__main__":
    # 运行演示
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 程序被用户中断")
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        logger.error(f"程序执行失败: {e}")
