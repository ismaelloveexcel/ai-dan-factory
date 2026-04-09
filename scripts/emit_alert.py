#!/usr/bin/env python3
"""
Emit deterministic alert payloads for factory failures.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request

from factory_utils import log_event, maybe_write_result, redact_secrets, validate_webhook_url

STEP_NAME = "emit_alert"
_DEFAULT_DIRECTOR_BASE_URL_ENV = "FACTORY_BASE_URL"
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 2


def _post_webhook(
    *,
    director_base_url: str,
    payload: dict,
    project_id: str,
    timeout: int = 30,
) -> None:
    """POST alert payload to Managing Director webhook (best-effort)."""
    url = director_base_url.rstrip("/") + "/factory/webhook"
    validate_webhook_url(url)
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")

    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="webhook_sent",
                    mode="production",
                    http_status=resp.status,
                    director_url=redact_secrets(url),
                )
            return
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="retrying",
                    mode="production",
                    attempt=attempt + 1,
                    http_status=exc.code,
                    retry_in_seconds=_RETRY_DELAY_SECONDS,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise
        except urllib.error.URLError as exc:
            if attempt < _MAX_RETRIES - 1:
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="retrying",
                    mode="production",
                    attempt=attempt + 1,
                    reason="network_error",
                    retry_in_seconds=_RETRY_DELAY_SECONDS,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit structured alert payload")
    parser.add_argument("--project-id", required=True, help="Project id")
    parser.add_argument("--run-id", required=True, help="Workflow run id")
    parser.add_argument("--run-attempt", required=True, help="Workflow run attempt")
    parser.add_argument("--workflow-url", required=True, help="Workflow URL")
    parser.add_argument("--failure-reason", required=True, help="Concise failure reason")
    parser.add_argument("--error-summary", required=True, help="Expanded error summary")
    parser.add_argument("--result-file", required=True, help="Path for alert payload JSON")
    parser.add_argument(
        "--director-base-url",
        default="",
        help=f"Base URL of Managing Director (defaults to env var {_DEFAULT_DIRECTOR_BASE_URL_ENV})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Log the payload but do not send webhook")
    args = parser.parse_args()

    project_id = args.project_id.strip().lower()
    mode = "dry_run" if args.dry_run else "production"

    payload = {
        "project_id": project_id,
        "run_id": args.run_id.strip(),
        "run_attempt": args.run_attempt.strip(),
        "workflow_url": args.workflow_url.strip(),
        "alert_type": "factory_failure",
        "failure_reason": args.failure_reason.strip(),
        "error_summary": args.error_summary.strip(),
        "status": "failed",
    }
    maybe_write_result(args.result_file, payload)
    print(json.dumps(payload, ensure_ascii=True))

    director_base_url = (
        args.director_base_url.strip()
        or os.environ.get(_DEFAULT_DIRECTOR_BASE_URL_ENV, "").strip()
    )
    if not director_base_url:
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="webhook_skipped",
            mode=mode,
            reason="no_director_url",
        )
        return

    if args.dry_run:
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="webhook_skipped",
            mode=mode,
            reason="dry_run",
        )
        return

    try:
        _post_webhook(
            director_base_url=director_base_url,
            payload=payload,
            project_id=project_id,
        )
    except Exception as exc:
        # Best-effort: log the failure but do not fail the script
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="webhook_failed",
            mode=mode,
            error=redact_secrets(str(exc)),
        )


if __name__ == "__main__":
    main()
