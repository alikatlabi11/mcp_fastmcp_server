# app/services/artifacts.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import re
import glob
from app.logging import redact_args


SAFE_TAG = re.compile(r"[^a-zA-Z0-9:_\-]+")


def _safe_tag(tag: str) -> str:
    s = SAFE_TAG.sub("_", tag.strip())
    return s or "untagged"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class ArtifactService:
    """
    Append/list NDJSON artifact records under the sandbox:
      .sandbox/<ARTIFACTS_SUBDIR>/<YYYY-MM>/<tag>-NNNN.ndjson

    Rotation: create a new file when current file exceeds max_bytes.
    Redaction: applies to all string fields in 'content' and 'meta'.
    """
    sandbox_root: Path
    subdir_name: str = "artifacts"
    max_bytes: int = 10_000_000  # ~10MB per file

    def __post_init__(self):
        self.base = (self.sandbox_root / self.subdir_name).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    # ---------- Public API ----------

    def append(
        self,
        tag: str,
        content: Any,
        *,
        meta: Optional[Dict[str, Any]] = None,
        corr: Optional[str] = None,
        actor: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> Dict[str, Any]:
        tag_safe = _safe_tag(tag)
        month_dir = self._month_dir()
        month_dir.mkdir(parents=True, exist_ok=True)

        record = {
            "ts": _iso_now(),
            "tag": tag_safe,
            **({"corr": corr} if corr else {}),
            **({"actor": actor} if actor else {}),
            **({"tool": tool} if tool else {}),
            "content": self._redact_obj(content),
            "meta": self._redact_obj(meta) if meta is not None else None,
        }

        # Determine current index file and rotate by size if needed
        path = self._ensure_current_file(month_dir, tag_safe)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return {"ok": True, "file": str(path), "ts": record["ts"]}

    def list(
        self,
        tag: str,
        *,
        limit: int = 50,
        order: str = "desc",  # "desc" (newest first) or "asc"
        months_back: int = 12,  # how many months to scan backwards
    ) -> Dict[str, Any]:
        tag_safe = _safe_tag(tag)
        files = self._files_for_tag(tag_safe, months_back=months_back)
        lines: List[str] = []
        # Read newest files first for "desc"
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    file_lines = f.readlines()
                    lines.extend(file_lines)
                    if len(lines) >= limit:
                        break
            except FileNotFoundError:
                continue

        # Build records (take last N lines collected for desc)
        if order == "desc":
            chosen = list(reversed(lines))[:limit]
        else:
            chosen = lines[:limit]
        records = [json.loads(x) for x in chosen]
        return {"count": len(records), "records": records}

    # ---------- Internals ----------

    def _month_dir(self, dt: Optional[datetime] = None) -> Path:
        dt = dt or datetime.now(timezone.utc)
        return self.base / f"{dt.year:04d}-{dt.month:02d}"

    def _glob_indices(self, month_dir: Path, tag_safe: str) -> List[Path]:
        return sorted(month_dir.glob(f"{tag_safe}-*.ndjson"))

    def _ensure_current_file(self, month_dir: Path, tag_safe: str) -> Path:
        existing = self._glob_indices(month_dir, tag_safe)
        if not existing:
            return month_dir / f"{tag_safe}-0001.ndjson"

        current = existing[-1]
        try:
            sz = current.stat().st_size
        except FileNotFoundError:
            return month_dir / f"{tag_safe}-0001.ndjson"

        if sz >= self.max_bytes:
            # Rotate
            idx = int(current.stem.split("-")[-1])
            next_idx = f"{idx+1:04d}"
            return month_dir / f"{tag_safe}-{next_idx}.ndjson"
        return current

    def _files_for_tag(self, tag_safe: str, months_back: int) -> List[Path]:
        # Scan current month back to N months, newest first
        files: List[Path] = []
        now = datetime.now(timezone.utc)
        for k in range(months_back):
            y = now.year
            m = now.month - k
            while m <= 0:
                y -= 1
                m += 12
            month_dir = self.base / f"{y:04d}-{m:02d}"
            # Add in reverse index order so newest file first
            idx_files = sorted(glob.glob(str(month_dir / f"{tag_safe}-*.ndjson")))
            if idx_files:
                files.extend(reversed([Path(p) for p in idx_files]))
        return files

    def _redact_obj(self, obj: Any) -> Any:
        if obj is None:
            return None
        # Use existing redaction on dicts, but recurse on lists
        if isinstance(obj, dict):
            return redact_args(obj)
        if isinstance(obj, list):
            return [self._redact_obj(x) for x in obj]
        # Pass-through primitives; redact only strings using redact_args helpers
        if isinstance(obj, str):
            return redact_args({"x": obj})["x"]
        return obj
