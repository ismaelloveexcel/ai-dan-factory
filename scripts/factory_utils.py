#!/usr/bin/env python3
"""
Shared utilities for factory scripts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SENSITIVE_ENV_VARS = ("GITHUB_TOKEN", "VERCEL_DEPLOY_HOOK_URL", "FACTORY_GITHUB_TOKEN", "FACTORY_BASE_URL")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_secrets(text: str) -> str:
    redacted = text
    for env_name in SENSITIVE_ENV_VARS:
        secret = os.environ.get(env_name, "")
        if secret:
            redacted = redacted.replace(secret, "***")
    return redacted


def log_event(
    *,
    project_id: str,
    step: str,
    status: str,
    mode: str,
    idempotency_key: str = "",
    error: str = "",
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "project_id": project_id,
        "step": step,
        "status": status,
        "mode": mode,
        "timestamp": utc_timestamp(),
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    if error:
        payload["error"] = redact_secrets(error)
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    print(json.dumps(payload, ensure_ascii=True), flush=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def atomic_write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent))
    temp_path = Path(tmp_file.name)
    try:
        with tmp_file:
            tmp_file.write(contents)
        temp_path.replace(path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def maybe_write_result(result_file: str, payload: dict[str, Any]) -> None:
    if not result_file:
        return
    write_json(Path(result_file).expanduser().resolve(), payload)


def normalize_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized


def stable_idempotency_key(project_id: str, brief: dict[str, str]) -> str:
    digest_source = json.dumps(brief, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
    return f"{project_id}:{digest}"


def validate_webhook_url(url: str) -> str:
    """Validate and return a webhook URL; enforce HTTPS to mitigate SSRF."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Webhook URL must use HTTPS scheme, got '{parsed.scheme}'")
    if not parsed.hostname:
        raise ValueError("Webhook URL has no hostname")
    if parsed.hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError(f"Webhook URL must not target localhost: '{parsed.hostname}'")
    return url
