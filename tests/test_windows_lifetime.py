"""Actual native Windows child lifetime; skipped rather than simulated elsewhere."""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from experiment_lab.acp import Client


@unittest.skipUnless(os.name == "nt", "Requires native Windows process/job APIs")
class WindowsLifetime(unittest.IsolatedAsyncioTestCase):
    def alive(self, pid):
        from ctypes import wintypes as w
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        kernel.CloseHandle.argtypes = [w.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 0x102
        finally:
            kernel.CloseHandle(handle)

    async def test_immediate_descendant_is_closed_with_client(self):
        with tempfile.TemporaryDirectory(prefix="Lab café 子 ") as folder:
            root = Path(folder)
            marker = root / "descendant.json"
            script = root / "endpoint.py"
            script.write_text('''import json,pathlib,subprocess,sys
child=subprocess.Popen([sys.executable,"-X","utf8","-c","import time; time.sleep(60)"])
pathlib.Path(sys.argv[1]).write_text(json.dumps({"pid":child.pid}),encoding="utf-8")
for line in sys.stdin:
 request=json.loads(line)
 if request.get("method")=="initialize":
  print(json.dumps({"jsonrpc":"2.0","id":request["id"],"result":{"protocolVersion":1,"agentCapabilities":{},"agentInfo":{"name":"immediate-child","version":"1"},"authMethods":[]}}),flush=True)
''', encoding="utf-8")
            client = Client({"command":[sys.executable,"-X","utf8",str(script),str(marker)],"cwd":folder},lambda *args,**kwargs:None)
            try:
                await asyncio.wait_for(client.start(),10)
                pid=json.loads(marker.read_text(encoding="utf-8"))["pid"]
                self.assertTrue(self.alive(pid))
                await asyncio.wait_for(client.close(),5)
                for _ in range(40):
                    if not self.alive(pid):break
                    await asyncio.sleep(.05)
                self.assertFalse(self.alive(pid),"Immediate descendant survived its owned operation")
            finally:
                await asyncio.wait_for(client.close(),5)

    async def test_attach_failure_never_runs_suspended_endpoint(self):
        with tempfile.TemporaryDirectory(prefix="Lab café 子 ") as folder:
            marker=Path(folder)/"must-not-run.txt"
            command=[sys.executable,"-X","utf8","-c","import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran',encoding='utf-8')",str(marker)]
            client=Client({"command":command,"cwd":folder},lambda *args,**kwargs:None)
            try:
                with patch("experiment_lab.acp.ProcessJob",side_effect=OSError("injected job attachment failure")):
                    with self.assertRaisesRegex(OSError,"attachment failure"):
                        await asyncio.wait_for(client.start(),5)
                self.assertIsNotNone(client.process.returncode)
                self.assertFalse(marker.exists())
            finally:await client.close()
