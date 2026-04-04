#!/usr/bin/env python3
"""
Trigger a Vercel deployment via Deploy Hook API.

Required environment variables (unless --dry-run):
  - VERCEL_DEPLOY_HOOK_URL
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request


def trigger_deploy(project_id: str, hook_url: str) -> str:
    payload = {
        "project_id": project_id,
        "trigger": "github-factory",
    }
    request = urllib.request.Request(
        url=hook_url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode("utf-8")
            if not body:
                return "[ok] Deployment trigger accepted."
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                return body
            return json.dumps(parsed, ensure_ascii=False)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"[error] Vercel deploy trigger failed ({exc.code}): {error_body}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger a Vercel deployment via Deploy Hook API")
    parser.add_argument("--project-id", required=True, help="Project identifier for logging and payload metadata")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print intended action")
    args = parser.parse_args()

    hook_url = os.environ.get("VERCEL_DEPLOY_HOOK_URL", "").strip()
    if args.dry_run:
        configured = "set" if hook_url else "missing"
        print(f"[dry-run] Would trigger Vercel deploy hook for '{args.project_id}' (hook: {configured})")
        return

    if not hook_url:
        raise SystemExit("[error] VERCEL_DEPLOY_HOOK_URL is required.")

    response = trigger_deploy(project_id=args.project_id, hook_url=hook_url)
    print(f"[ok] Deployment triggered for {args.project_id}")
    print(response)


if __name__ == "__main__":
    main()
