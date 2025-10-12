# app/services/filesystem.py
from pathlib import Path


class FileSystemService:
    """
    Sandbox all file operations inside SANDBOX_ROOT.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_in_root(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        # Prevent path traversal / symlink escape
        if not str(p).startswith(str(self.root)):
            raise PermissionError("Path escapes sandbox root")
        return p

    def write_text(self, rel_path: str, content: str) -> str:
        p = self._resolve_in_root(rel_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return "OK"

    def read_text(self, rel_path: str) -> str:
        p = self._resolve_in_root(rel_path)
        return p.read_text(encoding="utf-8")
