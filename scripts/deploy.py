#!/usr/bin/env python3
"""
Trigger a Vercel deployment via Deploy Hook API.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request

from factory_utils import log_event, maybe_write_result

STEP_NAME = "deploy"
RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class DeployError(Exception):
    pass


def _extract_deployment_url(raw_body: str) -> str:
    """
    Extract a deployment URL from a Vercel hook response.

    Vercel deploy hooks return {"job": {"id": "...", "state": "pending"}} — no URL.
    This function handles that and falls back gracefully.
    """
    if not raw_body:
        return ""
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        match = re.search(r"https?://[^\s\"']+", raw_body)
        return match.group(0) if match else ""
    if isinstance(parsed, dict):
        for key in ("url", "deployment_url", "target", "inspectorUrl"):
            value = parsed.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
    return ""


def _build_production_url(project_id: str) -> str:
    """
    Construct the predictable Vercel production URL from the project slug.

    When a project is deployed to Vercel, its production domain is always
    https://{project-name}.vercel.app unless a custom domain is configured.
    This gives us a reliable URL even when the deploy hook response has none.
    """
    return f"https://{project_id}.vercel.app"


def trigger_deploy(
    *,
    project_id: str,
    hook_url: str,
    mode: str,
    idempotency_key: str,
    timeout: int,
    max_retries: int,
) -> tuple[str, str]:
    payload = {"project_id": project_id, "trigger": "github-factory", "idempotency_key": idempotency_key}
    encoded_payload = json.dumps(payload).encode("utf-8")

    for attempt in range(max_retries + 1):
        request = urllib.request.Request(
            url=hook_url,
            data=encoded_payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_body = response.read().decode("utf-8")
                deployment_url = _extract_deployment_url(response_body)
                return response_body, deployment_url
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code in RETRYABLE_STATUS_CODES
            if retryable and attempt < max_retries:
                delay = 2**attempt
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="retrying",
                    mode=mode,
                    idempotency_key=idempotency_key,
                    retry_in_seconds=delay,
                    http_status=exc.code,
                )
                time.sleep(delay)
                continue
            raise DeployError(f"Vercel deploy trigger failed: HTTP {exc.code}: {response_body}") from exc
        except urllib.error.URLError as exc:
            if attempt < max_retries:
                delay = 2**attempt
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="retrying",
                    mode=mode,
                    idempotency_key=idempotency_key,
                    retry_in_seconds=delay,
                    reason="network_error",
                )
                time.sleep(delay)
                continue
            raise DeployError(f"Vercel deploy trigger failed: {exc}") from exc

    raise DeployError("Vercel deploy trigger failed after retries.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger a Vercel deployment via Deploy Hook API")
    parser.add_argument("--project-id", required=True, help="Project identifier for logging and payload metadata")
    parser.add_argument("--idempotency-key", default="", help="Idempotency key for deduplication/audit")
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print intended action")
    parser.add_argument("--request-timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--max-retries", type=int, default=3, help="Retries for transient API/network failures")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id = args.project_id.strip()
    idempotency_key = args.idempotency_key.strip()
    result_file = args.result_file

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode=mode, idempotency_key=idempotency_key)
    try:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", project_id):
            raise DeployError("project_id must be a safe slug: lowercase letters, numbers, hyphens.")

        hook_url = os.environ.get("VERCEL_DEPLOY_HOOK_URL", "").strip()
        if not args.dry_run and not hook_url:
            raise DeployError("VERCEL_DEPLOY_HOOK_URL is required.")

        if args.dry_run:
            result_payload = {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "success",
                "mode": mode,
                "idempotency_key": idempotency_key,
                "simulated": True,
                "deployment_status": "simulated",
                "deployment_url": "",
            }
            maybe_write_result(result_file, result_payload)
            log_event(
                project_id=project_id,
                step=STEP_NAME,
                status="success",
                mode=mode,
                idempotency_key=idempotency_key,
                simulated=True,
                deployment_status="simulated",
            )
            return

        _response_body, deployment_url = trigger_deploy(
            project_id=project_id,
            hook_url=hook_url,
            mode=mode,
            idempotency_key=idempotency_key,
            timeout=args.request_timeout,
            max_retries=args.max_retries,
        )

        # Vercel deploy hooks return a job ID, not a URL.
        # Fall back to the predictable production URL from the project slug.
        if not deployment_url:
            deployment_url = _build_production_url(project_id)
            log_event(
                project_id=project_id,
                step=STEP_NAME,
                status="info",
                mode=mode,
                idempotency_key=idempotency_key,
                note="Hook response contained no URL; using predictable production URL.",
                deployment_url=deployment_url,
            )

        result_payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "idempotency_key": idempotency_key,
            "simulated": False,
            "deployment_status": "triggered",
            "deployment_url": deployment_url,
        }
        maybe_write_result(result_file, result_payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode=mode,
            idempotency_key=idempotency_key,
            deployment_status="triggered",
            deployment_url=deployment_url,
        )
    except DeployError as exc:
        error_message = str(exc)
        maybe_write_result(
            result_file,
            {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "failed",
                "mode": mode,
                "idempotency_key": idempotency_key,
                "error": error_message,
            },
        )
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            idempotency_key=idempotency_key,
            error=error_message,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
