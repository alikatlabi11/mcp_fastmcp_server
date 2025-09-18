# server/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Type, Optional, List
from pydantic import BaseModel

from app.di import build_container
from app.config import Settings

# Import only the Pydantic input models from existing tool modules.
from server.tools.files import FsWriteIn, FsReadIn
from server.tools.http_fetch import FetchIn
from server.tools.json_validate import JsonValidateIn
from server.tools.artifacts import ArtifactLogIn, ArtifactListIn
# KV models are optional (only if Redis configured)
from server.tools.kv import KvPutIn, KvGetIn


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: Type[BaseModel]
    handler: Callable[[BaseModel], Any]


class ToolHandlers:
    """
    Named handlers for each tool (no lambdas).
    Keeps all cross-cutting logic and observability in one place.
    """
    def __init__(self):
        self.container = build_container()

    # ---- Filesystem
    def fs_write(self, args: FsWriteIn) -> str:
        return self.container.fs_service.write_text(args.path, args.content)

    def fs_read(self, args: FsReadIn) -> str:
        return self.container.fs_service.read_text(args.path)

    # ---- HTTP fetch
    def http_fetch(self, args: FetchIn) -> dict:
        return self.container.http_service.fetch(str(args.url), args.method, args.headers, args.body)

    # ---- JSON Schema validation
    def json_validate(self, args: JsonValidateIn) -> dict:
        return self.container.validator_service.validate(args.instance, args.schema, args.draft)

    # ---- Artifacts
    def artifact_log(self, args: ArtifactLogIn) -> dict:
        return self.container.artifact_service.append(
            args.tag, args.content, meta=args.meta, corr=args.corr, actor=args.actor, tool=args.tool
        )

    def artifact_list(self, args: ArtifactListIn) -> dict:
        return self.container.artifact_service.list(
            args.tag, limit=args.limit, order=args.order, months_back=args.months_back
        )

    # ---- KV (optional)
    def kv_put(self, args: KvPutIn) -> str:
        if self.container.kv_service is None:
            raise RuntimeError("KV service not configured")
        return self.container.kv_service.put(args.key, args.value, args.ttlSec)

    def kv_get(self, args: KvGetIn) -> str:
        if self.container.kv_service is None:
            raise RuntimeError("KV service not configured")
        return self.container.kv_service.get(args.key) or ""


def _schema_from_model(model: Type[BaseModel]) -> Dict[str, Any]:
    return model.model_json_schema()


def build_tool_registry() -> Dict[str, ToolSpec]:
    """
    Build a registry once at startup using DI.
    Transport layers (stdio/HTTP) read from this registry to expose tools.
    """
    settings = Settings()
    handlers = ToolHandlers()

    reg: Dict[str, ToolSpec] = {
        "fs_write": ToolSpec(
            name="fs_write",
            description="Write a text file under sandbox root",
            input_model=FsWriteIn,
            handler=handlers.fs_write,
        ),
        "fs_read": ToolSpec(
            name="fs_read",
            description="Read a text file under sandbox root",
            input_model=FsReadIn,
            handler=handlers.fs_read,
        ),
        "http_fetch": ToolSpec(
            name="http_fetch",
            description="Fetch a URL with allowlist, timeouts, and SSRF safeguards",
            input_model=FetchIn,
            handler=handlers.http_fetch,
        ),
        "json_validate": ToolSpec(
            name="json_validate",
            description="Validate a JSON instance against a JSON Schema (draft 2020-12 by default).",
            input_model=JsonValidateIn,
            handler=handlers.json_validate,
        ),
        "artifact_log": ToolSpec(
            name="artifact_log",
            description="Append an immutable artifact record (NDJSON) under the sandboxed artifacts directory.",
            input_model=ArtifactLogIn,
            handler=handlers.artifact_log,
        ),
        "artifact_list": ToolSpec(
            name="artifact_list",
            description="List recent artifact records for a tag (newest first by default).",
            input_model=ArtifactListIn,
            handler=handlers.artifact_list,
        ),
    }

    # Register KV tools only when Redis is configured.
    if settings.REDIS_URL:
        reg["kv_put"] = ToolSpec(
            name="kv_put",
            description="Put a key/value pair with optional TTL (seconds)",
            input_model=KvPutIn,
            handler=handlers.kv_put,
        )
        reg["kv_get"] = ToolSpec(
            name="kv_get",
            description="Get the value for a key",
            input_model=KvGetIn,
            handler=handlers.kv_get,
        )

    return reg


def list_tools_payload(registry: Dict[str, ToolSpec]) -> Dict[str, Any]:
    """
    Produce the `tools/list` payload body as per MCP Tools spec.
    """
    tools = []
    for spec in registry.values():
        tools.append({
            "name": spec.name,
            "description": spec.description,
            "inputSchema": _schema_from_model(spec.input_model),
        })
    return {"tools": tools}


def dispatch_tool_call(registry: Dict[str, ToolSpec], name: str, arguments: Dict[str, Any]) -> Any:
    """
    Validate args with the tool's Pydantic model, then invoke the named handler.
    """
    if name not in registry:
        raise KeyError(f"Tool not found: {name}")
    spec = registry[name]
    args_obj = spec.input_model(**arguments)
    return spec.handler(args_obj)


def register_into_fastmcp(mcp, registry: Dict[str, ToolSpec]) -> None:
    """
    Register all registry tools into a FastMCP stdio host.
    This keeps stdio and HTTP transports in sync without duplication.
    """
    for spec in registry.values():
        # Create a local closure so each handler binds to its spec
        def make_tool(spec: ToolSpec):
            def tool_handler(input_obj: spec.input_model):
                return spec.handler(input_obj)
            return tool_handler

        # FastMCP's decorator returns a decorator we can call dynamically.
        mcp.tool(name=spec.name, description=spec.description)(make_tool(spec))
