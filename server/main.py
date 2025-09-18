# server/main.py
from fastmcp import FastMCP
from app.di import build_container
from server.tools.artifacts import register_artifact_tools
from server.tools.files import register_file_tools
from server.tools.json_validate import register_json_tools
from server.tools.kv import register_kv_tools
from server.tools.http_fetch import register_http_tools

def create_app() -> FastMCP:
    """
    Build DI container, create FastMCP host, and register tools.
    Keep the server (protocol) separate from tool/service logic.
    """
    container = build_container()

    mcp = FastMCP("AcmeMCP", version="0.1.0")

    # Register tools (thin adapters)
    register_file_tools(mcp, container.fs_service)
    register_http_tools(mcp, container.http_service)

    
    register_json_tools(mcp, container.validator_service)
    register_artifact_tools(mcp, container.artifact_service)

    
    # KV tools are optional — only register if Redis URL configured
    if container.settings.REDIS_URL:
        register_kv_tools(mcp, container.kv_service)

    return mcp


if __name__ == "__main__":
    app = create_app()
    # stdio transport: client (agent/IDE) launches this process and speaks JSON-RPC on stdin/stdout
    app.run(transport="stdio")
