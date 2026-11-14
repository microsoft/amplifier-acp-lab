"""Credential-free decision fixture for Unified's actual Core/loop-live worker."""
import asyncio
import json
from urllib.request import Request, urlopen

from amplifier_core import ModelInfo, ProviderInfo
from amplifier_core.message_models import ChatResponse, TextBlock, ToolCall

__amplifier_module_type__ = "provider"


class ReferenceProvider:
    name = "reference"

    def __init__(self, config=None, coordinator=None):
        self.coordinator, self.config = coordinator, config or {}

    def get_info(self):
        return ProviderInfo(id=self.name, display_name="Deterministic reference decisions",
            capabilities=["tools"], defaults={"model": "reference", "context_window": 200000, "max_output_tokens": 4096})

    async def list_models(self):
        return [ModelInfo(id="reference", display_name="Reference fixture", context_window=200000,
            max_output_tokens=4096, capabilities=["tools"])]

    def parse_tool_calls(self, response):
        return response.tool_calls or []

    async def complete(self, request, **kwargs):
        body = {"messages": [], "tools": [{"function": tool.model_dump()} for tool in request.tools or []],
                "metadata": request.metadata, "max_output_tokens": request.max_output_tokens}
        for message in request.messages:
            row = message.model_dump(mode="json")
            content = row["content"]
            if isinstance(content, list):
                tool_results = [block for block in content if block.get("type") == "tool_result"]
                if tool_results:
                    for block in tool_results:
                        body["messages"].append({"role": "tool", "tool_call_id": block["tool_call_id"],
                            "content": json.dumps(block.get("output", block.get("content")))})
                    continue
                content = "\n".join(block.get("text", "") for block in content if block.get("type") == "text")
            body["messages"].append({"role": row["role"], "content": content,
                                     **({"tool_call_id": row["tool_call_id"]} if row.get("tool_call_id") else {})})

        def call():
            req = Request(self.config["endpoint"], json.dumps(body).encode(), {"Content-Type": "application/json"})
            with urlopen(req, timeout=90) as response:
                return response.read().decode()
        wire = await asyncio.to_thread(call)
        calls, text = [], ""
        for line in wire.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            delta = json.loads(line[6:])["choices"][0]["delta"]
            text += delta.get("content", "")
            for tool in delta.get("tool_calls", []):
                calls.append(ToolCall(id=tool["id"], name=tool["function"]["name"], arguments=json.loads(tool["function"]["arguments"])))
        if text and (request.metadata or {}).get("stream") is not False:
            await self.coordinator.hooks.emit("llm:stream_block_delta", {"block_type": "text", "text": text,
                "request_id": "reference", "block_index": 0})
        return ChatResponse(content=[TextBlock(text=text)] if text else [], tool_calls=calls or None,
            finish_reason="tool_calls" if calls else "stop", usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})


async def mount(coordinator, config=None):
    await coordinator.mount("providers", ReferenceProvider(config or {}, coordinator), name="reference")
