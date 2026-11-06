import asyncio
from pathlib import Path
import sys
import unittest
from experiment_lab.acp import Client, ProtocolError


class SdkBoundary(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.client = Client({"command": [sys.executable, str(Path(__file__).parent / "fixtures/sdk_agent.py")],
                              "cwd": str(Path.cwd())},
                             lambda kind, **data: self.events.append({"kind": kind, **data}))
        await self.client.start()
        await self.client.open_session()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_slow_observations_finish_in_order_before_terminal_result(self):
        seen = []
        async def collect(text):
            await asyncio.sleep(0.03)
            seen.append(text)
        result = await self.client.prompt("normal", timeout=3, on_chunk=collect)
        self.assertEqual(seen, ["first", " second", " third"])
        self.assertEqual(result, {"text": "first second third", "stop_reason": "end_turn"})

    async def test_observer_failure_is_not_swallowed_or_reported_as_success(self):
        async def collect(text):
            raise ProtocolError("Observation failed")
        with self.assertRaisesRegex(ProtocolError, "Observation failed"):
            await self.client.prompt("normal", timeout=3, on_chunk=collect)

    async def test_sdk_load_keeps_original_session_and_does_not_start_prompt(self):
        session = self.client.session
        self.assertEqual(await self.client.open_session(session), session)
        self.assertEqual(self.events[-1]["kind"], "session_loaded")
        self.assertEqual((await self.client.prompt("normal", timeout=3))["text"], "first second third")

    async def test_sdk_error_is_redacted(self):
        with self.assertRaises(ProtocolError) as error:
            await self.client.prompt("error", timeout=3)
        self.assertNotIn("PRIVATE_PROVIDER_ERROR_CANARY", str(error.exception))
        self.assertNotIn("PRIVATE_PROVIDER_ERROR_CANARY", str(self.events))

    async def test_wrong_session_and_excessive_output_fail_collection(self):
        with self.assertRaisesRegex(ProtocolError, "different ACP session"):
            await self.client.prompt("wrong-session", timeout=3)

    async def test_excessive_output_fails_collection(self):
        with self.assertRaisesRegex(ProtocolError, "observation limit"):
            await self.client.prompt("oversize", timeout=3)

    async def test_closed_transport_cannot_complete_successfully(self):
        with self.assertRaises(ProtocolError):
            await self.client.prompt("disconnect", timeout=3)

    async def test_sdk_rejects_unadvertised_filesystem_access(self):
        result = await self.client.prompt("filesystem", timeout=3)
        self.assertEqual(result["text"], "-32601")

    async def test_timeout_requests_sdk_cancel_without_claiming_completion(self):
        with self.assertRaises(asyncio.TimeoutError):
            await self.client.prompt("wait", timeout=0.1)
        self.assertIn("timeout_cancel_requested", [event["kind"] for event in self.events])
