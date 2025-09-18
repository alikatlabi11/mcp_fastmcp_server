# server/tools/files.py
from pydantic import BaseModel, Field
from fastmcp import FastMCP

class FsWriteIn(BaseModel):
    path: str = Field(..., description="Relative path under sandbox root")
    content: str = Field(..., description="UTF-8 text content to write")


class FsReadIn(BaseModel):
    path: str = Field(..., description="Relative path under sandbox root")


def register_file_tools(mcp: FastMCP, fs_service):
    """
    Very thin tool adapters:
    - validate/deserialize inputs (Pydantic)
    - call the service (business logic + security)
    - return the result
    """

    @mcp.tool(name="fs_write", description="Write a text file under sandbox root")
    def fs_write(input: FsWriteIn) -> str:
        return fs_service.write_text(input.path, input.content)

    @mcp.tool(name="fs_read", description="Read a text file under sandbox root")
    def fs_read(input: FsReadIn) -> str:
        return fs_service.read_text(input.path)
