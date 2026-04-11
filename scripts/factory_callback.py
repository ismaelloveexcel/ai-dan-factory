#!/usr/bin/env python3
"""
Factory callback — POST build result to the Managing Director /factory/callback.

This is the primary result-delivery mechanism matching the MD's FactoryCallbackPayload:
  project_id, correlation_id, run_id, status, deploy_url, repo_url, error

Authenticated via X-Factory-Secret header when FACTORY_SECRET is set.
Also sends X-API-Key header when FACTORY_API_KEY is set (required by MD middleware).
Falls back to the legacy /factory/webhook endpoint if callback_url is not provided.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from factory_utils import log_event, maybe_write_result, redact_secrets, validate_webhook_url

DLQ_FILE = os.environ.get("FACTORY_CALLBACK_DLQ_FILE", "/tmp/factory_callback_dlq.json")

STEP_NAME = "factory_callback"
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_INITIAL_DELAY_SECONDS = 2


def _post_callback(
    *,
    callback_url: str,
    payload: dict,
    factory_secret: str = "",
    api_key: str = "",
    timeout: int = 30,
) -> dict | None:
    """POST the result payload to the MD callback endpoint with auth.

    Returns the parsed JSON ack from the MD on success, or raises on failure.
    """
    validate_webhook_url(callback_url)
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(url=callback_url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "ai-dan-factory/1.0")
        if factory_secret:
            req.add_header("X-Factory-Secret", factory_secret)
        if api_key:
            req.add_header("X-API-Key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                log_event(
                    project_id=payload.get("project_id", "unknown"),
                    step=STEP_NAME,
                    status="callback_sent",
                    mode="production",
                    http_status=resp.status,
                    callback_url=redact_secrets(callback_url),
                )
                try:
                    return json.loads(resp_body)
                except (json.JSONDecodeError, ValueError):
                    return None
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                delay = _INITIAL_DELAY_SECONDS * (2 ** attempt)
                log_event(
                    project_id=payload.get("project_id", "unknown"),
                    step=STEP_NAME,
                    status="retrying",
                    mode="production",
                    attempt=attempt + 1,
                    http_status=exc.code,
                    retry_in_seconds=delay,
                )
                time.sleep(delay)
                continue
            raise
        except urllib.error.URLError as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                delay = _INITIAL_DELAY_SECONDS * (2 ** attempt)
                log_event(
                    project_id=payload.get("project_id", "unknown"),
                    step=STEP_NAME,
                    status="retrying",
                    mode="production",
                    attempt=attempt + 1,
                    reason="network_error",
                    retry_in_seconds=delay,
                )
                time.sleep(delay)
                continue
            raise

    if last_exc is not None:
        raise last_exc


def _append_to_dlq(payload: dict, callback_url: str) -> None:
    import fcntl

    entry = {"callback_url": callback_url, "payload": payload, "retries": 0}
    dlq_path = DLQ_FILE
    try:
        existing: list = []
        try:
            with open(dlq_path, "r", encoding="utf-8") as fh:
                fcntl.flock(fh, fcntl.LOCK_SH)
                existing = json.load(fh)
                fcntl.flock(fh, fcntl.LOCK_UN)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        existing.append(entry)
        with open(dlq_path, "w", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            json.dump(existing, fh, indent=2, ensure_ascii=True)
            fcntl.flock(fh, fcntl.LOCK_UN)
        print(f"[{STEP_NAME}] Payload appended to DLQ: {dlq_path}", file=sys.stderr, flush=True)
    except Exception as dlq_exc:
        print(f"[{STEP_NAME}] DLQ write failed: {dlq_exc}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="POST factory build result to Managing Director callback endpoint"
    )
    parser.add_argument("--project-id", required=True, help="Project identifier")
    parser.add_argument("--correlation-id", default="", help="End-to-end correlation ID")
    parser.add_argument("--callback-url", default="", help="MD callback URL")
    parser.add_argument("--status", required=True, choices=["succeeded", "failed"], help="Build outcome")
    parser.add_argument("--run-id", default="", help="Workflow run ID")
    parser.add_argument("--workflow-url", default="", help="Workflow run URL")
    parser.add_argument("--deploy-url", default="", help="Deployment URL")
    parser.add_argument("--repo-url", default="", help="Repository URL")
    parser.add_argument("--error-summary", default="", help="Error summary for failures")
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    parser.add_argument("--dry-run", action="store_true", help="Log the payload but do not send")
    args = parser.parse_args()

    callback_url = args.callback_url.strip()
    correlation_id = args.correlation_id.strip()
    factory_secret = os.environ.get("FACTORY_SECRET", "").strip()
    factory_api_key = os.environ.get("FACTORY_API_KEY", "").strip()
    project_id = args.project_id.strip()

    # Build payload matching FactoryCallbackPayload on the MD side
    payload: dict = {
        "project_id": project_id,
        "correlation_id": correlation_id,
        "run_id": args.run_id.strip(),
        "status": args.status,
        "deploy_url": args.deploy_url.strip(),
        "repo_url": args.repo_url.strip(),
        "contract_version": "1.0",
    }
    if args.error_summary.strip():
        payload["error"] = args.error_summary.strip()

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode="production" if not args.dry_run else "dry_run")

    if args.dry_run:
        log_event(project_id=project_id, step=STEP_NAME, status="success", mode="dry_run", simulated=True, payload=payload)
        maybe_write_result(args.result_file, {"project_id": project_id, "step": STEP_NAME, "status": "success", "mode": "dry_run", "simulated": True, "payload": payload})
        return 0

    if not callback_url:
        log_event(project_id=project_id, step=STEP_NAME, status="skipped", mode="production", reason="no_callback_url")
        maybe_write_result(args.result_file, {"project_id": project_id, "step": STEP_NAME, "status": "skipped", "reason": "no_callback_url"})
        return 0

    if not correlation_id:
        print(f"[{STEP_NAME}] WARNING: No correlation_id — MD may not match this callback.", file=sys.stderr, flush=True)

    try:
        validate_webhook_url(callback_url)
    except ValueError as exc:
        log_event(project_id=project_id, step=STEP_NAME, status="failed", error=redact_secrets(str(exc)))
        maybe_write_result(args.result_file, {"project_id": project_id, "step": STEP_NAME, "status": "failed", "error": redact_secrets(str(exc))})
        return 1

    try:
        ack = _post_callback(callback_url=callback_url, payload=payload, factory_secret=factory_secret, api_key=factory_api_key)
        ack_status = ack.get("status", "") if ack else ""
        log_event(project_id=project_id, step=STEP_NAME, status="success", mode="production", md_ack_status=ack_status)
        result = {"project_id": project_id, "step": STEP_NAME, "status": "success", "mode": "production"}
        if ack:
            result["md_ack"] = ack
        maybe_write_result(args.result_file, result)
    except Exception as exc:
        error_msg = redact_secrets(str(exc))
        log_event(project_id=project_id, step=STEP_NAME, status="failed", error=error_msg)
        maybe_write_result(args.result_file, {"project_id": project_id, "step": STEP_NAME, "status": "failed", "error": error_msg})
        print(f"[{STEP_NAME}] Callback failed after retries: {error_msg}", file=sys.stderr, flush=True)
        _append_to_dlq(payload, callback_url)
        # Exit non-zero so the workflow step fails visibly and can trigger
        # the alert step — never silently swallow delivery failures.
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
