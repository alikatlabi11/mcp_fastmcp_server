# server/tools/artifacts.py
from __future__ import annotations
from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel, Field
from fastmcp import FastMCP

class ArtifactLogIn(BaseModel):
    tag: str = Field(..., description="Semantic tag, e.g., 'orders:create', 'errors', 'plan'")
    content: Any = Field(..., description="Serializable payload to log (redacted)")
    meta: Optional[Dict[str, Any]] = Field(None, description="Optional metadata (redacted)")
    corr: Optional[str] = Field(None, description="Correlation ID for the run")
    actor: Optional[str] = Field(None, description="Agent identity/version")
    tool: Optional[str] = Field(None, description="Tool name that performed the action")


class ArtifactListIn(BaseModel):
    tag: str = Field(..., description="Tag to list, e.g., 'orders:create'")
    limit: int = Field(50, ge=1, le=1000, description="Max number of records to return")
    order: Literal["desc", "asc"] = Field(
        "desc", description="Return newest first ('desc') or oldest first ('asc')"
    )
    months_back: int = Field(
        12, ge=1, le=36, description="How many months of history to scan backwards"
    )


def register_artifact_tools(mcp: FastMCP, artifact_service):
    @mcp.tool(
        name="artifact_log",
        description="Append an immutable artifact record (NDJSON) under the " \
        "sandboxed artifacts directory.",
    )
    def artifact_log(input: ArtifactLogIn) -> Dict[str, Any]:
        return artifact_service.append(
            input.tag,
            input.content,
            meta=input.meta,
            corr=input.corr,
            actor=input.actor,
            tool=input.tool,
        )

    @mcp.tool(
        name="artifact_list",
        description="List recent artifact records for a tag (newest first by default).",
    )
    def artifact_list(input: ArtifactListIn) -> Dict[str, Any]:
        return artifact_service.list(
            input.tag, limit=input.limit, order=input.order, months_back=input.months_back
        )
