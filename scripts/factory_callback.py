#!/usr/bin/env python3
"""
Factory callback — POST build result to the Managing Director /factory/callback.

This is the primary result-delivery mechanism matching the MD's FactoryCallbackPayload:
  project_id, correlation_id, run_id, status, deploy_url, repo_url, error

Authenticated via X-Factory-Secret header when FACTORY_SECRET is set.
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

STEP_NAME = "factory_callback"
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 2


def _post_callback(
    *,
    callback_url: str,
    payload: dict,
    factory_secret: str = "",
    timeout: int = 30,
) -> None:
    """POST the result payload to the MD callback endpoint with auth."""
    validate_webhook_url(callback_url)
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(url=callback_url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if factory_secret:
            req.add_header("X-Factory-Secret", factory_secret)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                log_event(
                    project_id=payload.get("project_id", "unknown"),
                    step=STEP_NAME,
                    status="callback_sent",
                    mode="production",
                    http_status=resp.status,
                    callback_url=redact_secrets(callback_url),
                )
            return
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                log_event(
                    project_id=payload.get("project_id", "unknown"),
                    step=STEP_NAME,
                    status="retrying",
                    mode="production",
                    attempt=attempt + 1,
                    http_status=exc.code,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise
        except urllib.error.URLError as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                log_event(
                    project_id=payload.get("project_id", "unknown"),
                    step=STEP_NAME,
                    status="retrying",
                    mode="production",
                    attempt=attempt + 1,
                    reason="network_error",
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise

    if last_exc is not None:
        raise last_exc


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
    project_id = args.project_id.strip()

    # Build payload matching FactoryCallbackPayload on the MD side
    payload: dict = {
        "project_id": project_id,
        "correlation_id": correlation_id,
        "run_id": args.run_id.strip(),
        "status": args.status,
        "deploy_url": args.deploy_url.strip(),
        "repo_url": args.repo_url.strip(),
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
        _post_callback(callback_url=callback_url, payload=payload, factory_secret=factory_secret)
        log_event(project_id=project_id, step=STEP_NAME, status="success", mode="production")
        maybe_write_result(args.result_file, {"project_id": project_id, "step": STEP_NAME, "status": "success", "mode": "production"})
    except Exception as exc:
        # Best-effort: log but don't fail the workflow
        error_msg = redact_secrets(str(exc))
        log_event(project_id=project_id, step=STEP_NAME, status="failed", error=error_msg)
        maybe_write_result(args.result_file, {"project_id": project_id, "step": STEP_NAME, "status": "failed", "error": error_msg})
        print(f"[{STEP_NAME}] Callback failed (best-effort): {error_msg}", file=sys.stderr, flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
