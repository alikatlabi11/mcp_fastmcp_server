# tests/conftest.py
import importlib
import sys
from typing import Dict, Iterator

import pytest
from fastapi.testclient import TestClient


def _reload_http_app() -> object:
    """
    Import (or reimport) server.http_app after env changes so Settings() rebinds.
    """
    module_name = "server.http_app"
    if module_name in sys.modules:
        del sys.modules[module_name]
    import server.http_app as http_app  # type: ignore

    importlib.reload(http_app)
    return http_app.app


@pytest.fixture
def http_client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[TestClient]:
    """
    Default HTTP client with:
      - sandbox under tmp_path
      - KV disabled (REDIS_URL="")
      - allow-no-origin=True (so tests need no Origin header)
      - fixed bearer token for auth tests
    """
    monkeypatch.setenv("SANDBOX_ROOT", str(tmp_path))
    monkeypatch.setenv("REDIS_URL", "")  # disable kv tools in registry
    monkeypatch.setenv("MCP_HTTP_BEARER_TOKEN", "test-token")
    # Keep allow-no-origin True so we don't need an Origin header unless we test security:
    monkeypatch.setenv("MCP_HTTP_ALLOW_NO_ORIGIN", "true")
    # Allowed origins list (used only when MCP_HTTP_ALLOW_NO_ORIGIN=false)
    monkeypatch.setenv("MCP_HTTP_ALLOWED_ORIGINS", "http://allowed.test, http://localhost")

    http_app = _reload_http_app()
    client = TestClient(http_app)
    yield client


@pytest.fixture
def registry_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Dict[str, Dict]:
    """
    Snapshot of the registry content (names → ToolSpec) built with the same env as http_client,
    so we can compare HTTP tools/list vs registry.
    """
    monkeypatch.setenv("SANDBOX_ROOT", str(tmp_path))
    monkeypatch.setenv("REDIS_URL", "")  # disable kv
    from core.di import build_container
    from server.registry import build_tool_registry

    container = build_container()
    reg = build_tool_registry(container)
    # Return a simple structure for comparison
    return {
        name: {"description": spec.description, "model": spec.input_model}
        for name, spec in reg.items()
    }


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    return {"Authorization": "Bearer test-token"}
