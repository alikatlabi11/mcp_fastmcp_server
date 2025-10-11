# server/http_app.py
from __future__ import annotations

from typing import Any, Dict

import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Settings
from app.di import build_container
from server.registry import (
    build_tool_registry,
    list_tools_payload,
    dispatch_tool_call,
)

app = FastAPI(title="MCP HTTP Server", version="0.1.0")

settings = Settings()
container = build_container()
REGISTRY = build_tool_registry(container)
PROTOCOL_VERSION = "2025-03-26"  # illustrative; version negotiation is done at initialize


# ---------- JSON-RPC helpers ----------


def _jsonrpc_error_response(
    id_: Any,
    code: int,
    message: str,
    http_status: int,
    data: Any | None = None,
) -> JSONResponse:
    body: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": id_,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        body["error"]["data"] = data
    return JSONResponse(body, status_code=http_status)


def _jsonrpc_ok_response(id_: Any, result: Any, http_status: int = 200) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result}, status_code=http_status)


# ---------- Security: Origin validation & Bearer token ----------


def _origin_allowed(req: Request) -> bool:
    origin = req.headers.get("origin")
    if not origin:
        return settings.MCP_HTTP_ALLOW_NO_ORIGIN
    allowed = {o.strip().lower() for o in settings.MCP_HTTP_ALLOWED_ORIGINS.split(",") if o.strip()}
    return origin.lower() in allowed


@app.middleware("http")
async def origin_validation_mw(request: Request, call_next):
    # MCP Streamable HTTP guidance: validate Origin to prevent DNS rebinding
    if not _origin_allowed(request):
        # No reliable message id yet → use id=None
        return _jsonrpc_error_response(
            id_=None, code=403, message="Forbidden origin", http_status=403
        )
    return await call_next(request)


def _check_auth_return_error(req: Request, id_: Any) -> JSONResponse | None:
    auth = req.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return _jsonrpc_error_response(
            id_, code=401, message="Missing Bearer token", http_status=401
        )
    token = auth.split(" ", 1)[1]
    if token != settings.MCP_HTTP_BEARER_TOKEN:
        return _jsonrpc_error_response(
            id_, code=401, message="Invalid Bearer token", http_status=401
        )
    return None


# ---------- MCP JSON-RPC endpoint (Streamable HTTP; non-streaming JSON here) ----------


@app.post(settings.MCP_HTTP_PATH)
async def mcp_endpoint(request: Request):
    # Parse JSON first so we can carry message id into any auth error
    try:
        payload = await request.json()
    except Exception:
        return _jsonrpc_error_response(
            id_=None, code=-32700, message="Parse error", http_status=400
        )

    id_ = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    # Auth gate (after we have id)
    auth_err = _check_auth_return_error(request, id_)
    if auth_err is not None:
        return auth_err

    if method == "initialize":
        return _jsonrpc_ok_response(
            id_,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "acme-mcp-http", "version": "0.1.0"},
            },
        )

    if method == "tools/list":
        return _jsonrpc_ok_response(id_, list_tools_payload(REGISTRY))

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            result = dispatch_tool_call(REGISTRY, name, args)
        except KeyError as ke:
            return _jsonrpc_error_response(id_, code=-32601, message=str(ke), http_status=404)
        except Exception as e:
            return _jsonrpc_error_response(
                id_, code=-32603, message="Internal error", http_status=500, data=str(e)
            )

        content_block = (
            {"type": "json", "json": result}
            if isinstance(result, (dict, list))
            else {"type": "text", "text": str(result)}
        )
        return _jsonrpc_ok_response(id_, {"content": [content_block], "isError": False})

    return _jsonrpc_error_response(
        id_, code=-32601, message=f"Method not found: {method}", http_status=404
    )

# ---------- Models for /status endpoint ----------
# ✅ Origin allow‑list (done) and Bearer auth (done). [Security O...r · GitHub]
# ✅ HTTP client SSRF guard + allow‑list in your services (already present; keep it).
# ✅ Sanitize artifacts (you added redaction & Windows‑safe tags).
# ⬜ Rate limit /mcp and body size caps.
# ⬜ Secrets: only log redacted tokens/headers; keep .env out of artifacts.