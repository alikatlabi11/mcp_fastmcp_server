from pathlib import Path

import pytest

from core.services.filesystem import FileSystemService


def test_fs_sandbox_prevents_escape(tmp_path: Path):
    fs = FileSystemService(tmp_path)
    fs.write_text("ok.txt", "ok")
    assert fs.read_text("ok.txt") == "ok"
    with pytest.raises(PermissionError):
        fs.read_text("../escape.txt")
