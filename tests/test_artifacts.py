# tests/test_artifacts.py
from pathlib import Path
import json

from app.services.artifacts import ArtifactService

def test_artifact_append_and_list(tmp_path: Path):
    svc = ArtifactService(sandbox_root=tmp_path, subdir_name="artifacts", max_bytes=1000000)

    # Append two records
    svc.append("orders:create", {"id": "O-1", "email": "john.doe@example.com"}, meta={"note": "ok"})
    svc.append("orders:create", {"id": "O-2", "email": "jane@example.com"}, meta={"note": "ok"})

    # List newest first
    out = svc.list("orders:create", limit=2, order="desc")
    assert out["count"] == 2
    ids = [r["content"]["id"] for r in out["records"]]
    assert ids == ["O-2", "O-1"]

    # Redaction check (emails should be redacted in content/meta)
    assert out["records"][0]["content"]["email"] != "jane@example.com"
