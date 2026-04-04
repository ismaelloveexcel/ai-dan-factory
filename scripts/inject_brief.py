#!/usr/bin/env python3
"""
Generate PRODUCT_BRIEF.md and product.config.json from a BuildBrief JSON payload.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _first_non_empty(data: dict[str, object], *keys: str, default: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _normalize_brief(raw: dict[str, object]) -> dict[str, str]:
    return {
        "project_id": _first_non_empty(raw, "project_id", "projectId", "slug", default="replace-with-project-id"),
        "product_name": _first_non_empty(
            raw,
            "product_name",
            "productName",
            "name",
            "title",
            default="Replace with product name",
        ),
        "problem": _first_non_empty(raw, "problem", default="Replace with the core problem"),
        "solution": _first_non_empty(raw, "solution", default="Replace with your solution"),
        "cta": _first_non_empty(raw, "cta", "cta_text", "call_to_action", default="Get Started"),
    }


def _render_product_brief(brief: dict[str, str]) -> str:
    return (
        "# Product Brief\n\n"
        "## Product Name\n"
        f"{brief['product_name']}\n\n"
        "## Problem\n"
        f"{brief['problem']}\n\n"
        "## Solution\n"
        f"{brief['solution']}\n\n"
        "## CTA\n"
        f"{brief['cta']}\n"
    )


def _render_product_config(brief: dict[str, str]) -> str:
    payload = {
        "project_id": brief["project_id"],
        "product_name": brief["product_name"],
        "problem": brief["problem"],
        "solution": brief["solution"],
        "cta": brief["cta"],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _load_brief(args: argparse.Namespace) -> dict[str, object]:
    if args.brief_file:
        brief_path = Path(args.brief_file).expanduser().resolve()
        if not brief_path.is_file():
            raise SystemExit(f"[error] --brief-file does not exist: {brief_path}")
        raw = brief_path.read_text(encoding="utf-8")
    else:
        raw = args.brief_json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[error] BuildBrief JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("[error] BuildBrief JSON must be an object.")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate product brief files from BuildBrief JSON")
    parser.add_argument("--project-dir", required=True, help="Path to the project root")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--brief-json", help="BuildBrief JSON string")
    group.add_argument("--brief-file", help="Path to BuildBrief JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing files")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        raise SystemExit(f"[error] --project-dir does not exist: {project_dir}")

    brief = _normalize_brief(_load_brief(args))
    product_brief = _render_product_brief(brief)
    product_config = _render_product_config(brief)

    brief_path = project_dir / "PRODUCT_BRIEF.md"
    config_path = project_dir / "product.config.json"

    if args.dry_run:
        print(f"[dry-run] Would write {brief_path}")
        print(f"[dry-run] Would write {config_path}")
        return

    brief_path.write_text(product_brief, encoding="utf-8")
    config_path.write_text(product_config, encoding="utf-8")
    print(f"[ok] Wrote {brief_path}")
    print(f"[ok] Wrote {config_path}")


if __name__ == "__main__":
    main()
