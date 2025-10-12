# app/logging.py
import json
import logging
import os
import re
from typing import Any, Dict

PII_RE = re.compile(r"([\w\.-]+)@([\w\.-]+)")  # naive email redaction


def configure_logging():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def redact_str(s: str) -> str:
    return PII_RE.sub("[redacted-email]", s)


def redact_args(args: Dict[str, Any]) -> Dict[str, Any]:
    safe = json.loads(json.dumps(args))  # shallow copy via JSON
    for k, v in list(safe.items()):
        if isinstance(v, str):
            safe[k] = redact_str(v)
    return safe


def log_tool_call(logger: logging.Logger, name: str, args: Dict[str, Any]):
    logger.info("tool_call %s %s", name, redact_args(args))
