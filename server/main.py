# server/main.py
from fastmcp import FastMCP

from core.di import build_container
from server.registry import build_tool_registry, register_into_fastmcp


def create_app() -> FastMCP:
    """
    Build DI container, create FastMCP host, and register tools via the single registry.
    This keeps transport concerns separate from tool/service logic.
    """
    container = build_container()
    mcp = FastMCP("AcmeMCP", version="0.1.0")

    # Build unified registry and register into FastMCP (stdio transport)
    registry = build_tool_registry(container)
    register_into_fastmcp(mcp, registry)
    return mcp


if __name__ == "__main__":
    app = create_app()
    # STDIO transport: the MCP client (agent/IDE) launches this process and
    # exchanges JSON-RPC messages on stdin/stdout.
    app.run(transport="stdio")
