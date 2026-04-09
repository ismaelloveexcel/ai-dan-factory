#!/usr/bin/env python3
"""
Notify the Managing Director via webhook on build completion or failure.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request

from factory_utils import log_event, maybe_write_result, redact_secrets

STEP_NAME = "notify_director"
_DEFAULT_DIRECTOR_BASE_URL_ENV = "FACTORY_BASE_URL"
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 2
_ALLOWED_SCHEMES = ("https://",)


def _validate_url(url: str) -> None:
    """Reject non-HTTPS URLs to prevent SSRF via redirect or misconfiguration."""
    if not any(url.startswith(s) for s in _ALLOWED_SCHEMES):
        raise ValueError(
            f"Director webhook URL must use HTTPS (got {url[:40]}...)"
        )


def _post_webhook(
    *,
    director_base_url: str,
    payload: dict,
    project_id: str,
    mode: str,
    timeout: int = 30,
) -> None:
    url = director_base_url.rstrip("/") + "/factory/webhook"
    _validate_url(url)
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="webhook_sent",
                    mode=mode,
                    http_status=resp.status,
                    director_url=url,
                )
            return
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="retrying",
                    mode=mode,
                    attempt=attempt + 1,
                    http_status=exc.code,
                    retry_in_seconds=_RETRY_DELAY_SECONDS,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise
        except urllib.error.URLError as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="retrying",
                    mode=mode,
                    attempt=attempt + 1,
                    reason="network_error",
                    retry_in_seconds=_RETRY_DELAY_SECONDS,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise

    if last_exc is not None:
        raise last_exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Notify Managing Director webhook on build completion/failure")
    parser.add_argument("--project-id", required=True, help="Project identifier")
    parser.add_argument("--run-id", required=True, help="Workflow run ID")
    parser.add_argument("--status", required=True, choices=["succeeded", "failed"], help="Build outcome")
    parser.add_argument("--deploy-url", default="", help="Deployment URL if available")
    parser.add_argument("--repo-url", default="", help="Repository URL")
    parser.add_argument("--error", default="", help="Error message (optional, for failures)")
    parser.add_argument(
        "--director-base-url",
        default="",
        help=f"Base URL of Managing Director (defaults to env var {_DEFAULT_DIRECTOR_BASE_URL_ENV})",
    )
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    parser.add_argument("--dry-run", action="store_true", help="Log the payload but do not send")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id = args.project_id.strip()

    director_base_url = (
        args.director_base_url.strip()
        or os.environ.get(_DEFAULT_DIRECTOR_BASE_URL_ENV, "").strip()
    )

    payload: dict = {
        "project_id": project_id,
        "run_id": args.run_id.strip(),
        "status": args.status,
        "deploy_url": args.deploy_url.strip(),
        "repo_url": args.repo_url.strip(),
    }
    if args.error.strip():
        payload["error"] = args.error.strip()

    log_event(
        project_id=project_id,
        step=STEP_NAME,
        status="started",
        mode=mode,
        director_base_url=director_base_url or "(none)",
        build_status=args.status,
    )

    if args.dry_run:
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode=mode,
            simulated=True,
            payload=payload,
        )
        maybe_write_result(
            args.result_file,
            {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "success",
                "mode": mode,
                "simulated": True,
                "payload": payload,
            },
        )
        return

    if not director_base_url:
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="skipped",
            mode=mode,
            reason=f"No director base URL configured (set {_DEFAULT_DIRECTOR_BASE_URL_ENV} or --director-base-url)",
        )
        maybe_write_result(
            args.result_file,
            {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "skipped",
                "mode": mode,
                "reason": "no_director_url",
            },
        )
        return

    try:
        _post_webhook(
            director_base_url=director_base_url,
            payload=payload,
            project_id=project_id,
            mode=mode,
        )
        result = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "director_base_url": director_base_url,
        }
        maybe_write_result(args.result_file, result)
        log_event(project_id=project_id, step=STEP_NAME, status="success", mode=mode)
    except Exception as exc:
        error_message = redact_secrets(str(exc))
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            error=error_message,
        )
        maybe_write_result(
            args.result_file,
            {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "failed",
                "mode": mode,
                "error": error_message,
            },
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
