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
        return True, f"  ✓ {name} = {'*' * min(len(val), 8)}..."
    return False, f"  ✗ {name} = (not set)"


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
        print(f"  ✓ TEMPLATE_PROJECT_DIR = {template_dir} (exists)", flush=True)
    else:
        print(f"  ⚠ TEMPLATE_PROJECT_DIR = {template_dir} (not found locally, OK for GitHub Actions)", flush=True)

    # --- Print warnings ---
    for w in warnings:
        print(f"  ⚠ {w}", flush=True)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate factory environment configuration")
    parser.add_argument("--mode", default="production", choices=["production", "dry_run", "tests_only"], help="Execution mode")
    args = parser.parse_args()

    errors = validate(args.mode)
    if errors:
        print(f"\n[env_check] FAILED — {len(errors)} error(s):", file=sys.stderr, flush=True)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr, flush=True)
        return 1

    print("\n[env_check] PASSED — environment is valid.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
