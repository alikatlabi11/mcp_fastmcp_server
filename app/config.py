# app/config.py
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Filesystem sandbox
    SANDBOX_ROOT: Path = Path("./.sandbox")

    # Redis (optional)
    REDIS_URL: str | None = "redis://127.0.0.1:6379/0"

    # HTTP safety
    HTTP_ALLOWLIST: str = "example.com, api.github.com"
    HTTP_TIMEOUT_SEC: float = 10.0
    HTTP_MAX_BYTES: int = 2_000_000

    
    # HTTP MCP transport
    MCP_HTTP_ENABLED: bool = True
    MCP_HTTP_HOST: str = "127.0.0.1"
    MCP_HTTP_PORT: int = 8080
    MCP_HTTP_PATH: str = "/mcp"

    # Security: Bearer token and allowed origins
    MCP_HTTP_BEARER_TOKEN: str = "change-me"         # set in .env for prod
    MCP_HTTP_ALLOWED_ORIGINS: str = "http://localhost, http://127.0.0.1"
    MCP_HTTP_ALLOW_NO_ORIGIN: bool = True            # allow non-browser clients

    # Logging
    LOG_LEVEL: str = "INFO"

    
    # Artifacts (append-only audit)
    ARTIFACTS_SUBDIR: str = "artifacts"   # under SANDBOX_ROOT
    ARTIFACT_MAX_BYTES: int = 10_000_000  # rotate when file exceeds this size

    class Config:
        env_file = ".env"
