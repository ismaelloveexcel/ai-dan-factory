#!/usr/bin/env python3
"""
Inject environment variables into a Vercel project via the Vercel API.

Used by the factory pipeline to ensure newly created products have
the correct Stripe, email, and analytics env vars configured before deploy.

Required env vars:
  VERCEL_TOKEN — Vercel API token with project-edit scope
  VERCEL_TEAM_ID — (optional) Team/org ID if not personal account

Usage:
  python inject_vercel_env.py --project-id my-saas \\
      --env STRIPE_SECRET_KEY=sk_live_xxx \\
      --env RESEND_API_KEY=re_xxx \\
      --env NEXT_PUBLIC_BASE_URL=https://my-saas.vercel.app
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from factory_utils import log_event, redact_secrets

STEP_NAME = "inject_vercel_env"

# Env vars that should only be available server-side
_SERVER_ONLY_PREFIXES = ("STRIPE_SECRET", "STRIPE_WEBHOOK", "RESEND_", "EMAIL_FROM")


def _target_for_key(key: str) -> list[str]:
    """Determine Vercel env var targets (production, preview, development)."""
    # Server-only secrets → production only
    if any(key.startswith(p) for p in _SERVER_ONLY_PREFIXES):
        return ["production"]
    return ["production", "preview"]


def _env_type_for_key(key: str) -> str:
    """Secrets get 'encrypted', public vars get 'plain'."""
    if key.startswith("NEXT_PUBLIC_"):
        return "plain"
    return "encrypted"


def inject_env_vars(
    *,
    project_id: str,
    env_pairs: list[str],
    vercel_token: str,
    team_id: str = "",
    dry_run: bool = False,
) -> list[dict]:
    """Parse KEY=VALUE pairs and push them to Vercel."""
    results = []

    for pair in env_pairs:
        if "=" not in pair:
            print(f"[{STEP_NAME}] WARNING: skipping invalid env pair: {pair}", file=sys.stderr)
            continue

        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or not value:
            continue

        entry = {
            "key": key,
            "value": value,
            "type": _env_type_for_key(key),
            "target": _target_for_key(key),
        }

        if dry_run:
            log_event(
                project_id=project_id,
                step=STEP_NAME,
                status="simulated",
                mode="dry_run",
                env_key=key,
                env_type=entry["type"],
                targets=entry["target"],
            )
            results.append({"key": key, "status": "simulated"})
            continue

        # POST to Vercel API
        url = f"https://api.vercel.com/v10/projects/{project_id}/env"
        if team_id:
            url += f"?teamId={team_id}"

        body = json.dumps(entry).encode("utf-8")
        req = urllib.request.Request(url=url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {vercel_token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="injected",
                    mode="production",
                    env_key=key,
                    http_status=resp.status,
                )
                results.append({"key": key, "status": "injected"})
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            # 409 = already exists — that's OK, try to update instead
            if exc.code == 409:
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="already_exists",
                    mode="production",
                    env_key=key,
                )
                results.append({"key": key, "status": "already_exists"})
            else:
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="failed",
                    mode="production",
                    env_key=key,
                    http_status=exc.code,
                    error=redact_secrets(error_body[:200]),
                )
                results.append({"key": key, "status": "failed", "error": f"HTTP {exc.code}"})

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject env vars into a Vercel project")
    parser.add_argument("--project-id", required=True, help="Vercel project name or ID")
    parser.add_argument("--env", action="append", default=[], help="KEY=VALUE pair (repeatable)")
    parser.add_argument("--env-file", default="", help="Path to .env file with KEY=VALUE lines")
    parser.add_argument("--dry-run", action="store_true", help="Parse and log but don't call Vercel API")
    args = parser.parse_args()

    # Collect env pairs from --env flags and --env-file
    env_pairs: list[str] = list(args.env)
    if args.env_file:
        try:
            with open(args.env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        env_pairs.append(line)
        except OSError as exc:
            print(f"[{STEP_NAME}] WARNING: could not read env file: {exc}", file=sys.stderr)

    if not env_pairs:
        print(f"[{STEP_NAME}] No env vars to inject.", file=sys.stderr)
        return

    vercel_token = os.environ.get("VERCEL_TOKEN", "").strip()
    team_id = os.environ.get("VERCEL_TEAM_ID", "").strip()

    if not args.dry_run and not vercel_token:
        print(f"[{STEP_NAME}] ERROR: VERCEL_TOKEN is required.", file=sys.stderr)
        raise SystemExit(1)

    results = inject_env_vars(
        project_id=args.project_id.strip(),
        env_pairs=env_pairs,
        vercel_token=vercel_token,
        team_id=team_id,
        dry_run=args.dry_run,
    )

    print(json.dumps({"results": results}, ensure_ascii=True))


if __name__ == "__main__":
    main()
