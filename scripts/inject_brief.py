#!/usr/bin/env python3
"""
Generate PRODUCT_BRIEF.md and product.config.json from a validated BuildBrief payload.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factory_utils import atomic_write_text, log_event, maybe_write_result, normalize_text

STEP_NAME = "inject_brief"
REQUIRED_FIELDS = ("project_id", "product_name", "problem", "solution", "cta")


class BriefInjectionError(Exception):
    pass


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
    return json.dumps(payload, indent=2, ensure_ascii=True) + "\n"


def _load_brief(args: argparse.Namespace) -> dict[str, Any]:
    if args.brief_file:
        brief_path = Path(args.brief_file).expanduser().resolve()
        if not brief_path.is_file():
            raise BriefInjectionError(f"--brief-file does not exist: {brief_path}")
        raw = brief_path.read_text(encoding="utf-8")
    else:
        raw = args.brief_json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BriefInjectionError(f"BuildBrief JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise BriefInjectionError("BuildBrief JSON must be an object.")
    return data


def _normalize_required_brief(data: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for field_name in REQUIRED_FIELDS:
        raw_value = data.get(field_name)
        if not isinstance(raw_value, str):
            raise BriefInjectionError(f"Field '{field_name}' must be a non-empty string.")
        value = normalize_text(raw_value)
        if not value:
            raise BriefInjectionError(f"Field '{field_name}' must be a non-empty string.")
        normalized[field_name] = value
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject BuildBrief data into template files")
    parser.add_argument("--project-id", default="", help="Expected project id for consistency checks")
    parser.add_argument("--project-dir", required=True, help="Path to the project root")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--brief-json", help="BuildBrief JSON string")
    group.add_argument("--brief-file", help="Path to BuildBrief JSON file")
    parser.add_argument("--idempotency-key", default="", help="Idempotency key for deduplication/audit")
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing files")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    result_file = args.result_file
    idempotency_key = args.idempotency_key.strip()
    project_id_for_log = args.project_id.strip().lower() or "unknown"

    log_event(
        project_id=project_id_for_log,
        step=STEP_NAME,
        status="started",
        mode=mode,
        idempotency_key=idempotency_key,
    )
    try:
        project_dir = Path(args.project_dir).expanduser().resolve()
        if not project_dir.is_dir():
            raise BriefInjectionError(f"--project-dir does not exist: {project_dir}")

        loaded = _load_brief(args)
        brief = _normalize_required_brief(loaded)
        if args.project_id.strip() and brief["project_id"] != args.project_id.strip().lower():
            raise BriefInjectionError(
                f"Input project_id mismatch: expected '{args.project_id.strip().lower()}', "
                f"brief contains '{brief['project_id']}'"
            )
        project_id_for_log = brief["project_id"]
        idempotency_key = idempotency_key or str(loaded.get("idempotency_key", "")).strip()

        brief_path = project_dir / "PRODUCT_BRIEF.md"
        config_path = project_dir / "product.config.json"
        product_brief = _render_product_brief(brief)
        product_config = _render_product_config(brief)

        if not args.dry_run:
            atomic_write_text(brief_path, product_brief)
            atomic_write_text(config_path, product_config)

        result_payload = {
            "project_id": brief["project_id"],
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "idempotency_key": idempotency_key,
            "simulated": args.dry_run,
            "files_written": [str(brief_path), str(config_path)],
        }
        maybe_write_result(result_file, result_payload)
        log_event(
            project_id=brief["project_id"],
            step=STEP_NAME,
            status="success",
            mode=mode,
            idempotency_key=idempotency_key,
            simulated=args.dry_run,
            files_written=[str(brief_path), str(config_path)],
        )
    except BriefInjectionError as exc:
        error_message = str(exc)
        maybe_write_result(
            result_file,
            {
                "project_id": project_id_for_log,
                "step": STEP_NAME,
                "status": "failed",
                "mode": mode,
                "idempotency_key": idempotency_key,
                "error": error_message,
            },
        )
        log_event(
            project_id=project_id_for_log,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            idempotency_key=idempotency_key,
            error=error_message,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
