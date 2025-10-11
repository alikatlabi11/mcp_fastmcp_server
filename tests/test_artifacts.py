# tests/test_artifacts.py
from pathlib import Path
import json

from app.services.artifacts import ArtifactService

# tests/test_artifacts.py (optional debugging aid)


def test_artifact_append_and_list(tmp_path: Path):
    svc = ArtifactService(sandbox_root=tmp_path, subdir_name="artifacts", max_bytes=1000000)
    svc.append("orders:create", {"id": "O-1", "email": "john.doe@example.com"}, meta={"note": "ok"})
    svc.append("orders:create", {"id": "O-2", "email": "jane@example.com"}, meta={"note": "ok"})

    out = svc.list("orders:create", limit=2, order="desc")
    assert out["count"] == 2

    # Ensure the month directory actually has at least one ndjson file
    y_m = next((p for p in (tmp_path / "artifacts").iterdir() if p.is_dir()), None)
    assert y_m is not None
    assert list(y_m.glob("orders_create-*.ndjson"))  # tag sanitized on Windows
