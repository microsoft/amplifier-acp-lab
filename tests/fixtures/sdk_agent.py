"""Disposable official-SDK agent; no model, credentials or external services."""
import asyncio
import os
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent
from acp.schema import AgentCapabilities, AgentMessageChunk, TextContentBlock, LoadSessionResponse
from acp.exceptions import RequestError


class Peer(Agent):
    def on_connect(self, connection):
        self.connection = connection
        self.release = asyncio.Event()

    async def initialize(self, protocol_version, **kwargs):
        return InitializeResponse(protocol_version=protocol_version,
                                  agent_capabilities=AgentCapabilities(load_session=True))

    async def new_session(self, cwd, **kwargs):
        return NewSessionResponse(session_id="sdk-session")

    async def load_session(self, session_id, cwd, **kwargs):
        await self.chunk(session_id, "archived")
        return LoadSessionResponse()

    async def chunk(self, session_id, text):
        await self.connection.session_update(session_id=session_id,
            update=AgentMessageChunk(content=TextContentBlock(text=text)))

    async def prompt(self, session_id, prompt, **kwargs):
        mode = prompt[-1].text
        if mode == "error":
            raise RequestError(-32001, "PRIVATE_PROVIDER_ERROR_CANARY")
        if mode == "disconnect":
            os._exit(0)
        if mode == "wrong-session":
            await self.chunk("different-session", "private")
        elif mode == "oversize":
            await self.chunk(session_id, "x" * 250001)
        elif mode == "wait":
            await self.chunk(session_id, "waiting")
            await self.release.wait()
        elif mode == "filesystem":
            try:
                await self.connection.read_text_file(session_id=session_id, path="/must-not-read")
                await self.chunk(session_id, "unexpected access")
            except RequestError as error:
                await self.chunk(session_id, str(error.code))
        else:
            for text in ["first", " second", " third"]:
                await self.chunk(session_id, text)
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id, **kwargs):
        self.release.set()


asyncio.run(run_agent(Peer()))
