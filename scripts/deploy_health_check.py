#!/usr/bin/env python3
"""
Post-deploy health check for deployment URLs.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

from factory_utils import log_event, maybe_write_result, validate_webhook_url

STEP_NAME = "deploy_health_check"


class HealthCheckError(Exception):
    pass


def check_url(url: str, timeout_seconds: int) -> tuple[int, str]:
    validate_webhook_url(url)
    request = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        status_code = response.status
        body = response.read().decode("utf-8", errors="replace")
    return status_code, body


def main() -> None:
    parser = argparse.ArgumentParser(description="Run post-deploy health checks")
    parser.add_argument("--project-id", required=True, help="Project identifier")
    parser.add_argument("--deployment-url", required=True, help="Deployment URL to verify")
    parser.add_argument("--result-file", default="", help="Path to write result JSON")
    parser.add_argument("--attempts", type=int, default=3, help="Health check attempts")
    parser.add_argument("--delay-seconds", type=int, default=5, help="Delay between attempts")
    parser.add_argument("--timeout-seconds", type=int, default=10, help="Request timeout")
    parser.add_argument("--idempotency-key", default="", help="Idempotency key")
    parser.add_argument("--skip-check", action="store_true", help="Skip checks when URL is unavailable")
    parser.add_argument("--dry-run", action="store_true", help="Simulate health check")
    args = parser.parse_args()

    project_id = args.project_id.strip().lower()
    deployment_url = args.deployment_url.strip()
    idempotency_key = args.idempotency_key.strip()
    mode = "dry_run" if args.dry_run else "production"

    log_event(
        project_id=project_id,
        step=STEP_NAME,
        status="started",
        mode=mode,
        idempotency_key=idempotency_key,
    )

    if args.skip_check or args.dry_run:
        health_status = "simulated" if args.dry_run else "skipped"
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "idempotency_key": idempotency_key,
            "health_status": health_status,
            "failure_reason": "",
            "error_summary": "",
        }
        maybe_write_result(args.result_file, payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode=mode,
            idempotency_key=idempotency_key,
            health_status=health_status,
        )
        return

    if not deployment_url.startswith(("http://", "https://")):
        error_message = "deployment_url is missing or invalid for health check."
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "mode": mode,
            "idempotency_key": idempotency_key,
            "health_status": "failed",
            "failure_reason": "invalid_deployment_url",
            "error_summary": error_message,
        }
        maybe_write_result(args.result_file, payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            idempotency_key=idempotency_key,
            error=error_message,
        )
        raise SystemExit(1)

    try:
        validate_webhook_url(deployment_url)
    except ValueError as exc:
        error_message = f"SSRF protection blocked deployment URL: {exc}"
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "mode": mode,
            "idempotency_key": idempotency_key,
            "health_status": "failed",
            "failure_reason": "ssrf_blocked",
            "error_summary": error_message,
        }
        maybe_write_result(args.result_file, payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            idempotency_key=idempotency_key,
            error=error_message,
        )
        raise SystemExit(2)

    last_error = ""
    for attempt in range(1, max(1, args.attempts) + 1):
        try:
            status_code, body = check_url(deployment_url, args.timeout_seconds)
            if 200 <= status_code < 400:
                payload = {
                    "project_id": project_id,
                    "step": STEP_NAME,
                    "status": "success",
                    "mode": mode,
                    "idempotency_key": idempotency_key,
                    "health_status": "healthy",
                    "http_status": status_code,
                    "failure_reason": "",
                    "error_summary": "",
                }
                maybe_write_result(args.result_file, payload)
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="success",
                    mode=mode,
                    idempotency_key=idempotency_key,
                    health_status="healthy",
                    http_status=status_code,
                )
                return
            last_error = f"HTTP {status_code} returned from deployment."
            _ = body
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code} during health check."
        except urllib.error.URLError as exc:
            last_error = f"Network error during health check: {exc}"

        if attempt < args.attempts:
            time.sleep(max(0, args.delay_seconds))

    payload = {
        "project_id": project_id,
        "step": STEP_NAME,
        "status": "failed",
        "mode": mode,
        "idempotency_key": idempotency_key,
        "health_status": "failed",
        "failure_reason": "deployment_health_check_failed",
        "error_summary": last_error or "Deployment health check failed.",
    }
    maybe_write_result(args.result_file, payload)
    log_event(
        project_id=project_id,
        step=STEP_NAME,
        status="failed",
        mode=mode,
        idempotency_key=idempotency_key,
        error=payload["error_summary"],
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
