# app/di.py
from dataclasses import dataclass
from app.config import Settings
from app.services.filesystem import FileSystemService
from app.services.kvstore import KvService
from app.services.httpclient import SafeHttpService
from app.services.validator import JsonValidatorService
from app.services.artifacts import ArtifactService

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
    http = SafeHttpService(allowlist_domains=allow, timeout_sec=s.HTTP_TIMEOUT_SEC, 
                           max_bytes=s.HTTP_MAX_BYTES)

    validator = JsonValidatorService()
    artifact = ArtifactService(
        sandbox_root=s.SANDBOX_ROOT,
        subdir_name=s.ARTIFACTS_SUBDIR,
        max_bytes=s.ARTIFACT_MAX_BYTES,
    )

    return Container(s, fs, kv, http, validator, artifact)
