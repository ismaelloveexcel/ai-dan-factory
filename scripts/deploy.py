#!/usr/bin/env python3
"""
deploy.py – Deploy a project directory to Vercel.

Usage:
    python scripts/deploy.py --project-dir ./my-project --project-id my-saas [--dry-run]

Environment variables required (unless --dry-run):
    VERCEL_TOKEN – Vercel personal access token
    VERCEL_ORG_ID – (optional) Vercel team/org ID
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def deploy(project_dir: Path, project_id: str, token: str, org_id: str = "", prod: bool = True) -> str:
    """Run `vercel deploy` and return the deployment URL."""
    env = os.environ.copy()
    env["VERCEL_TOKEN"] = token
    if org_id:
        env["VERCEL_ORG_ID"] = org_id

    # Pass the token only via environment to avoid leaking it in process listings.
    cmd = ["vercel", "--yes"]
    if prod:
        cmd.append("--prod")
    if project_id:
        cmd += ["--name", project_id]

    result = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(result.stderr.rstrip(), file=sys.stderr)
        sys.exit(f"[error] Vercel deploy failed (exit {result.returncode})")

    # Extract the deployment URL (first https:// line from the end of stdout).
    url = ""
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line.startswith("http://") or line.startswith("https://"):
            url = line
            break
    if not url:
        print(result.stdout.rstrip(), file=sys.stderr)
        sys.exit("[error] Could not parse a deployment URL from Vercel output.")
    print(f"[ok] Deployed: {url}")
    return url


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy a project to Vercel")
    parser.add_argument("--project-dir", required=True, help="Path to the project to deploy")
    parser.add_argument("--project-id", required=True, help="Vercel project name / slug")
    parser.add_argument("--no-prod", action="store_true", help="Deploy to preview instead of production")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without deploying")
    args = parser.parse_args()

    token = os.environ.get("VERCEL_TOKEN", "")
    org_id = os.environ.get("VERCEL_ORG_ID", "")

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        sys.exit(f"[error] project-dir does not exist: {project_dir}")

    if args.dry_run:
        env_note = "VERCEL_TOKEN set" if token else "VERCEL_TOKEN NOT set"
        print(f"[dry-run] Would deploy {project_dir} as '{args.project_id}' ({env_note})")
        return

    if not token:
        sys.exit("[error] VERCEL_TOKEN environment variable is not set.")

    deploy(
        project_dir=project_dir,
        project_id=args.project_id,
        token=token,
        org_id=org_id,
        prod=not args.no_prod,
    )


if __name__ == "__main__":
    main()
