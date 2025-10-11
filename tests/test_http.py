# tests/test_http.py
import importlib
import sys
from typing import Any, Dict, Set

import pytest
from fastapi.testclient import TestClient

from app.config import Settings


def _reload_http_with_env(monkeypatch: pytest.MonkeyPatch, env: Dict[str, str]) -> TestClient:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Ensure a clean import so Settings() re-reads env
    if "server.http_app" in sys.modules:
        del sys.modules["server.http_app"]
    import server.http_app as http_app  # type: ignore

    importlib.reload(http_app)
    return TestClient(http_app.app)


def _rpc(
    client: TestClient,
    method: str,
    id_: int = 1,
    params: Dict[str, Any] | None = None,
    headers: Dict[str, str] | None = None,
):
    payload = {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}
    return client.post("/mcp", json=payload, headers=headers or {})


# ---------- Happy-path protocol flow ----------


def test_initialize_ok(http_client: TestClient, auth_headers: Dict[str, str]):
    r = _rpc(http_client, "initialize", id_=1, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert "result" in body
    assert "protocolVersion" in body["result"]
    assert "capabilities" in body["result"]


def test_tools_list_contains_expected(
    http_client: TestClient, auth_headers: Dict[str, str], registry_snapshot: Dict[str, Dict]
):
    r = _rpc(http_client, "tools/list", id_=2, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    tools = body["result"]["tools"]
    names_http: Set[str] = {t["name"] for t in tools}
    #names_registry: Set[str] = set(registry_snapshot.keys())
    all_tools_set = set(
        ["fs_write", "fs_read", "json_validate", "artifact_log", "artifact_list", "http_fetch"]
    )
    exposed_tools_set = all_tools_set - Settings.disabled_tools()
    # The unified registry is the single source of truth:
    assert names_http == exposed_tools_set


# def test_tool_call_json_validate_ok(http_client: TestClient, auth_headers: Dict[str, str]):
#     # Valid instance against a simple schema
#     params = {
#         "name": "json_validate",
#         "arguments": {
#             "instance": {"items": [{"sku": "A", "qty": 2}]},
#             "schema": {
#                 "type": "object",
#                 "properties": {
#                     "items": {
#                         "type": "array",
#                         "items": {
#                             "type": "object",
#                             "properties": {
#                                 "sku": {"type": "string"},
#                                 "qty": {"type": "integer", "minimum": 1},
#                             },
#                             "required": ["sku", "qty"],
#                             "additionalProperties": False,
#                         },
#                     }
#                 },
#                 "required": ["items"],
#             },
#             "draft": "2020-12",
#         },
#     }
#     r = _rpc(http_client, "tools/call", id_=3, params=params, headers=auth_headers)
#     assert r.status_code == 200, r.text
#     body = r.json()
#     assert body["id"] == 3
#     # Your HTTP adapter wraps results as content blocks; extract and assert:
#     result = body["result"]
#     assert result["isError"] is False
#     block = result["content"][0]
#     assert block["type"] == "json"
#     assert block["json"]["valid"] is True
#     assert block["json"]["errors"] == []


# ---------- Security behavior ----------


def test_security_forbidden_origin(monkeypatch: pytest.MonkeyPatch):
    """
    When MCP_HTTP_ALLOW_NO_ORIGIN=false and the Origin header is present but not allowed,
    the server must return 403.
    """
    client = _reload_http_with_env(
        monkeypatch,
        {
            "SANDBOX_ROOT": ".sandbox-tests",
            "REDIS_URL": "",
            "MCP_HTTP_BEARER_TOKEN": "change-me",
            "MCP_HTTP_ALLOW_NO_ORIGIN": "false",
            "MCP_HTTP_ALLOWED_ORIGINS": "http://allowed.test",
        },
    )
    # Disallowed Origin + (any) token -> 403 before auth
    r = _rpc(
        client,
        "initialize",
        id_=10,
        headers={"Authorization": "Bearer change-me", "Origin": "http://evil.test"},
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["error"]["message"].lower().startswith("forbidden origin")


# tests/test_http.py  (only the auth test shown here)


def test_security_missing_and_bad_token(monkeypatch: pytest.MonkeyPatch):
    """
    With an allowed Origin, a missing or invalid Bearer token must produce 401
    and a JSON-RPC shaped error envelope.
    """
    client = _reload_http_with_env(
        monkeypatch,
        {
            "SANDBOX_ROOT": ".sandbox-tests",
            "REDIS_URL": "",
            "MCP_HTTP_BEARER_TOKEN": "change-me",
            "MCP_HTTP_ALLOW_NO_ORIGIN": "false",
            "MCP_HTTP_ALLOWED_ORIGINS": "http://allowed.test",
        },
    )

    # Allowed origin but no Authorization header -> 401 + JSON-RPC error
    r1 = _rpc(client, "initialize", id_=11, headers={"Origin": "http://allowed.test"})
    assert r1.status_code == 401, r1.text
    body1 = r1.json()
    assert "error" in body1 and "message" in body1["error"]
    assert body1["error"]["message"].lower().startswith("missing bearer token")

    # Allowed origin but wrong token -> 401 + JSON-RPC error
    r2 = _rpc(
        client,
        "initialize",
        id_=12,
        headers={"Authorization": "Bearer wrong", "Origin": "http://allowed.test"},
    )
    assert r2.status_code == 401, r2.text
    body2 = r2.json()
    assert "error" in body2 and "message" in body2["error"]
    assert body2["error"]["message"].lower().startswith("invalid bearer token")
