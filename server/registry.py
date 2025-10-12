# server/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Type

from pydantic import BaseModel

from core.di import Container
from server.tools.artifacts import ArtifactListIn, ArtifactLogIn

# Import only the Pydantic input models (no business logic here)
from server.tools.files import FsReadIn, FsWriteIn
from server.tools.http_fetch import FetchIn
from server.tools.json_validate import JsonValidateIn
from server.tools.kv import KvGetIn, KvPutIn


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

    def __init__(self, container: Container):
        self.container = container

    # ----- Filesystem
    def fs_write(self, args: FsWriteIn) -> str:
        return self.container.fs_service.write_text(args.path, args.content)

    def fs_read(self, args: FsReadIn) -> str:
        return self.container.fs_service.read_text(args.path)

    # ----- HTTP fetch
    def http_fetch(self, args: FetchIn) -> dict:
        return self.container.http_service.fetch(
            str(args.url), args.method, args.headers, args.body
        )

    # ----- JSON Schema validation
    def json_validate(self, args: JsonValidateIn) -> dict:
        return self.container.validator_service.validate(args.instance, args.schema, args.draft)

    # ----- Artifacts
    def artifact_log(self, args: ArtifactLogIn) -> dict:
        return self.container.artifact_service.append(
            args.tag,
            args.content,
            meta=args.meta,
            corr=args.corr,
            actor=args.actor,
            tool=args.tool,
        )

    def artifact_list(self, args: ArtifactListIn) -> dict:
        return self.container.artifact_service.list(
            args.tag, limit=args.limit, order=args.order, months_back=args.months_back
        )

    # ----- KV (optional)
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


def build_tool_registry(container: Container) -> Dict[str, ToolSpec]:
    """
    Build a registry once at startup using DI.
    Transport layers (STDIO/HTTP) read from this registry to expose tools.
    """

    handlers = ToolHandlers(container)
    disabled = container.settings.disabled_tools()
    reg: Dict[str, ToolSpec] = {}

    def maybe_add(name: str, spec: ToolSpec):
        if name not in disabled:
            reg[name] = spec

    maybe_add(
        "fs_write",
        ToolSpec(
            name="fs_write",
            description="Write a text file under sandbox root",
            input_model=FsWriteIn,
            handler=handlers.fs_write,
        ),
    )

    maybe_add(
        "fs_read",
        ToolSpec(
            name="fs_read",
            description="Read a text file under sandbox root",
            input_model=FsReadIn,
            handler=handlers.fs_read,
        ),
    )

    maybe_add(
        "http_fetch",
        ToolSpec(
            name="http_fetch",
            description="Fetch a URL with allowlist, timeouts, and SSRF safeguards",
            input_model=FetchIn,
            handler=handlers.http_fetch,
        ),
    )

    maybe_add(
        "json_validate",
        ToolSpec(
            name="json_validate",
            description="Validate a JSON instance against a JSON Schema",
            input_model=JsonValidateIn,
            handler=handlers.json_validate,
        ),
    )

    maybe_add(
        "artifact_log",
        ToolSpec(
            name="artifact_log",
            description="Append an immutable artifact record",
            input_model=ArtifactLogIn,
            handler=handlers.artifact_log,
        ),
    )

    maybe_add(
        "artifact_list",
        ToolSpec(
            name="artifact_list",
            description="List recent artifact records for a tag",
            input_model=ArtifactListIn,
            handler=handlers.artifact_list,
        ),
    )

    if container.settings.REDIS_URL:
        maybe_add(
            "kv_put",
            ToolSpec(
                name="kv_put",
                description="Put a key/value pair with optional TTL",
                input_model=KvPutIn,
                handler=handlers.kv_put,
            ),
        )
        maybe_add(
            "kv_get",
            ToolSpec(
                name="kv_get",
                description="Get the value for a key",
                input_model=KvGetIn,
                handler=handlers.kv_get,
            ),
        )

    return reg


def list_tools_payload(registry: Dict[str, ToolSpec]) -> Dict[str, Any]:
    """
    Produce the `tools/list` payload body as per MCP Tools spec.
    """
    tools = []
    for spec in registry.values():
        tools.append(
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": _schema_from_model(spec.input_model),
            }
        )
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
    Register all registry tools into a FastMCP STDIO host.
    This keeps STDIO and HTTP transports in sync without duplication.

    Important: FastMCP tools must NOT use **kwargs.
    We construct a function that takes a single, explicitly-typed Pydantic model
    and set its __annotations__ at runtime so FastMCP can derive the schema.
    """
    for spec in registry.values():
        Model = spec.input_model  # Pydantic model class

        def make_tool(spec: ToolSpec, Model: Type[BaseModel]):
            # NOTE: do NOT add **kwargs here—FastMCP won't accept it.
            def tool_handler(input_obj):
                return spec.handler(input_obj)

            # Help FastMCP introspection: set a stable name, docstring, and annotations
            safe_name = spec.name.replace("-", "_")
            tool_handler.__name__ = f"{safe_name}_tool"
            tool_handler.__doc__ = spec.description
            tool_handler.__annotations__ = {"input_obj": Model, "return": Any}
            return tool_handler

        mcp.tool(name=spec.name, description=spec.description)(make_tool(spec, Model))
