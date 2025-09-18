# server/tools/json_validate.py
from __future__ import annotations
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field
from fastmcp import FastMCP


class JsonValidateIn(BaseModel):
    instance: Union[str, Dict[str, Any], list] = Field(
        ..., description="JSON instance (object/array) or stringified JSON"
    )
    schema: Union[str, Dict[str, Any]] = Field( # type: ignore
        ..., description="JSON Schema (object) or stringified JSON"
    )
    draft: str = Field(
        "2020-12",
        description="JSON Schema draft: '2020-12' (default), '2019-09', or '7'",
    )


def register_json_tools(mcp: FastMCP, validator_service):
    @mcp.tool(
        name="json_validate",
        description="Validate a JSON instance against a JSON Schema (draft 2020-12 by default).",
    )
    def json_validate(input: JsonValidateIn) -> Dict[str, Any]:
        # Pass through directly to service
        return validator_service.validate(input.instance, input.schema, input.draft)
