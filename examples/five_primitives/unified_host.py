#!/usr/bin/env python3
"""Use Unified's existing real-worker fixture pattern in a fresh private home.

An explicitly supplied interpreter bypasses automatic runtime preparation. The
installed RuntimeManager, worker, Core, context and loop-live still execute. This
is engine-boundary qualification, not an installer or default-profile proof.
"""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import signal
import sys


async def main(args):
    home = Path(args.home).absolute()
    home.mkdir(mode=0o700, parents=True, exist_ok=False)
    shared, app_home = home / "shared", home / "app"
    shared.mkdir()
    os.environ.update(AMPLIFIER_HOME=str(shared), AMPLIFIER_WEB_HOME=str(app_home),
        AMPLIFIER_SESSION_STATE_HOME=str(home / "session-state"), AMPLIFIER_UNIFIED_IMPORT_HOME=str(home / "legacy"),
        AMPLIFIER_RUNTIME_IMMUTABLE="1", SSL_CERT_FILE=str(Path(args.ca_file).absolute()),
        PYTHONPATH=str(Path(__file__).parent))
    for key in list(os.environ):
        if key.endswith(("_API_KEY", "_ACCESS_TOKEN")) or key in {"OPENAI_KEY", "ANTHROPIC_AUTH_TOKEN"}:
            os.environ.pop(key, None)
    import yaml
    from aiohttp import web
    import amplifier_module_context_simple as context
    import amplifier_module_tool_mcp as mcp
    import amplifier_web
    from amplifier_web.builtin_behaviors import APPENDED_DEFAULTS
    from amplifier_web.runtime import RuntimeManager
    from amplifier_web.server import create_app
    provider_path = str(Path(__file__).with_name("amplifier_module_provider_reference"))
    provider = {"module": "provider-reference", "id": "reference", "source": provider_path,
        "config": {"default_model": "reference", "endpoint": args.provider_url}}
    context_path, mcp_path = str(Path(context.__file__).parent), str(Path(mcp.__file__).parent)
    bundle = home / "bundle.yaml"
    bundle.write_text(yaml.safe_dump({"bundle": {"name": "five-primitives-reference", "version": "1.0.0"},
        "session": {"orchestrator": {"module": "loop-live"}, "context": {"module": "context-simple", "source": context_path}},
        "providers": [provider], "tools": [{"module": "tool-mcp", "source": mcp_path}]}))
    (shared / "settings.yaml").write_text(yaml.safe_dump({"bundle": {"active": str(bundle), "app": [],
        "added": {"five-primitives-reference": str(bundle)}}, "web_bundles": {"excluded": list(APPENDED_DEFAULTS)},
        "config": {"providers": [provider]}, "sources": {"modules": {"context-simple": context_path,
        "provider-reference": provider_path, "tool-mcp": mcp_path}}}))
    runtime = RuntimeManager(command=[sys.executable, "-u", str(Path(amplifier_web.__file__).with_name("runtime_worker.py"))],
        startup_timeout=90, preparation_timeout=90)
    app = await create_app(app_home, workspace=args.workspace, runtime=runtime,
        voice=False, background_updates=False, preload_providers=False)
    token = secrets.token_urlsafe(32)
    app["control_token"] = token
    runtime.app_bridge = app["service"].app_bridge
    token_file = home / "control-token"
    token_file.write_text(token)
    token_file.chmod(0o600)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
    app["allowed_origins"] = app["allowed_origins"] | {url}
    graph = sorted([{"name": distribution.metadata["Name"], "version": distribution.version,
                     "direct_url": json.loads(distribution.read_text("direct_url.json") or "null")}
                    for distribution in importlib.metadata.distributions()], key=lambda item: item["name"].lower())
    graph_file = home / "installed-graph.json"
    graph_file.write_text(json.dumps(graph, indent=2) + "\n")
    module_files = {"runtime_worker": Path(amplifier_web.__file__).with_name("runtime_worker.py"),
                    "mcp_wrapper": Path(mcp.__file__).with_name("wrapper.py")}
    (home / "ready.json").write_text(json.dumps({"url": url, "token_file": str(token_file), "bundle": str(bundle),
        "qualification_bypassed": True, "deterministic_provider": True,
        "profile": "explicit MCP reference profile; not Unified's default Work profile",
        "installed_graph": str(graph_file), "installed_graph_sha256": hashlib.sha256(graph_file.read_bytes()).hexdigest(),
        "module_files": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                         for name, path in module_files.items()},
        "versions": {name: importlib.metadata.version(name) for name in ["amplifier-unified", "amplifier-core",
            "amplifier-foundation", "amplifier-module-loop-live", "amplifier-module-context-simple", "amplifier-module-tool-mcp"]}}, indent=2))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await stop.wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("home", "workspace", "provider-url", "ca-file"):
        p.add_argument("--" + key, required=True)
    asyncio.run(main(p.parse_args()))
