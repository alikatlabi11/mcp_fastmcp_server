# server/tools/kv.py
from pydantic import BaseModel, Field
from fastmcp import FastMCP


class KvPutIn(BaseModel):
    key: str = Field(..., min_length=1, description="Key to set")
    value: str = Field(..., description="Value to store")
    ttlSec: int | None = Field(
        None, ge=1, le=7 * 24 * 3600, description="Optional TTL in seconds (max 7 days)"
    )


class KvGetIn(BaseModel):
    key: str = Field(..., min_length=1, description="Key to get")


def register_kv_tools(mcp: FastMCP, kv_service):
    @mcp.tool(name="kv_put", description="Put a key/value pair with optional TTL (seconds)")
    def kv_put(input: KvPutIn) -> str:
        return kv_service.put(input.key, input.value, input.ttlSec)

    @mcp.tool(name="kv_get", description="Get the value for a key (or empty string if missing)")
    def kv_get(input: KvGetIn) -> str:
        val = kv_service.get(input.key)
        return "" if val is None else val
