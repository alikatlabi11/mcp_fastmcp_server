from pydantic import BaseModel, Field, HttpUrl
from fastmcp import FastMCP
from typing import Dict, Optional

class FetchIn(BaseModel):
    url: HttpUrl
    method: str = Field("GET", pattern="^(GET|POST|PUT|PATCH|DELETE|HEAD)$")
    headers: Optional[Dict[str, str]] = None
    body: Optional[str] = None

def register_http_tools(mcp: FastMCP, http_service):
    @mcp.tool(name="http_fetch", description="Fetch a URL with allowlist, timeouts, and SSRF safeguards")
    def http_fetch(input: FetchIn) -> dict:
        return http_service.fetch(str(input.url), input.method, input.headers, input.body)
