#!/usr/bin/env python3
"""
inject_brief.py – Inject a BuildBrief (JSON) into the saas-template placeholder files.

Usage:
    python scripts/inject_brief.py \
        --project-dir ./my-project \
        --brief-file /tmp/brief.json

    # Or pass JSON inline (only safe for values without single quotes):
    python scripts/inject_brief.py \
        --project-dir ./my-project \
        --brief '{"product_name": "Acme", "product_tagline": "Ship faster"}'

The script replaces {{KEY}} tokens in:
    - PRODUCT_BRIEF.md
    - product.config.json
    - app/page.tsx
    - app/layout.tsx
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Files inside the project directory that contain placeholders
INJECTABLE_FILES = [
    "PRODUCT_BRIEF.md",
    "product.config.json",
    "app/page.tsx",
    "app/layout.tsx",
]

# Map brief keys → template tokens
TOKEN_MAP = {
    "product_name": "PRODUCT_NAME",
    "product_tagline": "PRODUCT_TAGLINE",
    "product_url": "PRODUCT_URL",
    "vercel_project_id": "VERCEL_PROJECT_ID",
    "problem": "PROBLEM",
    "solution": "SOLUTION",
    "target_audience": "TARGET_AUDIENCE",
    "key_features": "KEY_FEATURES",
    "pricing": "PRICING",
}


def inject(project_dir: Path, brief: dict, dry_run: bool = False) -> None:
    for relative_path in INJECTABLE_FILES:
        file_path = project_dir / relative_path
        if not file_path.exists():
            print(f"[skip] {file_path} not found", file=sys.stderr)
            continue

        content = file_path.read_text(encoding="utf-8")
        original = content

        for brief_key, token in TOKEN_MAP.items():
            value = brief.get(brief_key)
            if value is None:
                continue
            # Stringify lists/dicts for simple injection.
            # NOTE: In TypeScript/JSX files this only works safely when the
            # placeholder appears inside a string literal.  If you need to
            # inject a JavaScript value (array/object literal) directly, do
            # the substitution in a separate, format-aware step.
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            content = content.replace("{{" + token + "}}", str(value))

        # Warn about any remaining unfilled tokens
        remaining = re.findall(r"\{\{[A-Z_]+\}\}", content)
        if remaining:
            tokens = ", ".join(set(remaining))
            print(f"[warn] {relative_path}: unfilled tokens: {tokens}", file=sys.stderr)

        if content == original:
            print(f"[skip] {relative_path}: no changes")
            continue

        if dry_run:
            print(f"[dry-run] Would update {relative_path}")
        else:
            file_path.write_text(content, encoding="utf-8")
            print(f"[ok] Updated {relative_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject a BuildBrief into saas-template files")
    parser.add_argument("--project-dir", required=True, help="Path to the project directory (clone of saas-template)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--brief", help="BuildBrief as a JSON string")
    group.add_argument("--brief-file", help="Path to a file containing the BuildBrief JSON (preferred; avoids shell-quoting issues)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing files")
    args = parser.parse_args()

    if args.brief_file:
        brief_path = Path(args.brief_file).expanduser().resolve()
        if not brief_path.is_file():
            sys.exit(f"[error] --brief-file does not exist: {brief_path}")
        raw = brief_path.read_text(encoding="utf-8")
    else:
        raw = args.brief  # type: ignore[assignment]

    try:
        brief = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.exit(f"[error] Brief is not valid JSON: {exc}")

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        sys.exit(f"[error] project-dir does not exist: {project_dir}")

    inject(project_dir=project_dir, brief=brief, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
