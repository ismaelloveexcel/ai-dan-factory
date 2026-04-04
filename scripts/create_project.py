#!/usr/bin/env python3
"""
Create a GitHub repository from a template repository.

Features:
- strict input validation
- idempotency / duplicate protection
- retry logic for transient network/API failures
- structured JSON logs and machine-readable result file
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from factory_utils import log_event, maybe_write_result

STEP_NAME = "create_repo"
RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class ApiRequestError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _resolve_template_defaults() -> tuple[str, str]:
    owner = os.environ.get("TEMPLATE_OWNER", "").strip()
    repo = os.environ.get("TEMPLATE_REPO", "").strip()
    if owner and repo:
        return owner, repo

    current_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if "/" in current_repo:
        fallback_owner, fallback_repo = current_repo.split("/", 1)
        return owner or fallback_owner, repo or fallback_repo

    return owner, repo


def _github_request(
    *,
    method: str,
    path: str,
    token: str,
    project_id: str,
    mode: str,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
    max_retries: int = 3,
) -> tuple[int, dict[str, Any]]:
    url = f"https://api.github.com{path}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None

    for attempt in range(max_retries + 1):
        request = urllib.request.Request(url=url, data=body, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        request.add_header("Authorization", f"Bearer {token}")
        if body is not None:
            request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                return response.status, parsed
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
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
            raise ApiRequestError(f"GitHub API {method} {path} failed: HTTP {exc.code}: {error_body}", exc.code) from exc
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
            raise ApiRequestError(f"GitHub API {method} {path} failed: {exc}") from exc


def _github_repo_url(owner: str, project_id: str) -> str:
    return f"https://github.com/{owner}/{project_id}"


def _resolve_target_owner(
    *,
    requested_owner: str,
    token: str,
    project_id: str,
    mode: str,
    idempotency_key: str,
    timeout: int,
    max_retries: int,
) -> str:
    if requested_owner.strip():
        return requested_owner.strip()
    _, data = _github_request(
        method="GET",
        path="/user",
        token=token,
        project_id=project_id,
        mode=mode,
        idempotency_key=idempotency_key,
        timeout=timeout,
        max_retries=max_retries,
    )
    login = str(data.get("login", "")).strip()
    if not login:
        raise ApiRequestError("Unable to resolve authenticated GitHub user.")
    return login


def _repo_exists(
    *,
    owner: str,
    repo: str,
    token: str,
    project_id: str,
    mode: str,
    idempotency_key: str,
    timeout: int,
    max_retries: int,
) -> tuple[bool, str]:
    owner_path = urllib.parse.quote(owner, safe="")
    repo_path = urllib.parse.quote(repo, safe="")
    try:
        _, data = _github_request(
            method="GET",
            path=f"/repos/{owner_path}/{repo_path}",
            token=token,
            project_id=project_id,
            mode=mode,
            idempotency_key=idempotency_key,
            timeout=timeout,
            max_retries=max_retries,
        )
    except ApiRequestError as exc:
        if exc.status_code == 404:
            return False, _github_repo_url(owner, repo)
        raise
    repo_url = str(data.get("html_url", _github_repo_url(owner, repo))).strip()
    return True, repo_url


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a GitHub repository from a template repository")
    parser.add_argument("--project-id", required=True, help="Repository slug to create (example: acme-saas)")
    parser.add_argument("--org", default="", help="GitHub org/user that will own the repository")
    parser.add_argument("--template-owner", default="", help="Template repository owner")
    parser.add_argument("--template-repo", default="", help="Template repository name")
    parser.add_argument("--idempotency-key", default="", help="Idempotency key for deduplication/audit")
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    parser.add_argument("--public", action="store_true", help="Create a public repository (default: private)")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print intended action")
    parser.add_argument("--request-timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--max-retries", type=int, default=3, help="Retries for transient API/network failures")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id = args.project_id.strip()
    result_file = args.result_file
    idempotency_key = args.idempotency_key.strip()

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode=mode, idempotency_key=idempotency_key)
    try:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", project_id):
            raise ApiRequestError("project_id must be a safe slug: lowercase letters, numbers, hyphens.")

        default_template_owner, default_template_repo = _resolve_template_defaults()
        template_owner = (args.template_owner or default_template_owner).strip()
        template_repo = (args.template_repo or default_template_repo).strip()
        if not template_owner or not template_repo:
            raise ApiRequestError(
                "Template repository is not configured. "
                "Set TEMPLATE_OWNER and TEMPLATE_REPO or pass --template-owner/--template-repo."
            )

        if args.dry_run:
            target_owner = args.org.strip() or "<current-authenticated-user>"
            repo_url = _github_repo_url(target_owner, project_id)
            result_payload = {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "success",
                "mode": mode,
                "idempotency_key": idempotency_key,
                "already_exists": False,
                "created": False,
                "repo_url": repo_url,
                "simulated": True,
            }
            maybe_write_result(result_file, result_payload)
            log_event(
                project_id=project_id,
                step=STEP_NAME,
                status="success",
                mode=mode,
                idempotency_key=idempotency_key,
                repo_url=repo_url,
                simulated=True,
            )
            return

        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            raise ApiRequestError("GITHUB_TOKEN is required.")

        target_owner = _resolve_target_owner(
            requested_owner=args.org,
            token=token,
            project_id=project_id,
            mode=mode,
            idempotency_key=idempotency_key,
            timeout=args.request_timeout,
            max_retries=args.max_retries,
        )
        repo_exists, repo_url = _repo_exists(
            owner=target_owner,
            repo=project_id,
            token=token,
            project_id=project_id,
            mode=mode,
            idempotency_key=idempotency_key,
            timeout=args.request_timeout,
            max_retries=args.max_retries,
        )
        if repo_exists:
            result_payload = {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "success",
                "mode": mode,
                "idempotency_key": idempotency_key,
                "already_exists": True,
                "created": False,
                "repo_url": repo_url,
            }
            maybe_write_result(result_file, result_payload)
            log_event(
                project_id=project_id,
                step=STEP_NAME,
                status="success",
                mode=mode,
                idempotency_key=idempotency_key,
                already_exists=True,
                repo_url=repo_url,
            )
            return

        payload: dict[str, Any] = {
            "name": project_id,
            "private": not args.public,
            "description": f"Generated by GitHub Factory for project {project_id}",
            "include_all_branches": False,
            "owner": target_owner,
        }

        try:
            _, create_result = _github_request(
                method="POST",
                path=f"/repos/{urllib.parse.quote(template_owner, safe='')}/{urllib.parse.quote(template_repo, safe='')}/generate",
                token=token,
                payload=payload,
                project_id=project_id,
                mode=mode,
                idempotency_key=idempotency_key,
                timeout=args.request_timeout,
                max_retries=args.max_retries,
            )
            repo_url = str(create_result.get("html_url", _github_repo_url(target_owner, project_id)))
            created = True
            already_exists = False
        except ApiRequestError as exc:
            if exc.status_code == 422:
                repo_exists, repo_url = _repo_exists(
                    owner=target_owner,
                    repo=project_id,
                    token=token,
                    project_id=project_id,
                    mode=mode,
                    idempotency_key=idempotency_key,
                    timeout=args.request_timeout,
                    max_retries=args.max_retries,
                )
                if repo_exists:
                    created = False
                    already_exists = True
                else:
                    raise
            else:
                raise

        result_payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "idempotency_key": idempotency_key,
            "already_exists": already_exists,
            "created": created,
            "repo_url": repo_url,
        }
        maybe_write_result(result_file, result_payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode=mode,
            idempotency_key=idempotency_key,
            already_exists=already_exists,
            created=created,
            repo_url=repo_url,
        )
    except ApiRequestError as exc:
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
