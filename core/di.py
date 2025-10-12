# app/di.py
from dataclasses import dataclass

from core.config import Settings
from core.services.artifacts import ArtifactService
from core.services.filesystem import FileSystemService
from core.services.httpclient import SafeHttpConfig, SafeHttpService
from core.services.kvstore import KvService
from core.services.validator import JsonValidatorService


@dataclass
class Container:
    settings: Settings
    fs_service: FileSystemService
    kv_service: KvService | None
    http_service: SafeHttpService
    validator_service: JsonValidatorService
    artifact_service: ArtifactService


def build_container() -> Container:
    s = Settings()
    fs = FileSystemService(s.SANDBOX_ROOT)

    kv = KvService(s.REDIS_URL) if s.REDIS_URL else None

    allow = {d.strip().lower() for d in s.HTTP_ALLOWLIST.split(",") if d.strip()}
    http = SafeHttpService(
        SafeHttpConfig(
            allowlist_domains=allow,
            verify_ssl=True,  # or path to CA bundle; use False only for local dev
            timeout_sec=12.0,
            max_bytes=1_000_000,  # 1MB hard cap per fetch
            allowed_content_types=("text/html", "text/plain", "application/json"),
            extract_text=True,
            max_extracted_chars=8000,
            user_agent="HyperD-MCP/1.0 (+yourcompany.example)",
        )
    )

    validator = JsonValidatorService()
    artifact = ArtifactService(
        sandbox_root=s.SANDBOX_ROOT,
        subdir_name=s.ARTIFACTS_SUBDIR,
        max_bytes=s.ARTIFACT_MAX_BYTES,
    )

    return Container(s, fs, kv, http, validator, artifact)
