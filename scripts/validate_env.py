#!/usr/bin/env python3
"""
Validate required environment variables and configuration before factory execution.

Exit codes:
  0 = all required config present for the given mode
  1 = missing required config (prints diagnostics)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _check_env(name: str) -> tuple[bool, str]:
    """Check if an env var is set and non-empty."""
    val = os.environ.get(name, "").strip()
    if val:
        return True, f"  \u2713 {name} = {'*' * min(len(val), 8)}..."
    return False, f"  \u2717 {name} = (not set)"


def validate(mode: str = "production") -> list[str]:
    """Validate environment and return list of errors."""
    errors: list[str] = []
    warnings: list[str] = []

    print(f"[env_check] Validating environment for mode: {mode}", flush=True)

    # --- Always required for production builds ---
    if mode == "production":
        for var in ("FACTORY_GITHUB_TOKEN", "VERCEL_DEPLOY_HOOK_URL"):
            ok, msg = _check_env(var)
            print(msg, flush=True)
            if not ok:
                errors.append(f"Missing required secret: {var}")

    # --- Callback/auth secrets: required when STRICT_PROD=true ---
    strict_prod = os.environ.get("STRICT_PROD", "").strip().lower() == "true"
    for var in ("FACTORY_CALLBACK_SECRET", "FACTORY_SECRET"):
        ok, msg = _check_env(var)
        print(msg, flush=True)
        if not ok:
            if strict_prod:
                errors.append(f"Missing required secret (STRICT_PROD=true): {var}")
            else:
                warnings.append(f"Optional: {var} not set (callback authentication disabled)")

    # GH_TOKEN or GITHUB_TOKEN must be present (for GitHub API calls)
    gh_ok = (
        bool(os.environ.get("GH_TOKEN", "").strip())
        or bool(os.environ.get("GITHUB_TOKEN", "").strip())
        or bool(os.environ.get("FACTORY_GITHUB_TOKEN", "").strip())
    )
    if gh_ok:
        print("  \u2713 GH_TOKEN / GITHUB_TOKEN = set", flush=True)
    else:
        if strict_prod:
            errors.append("Missing required secret (STRICT_PROD=true): GH_TOKEN or GITHUB_TOKEN")
            print("  \u2717 GH_TOKEN / GITHUB_TOKEN = (not set)", flush=True)
        else:
            warnings.append("Optional: GH_TOKEN / GITHUB_TOKEN not set (GitHub API calls may fail)")
            print("  \u26a0 GH_TOKEN / GITHUB_TOKEN = (not set)", flush=True)

    # --- Recommended ---
    for var in ("OPENAI_API_KEY",):
        ok, msg = _check_env(var)
        print(msg, flush=True)
        if not ok:
            warnings.append(f"Optional: {var} not set (AI enhancement will use fallback templates)")

    # --- Integration ---
    for var in ("FACTORY_BASE_URL",):
        ok, msg = _check_env(var)
        print(msg, flush=True)
        if not ok:
            warnings.append(f"Optional: {var} not set (Managing Director webhook notifications disabled)")

    # --- Callback secret ---
    for var in ("FACTORY_SECRET",):
        ok, msg = _check_env(var)
        print(msg, flush=True)
        if not ok:
            warnings.append(f"Optional: {var} not set (callback authentication disabled)")

    # --- Template directory ---
    template_dir = os.environ.get("TEMPLATE_PROJECT_DIR", "templates/saas-template")
    if Path(template_dir).is_dir():
        print(f"  \u2713 TEMPLATE_PROJECT_DIR = {template_dir} (exists)", flush=True)
    else:
        print(f"  \u26a0 TEMPLATE_PROJECT_DIR = {template_dir} (not found locally, OK for GitHub Actions)", flush=True)

    # --- Print warnings ---
    for w in warnings:
        print(f"  \u26a0 {w}", flush=True)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate factory environment configuration")
    parser.add_argument("--mode", default="production", choices=["production", "dry_run", "tests_only"], help="Execution mode")
    args = parser.parse_args()

    errors = validate(args.mode)
    if errors:
        print(f"\n[env_check] FAILED \u2014 {len(errors)} error(s):", file=sys.stderr, flush=True)
        for e in errors:
            print(f"  \u2717 {e}", file=sys.stderr, flush=True)
        return 1

    print("\n[env_check] PASSED \u2014 environment is valid.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
