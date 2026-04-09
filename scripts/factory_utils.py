#!/usr/bin/env python3
"""
Shared utilities for factory scripts.
"""

from __future__ import annotations

import hashlib
import ipaddress as _ipaddress
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SENSITIVE_ENV_VARS = ("GITHUB_TOKEN", "FACTORY_GITHUB_TOKEN", "VERCEL_DEPLOY_HOOK_URL", "FACTORY_BASE_URL")


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
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent)) as tmp_file:
            tmp_file.write(contents)
            temp_path = Path(tmp_file.name)
        temp_path.replace(path)
    except BaseException:
        if temp_path is not None and temp_path.exists():
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


def resolve_and_validate_ip(hostname: str) -> None:
    """Resolve hostname to IP and reject private/reserved addresses.

    This provides DNS-rebinding protection by validating the *resolved*
    address rather than only the hostname string.
    """
    import socket

    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Cannot resolve — allow through (will fail at connection time)
        return
    for family, _type, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            addr = _ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if addr.is_loopback or addr.is_private or addr.is_reserved or addr.is_link_local:
            raise ValueError(
                f"Webhook URL resolves to blocked address: {ip_str}"
            )


def validate_webhook_url(url: str) -> None:
    """Reject invalid or non-HTTPS webhook URLs to mitigate SSRF risks.

    Checks:
      - HTTPS scheme required
      - Hostname must be present (via ``netloc`` and ``hostname``)
      - No embedded credentials or fragments
      - Hostname normalized (lowercase, trailing dot stripped) and checked
        against localhost names
      - IP literals in private, reserved, loopback, or link-local ranges
        are rejected via the ``ipaddress`` module
      - DNS resolution checked to prevent DNS rebinding attacks
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(
            f"Webhook URL must use HTTPS (got scheme={parsed.scheme!r})"
        )
    if not parsed.netloc or not parsed.hostname:
        raise ValueError("Webhook URL must include a valid HTTPS host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Webhook URL must not include embedded credentials")
    if parsed.fragment:
        raise ValueError("Webhook URL must not include a fragment")

    # Normalize: lowercase + strip trailing dot (FQDN form)
    hostname = parsed.hostname.lower().rstrip(".")

    _BLOCKED_HOSTNAMES = {"localhost"}
    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Webhook URL must not target localhost: '{hostname}'")

    # Reject IP literals in private/reserved/loopback/link-local ranges
    try:
        addr = _ipaddress.ip_address(hostname)
    except ValueError:
        # hostname is not an IP literal — resolve DNS to check actual IPs
        resolve_and_validate_ip(hostname)
    else:
        if addr.is_loopback or addr.is_private or addr.is_reserved or addr.is_link_local:
            raise ValueError(
                f"Webhook URL must not target private/reserved address: '{hostname}'"
            )
