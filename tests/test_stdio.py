# tests/test_stdio.py
import asyncio
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


def _project_root() -> Path:
    # tests/ is one level below project root in your layout
    return Path(__file__).resolve().parents[1]


async def _with_timeout(coro, seconds=20):
    return await asyncio.wait_for(coro, timeout=seconds)


async def _start_stdio_client(tmp_path: Path):
    """
    Start a FastMCP Client that launches the server via STDIO using an MCP config dict.
    We run the server as: <python> -m server.main (module-safe; works with package imports).
    """
    from fastmcp import Client
    project_root = _project_root()

    # STDIO servers don't inherit your shell env; pass what you need explicitly.
    env = {
        "SANDBOX_ROOT": str(tmp_path),  # per-test sandbox
        "REDIS_URL": "",                # disable kv_* for hermetic tests
        "LOG_LEVEL": "INFO",
        "PYTHONPATH": str(project_root),  # ensure package imports resolve
    }

    # Canonical MCP JSON-style config; the Client infers MCPConfig transport.
    config = {
        "mcpServers": {
            "sut": {
                "command": sys.executable,
                "args": ["-m", "server.main"],
                "env": env,
            }
        }
    }

    return Client(config)


async def _wait_ready(client, retries: int = 3, backoff_base: float = 0.5):
    """
    Brief readiness check using client.ping() with exponential backoff.
    Retries: 0.5s -> 1.0s -> 2.0s (default).
    """
    delay = backoff_base
    for attempt in range(1, retries + 1):
        try:
            # If ping is implemented, it will succeed once the session is up.
            await _with_timeout(client.ping(), 10)
            return
        except Exception:
            if attempt == retries:
                raise
            await asyncio.sleep(delay)
            delay *= 2.0


async def _list_tool_names(client) -> set[str]:
    tools = await _with_timeout(client.list_tools(), 15)
    # Tool objects have a .name attribute
    return {t.name for t in tools}


async def _call(client, name: str, arguments: dict):
    return await _with_timeout(client.call_tool(name, arguments), 20)


async def _fs_write_read_roundtrip(client):
    # Write file
    w = await _call(client, "fs_write", {"path": "hello.txt", "content": "hi"})
    assert isinstance(w, str) and w.upper() == "OK"

    # Read file
    r = await _call(client, "fs_read", {"path": "hello.txt"})
    assert isinstance(r, str) and r == "hi"


async def _json_validate_ok(client):
    result = await _call(
        client,
        "json_validate",
        {
            "instance": {"items": [{"sku": "A", "qty": 2}]},
            "schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string"},
                                "qty": {"type": "integer", "minimum": 1},
                            },
                            "required": ["sku", "qty"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["items"],
            },
            "draft": "2020-12",
        },
    )
    # For STDIO, FastMCP returns the handler's result directly (dict here)
    assert isinstance(result, dict)
    assert result.get("valid") is True
    assert result.get("errors") == []


async def _assert_registry_consistency(client):
    """
    Ensure the unified registry is in effect by spot-checking expected tool names.
    We don't assume KV because we disabled REDIS_URL.
    """
    names = await _list_tool_names(client)
    for expected in {
        "fs_write", "fs_read", "json_validate", "artifact_log", "artifact_list", "http_fetch"
    }:
        assert expected in names


async def _stdio_session(tmp_path: Path):
    client = await _start_stdio_client(tmp_path)
    # Use async context manager to ensure the subprocess is cleaned up
    async with client:
        await _wait_ready(client)  # <-- readiness retry via ping()
        await _assert_registry_consistency(client)
        await _fs_write_read_roundtrip(client)
        await _json_validate_ok(client)


async def _kill_stray_server_processes():
    """
    Safety: in rare cases if a test aborts mid-run, ensure no server process is left running.
    FastMCP client handles termination on context exit; best-effort no-op here.
    """
    await asyncio.sleep(0)


@pytest.mark.timeout(60)
async def test_stdio_initialize_list_and_fs_json(tmp_path: Path):
    """
    End-to-end STDIO test:
      - launch server as subprocess via MCP config
      - readiness check with ping() (retry/backoff)
      - list tools (registry is unified)
      - fs_write -> fs_read
      - json_validate
    """
    try:
        await _stdio_session(tmp_path)
    finally:
        await _kill_stray_server_processes()
