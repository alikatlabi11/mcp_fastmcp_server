# server/http_app.py
from __future__ import annotations

from typing import Any, Dict, Callable
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json

from app.di import build_container
from app.config import Settings

# Import the input models from existing tools
from server.tools.files import FsWriteIn
from server.tools.kv import KvPutIn, KvGetIn
from server.tools.http_fetch import FetchIn
from server.tools.json_validate import JsonValidateIn
from server.tools.artifacts import ArtifactLogIn, ArtifactListIn

from server.registry import build_tool_registry, list_tools_payload, dispatch_tool_call

app = FastAPI(title="MCP HTTP Server", version="0.1.0")
settings = Settings()
container = build_container()
REGISTRY = build_tool_registry()


PROTOCOL_VERSION = "2025-03-26"  # aligns with current spec draft dates

# ---------- Security: Origin validation & Bearer token ----------

def _origin_allowed(req: Request) -> bool:
    origin = req.headers.get("origin")
    if not origin:
        return settings.MCP_HTTP_ALLOW_NO_ORIGIN
    allowed = {o.strip().lower() for o in settings.MCP_HTTP_ALLOWED_ORIGINS.split(",") if o.strip()}
    return origin.lower() in allowed

def _require_auth(req: Request):
    auth = req.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth.split(" ", 1)[1]
    if token != settings.MCP_HTTP_BEARER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid Bearer token")

@app.middleware("http")
async def origin_validation_mw(request: Request, call_next):
    # MCP spec requires Origin validation to prevent DNS rebinding
    # If provided and not allowed → 403
    if not _origin_allowed(request):
        return JSONResponse({"error": {"code": 403, "message": "Forbidden origin"}}, status_code=403)
    return await call_next(request)


def schema_from_model(model: type[BaseModel]) -> Dict[str, Any]:
    # JSON Schema for tool's input parameters
    return model.model_json_schema()


def _jsonrpc_error(id_: Any, code: int, message: str, data: Any | None = None) -> JSONResponse:
    body: Dict[str, Any] = {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}
    if data is not None:
        body["error"]["data"] = data
    return JSONResponse(body)

def _jsonrpc_result(id_: Any, result: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result})



# ---------- MCP JSON-RPC endpoint (Streamable HTTP) ----------

@app.post(settings.MCP_HTTP_PATH)
async def mcp_endpoint(request: Request):
    _require_auth(request)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"Parse error"}})

    id_ = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": id_,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": { "tools": { "listChanged": True } },
                "serverInfo": { "name": "acme-mcp-http", "version": "0.1.0" }
            }
        })

    if method == "tools/list":
        return JSONResponse({"jsonrpc":"2.0","id":id_, "result": list_tools_payload(REGISTRY)})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            result = dispatch_tool_call(REGISTRY, name, args)
        except KeyError as ke:
            return JSONResponse({"jsonrpc":"2.0","id":id_, "error":{"code":-32601,"message":str(ke)}})
        except Exception as e:
            return JSONResponse({"jsonrpc":"2.0","id":id_, "error":{"code":-32603,"message":"Internal error","data":str(e)}})

        content_block = (
            {"type": "json", "json": result}
            if isinstance(result, (dict, list))
            else {"type": "text", "text": str(result)}
        )
        return JSONResponse({"jsonrpc":"2.0","id":id_, "result":{"content":[content_block], "isError": False}})

    return JSONResponse({"jsonrpc":"2.0","id":id_, "error":{"code":-32601,"message": f"Method not found: {method}"}})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.http_app:app",
        host=settings.MCP_HTTP_HOST,
        port=settings.MCP_HTTP_PORT,
        reload=False,
    )
