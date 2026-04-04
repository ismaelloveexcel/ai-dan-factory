#!/usr/bin/env python3
"""
Validate and normalize BuildBrief payloads before injection.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result, normalize_text, stable_idempotency_key

STEP_NAME = "validate_brief"
REPO_SLUG_REGEX = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

REQUIRED_FIELDS = (
    "project_id",
    "product_name",
    "problem",
    "solution",
    "cta",
    "source_type",
    "reference_context",
    "demand_level",
    "monetization_proof",
    "market_saturation",
    "differentiation",
)

FIELD_ALIASES = {
    "project_id": {"project_id", "projectid", "project", "projectslug", "slug"},
    "product_name": {"product_name", "productname", "name", "title"},
    "problem": {"problem"},
    "solution": {"solution"},
    "cta": {"cta", "cta_text", "ctatext", "call_to_action", "calltoaction"},
    "source_type": {"source_type", "sourcetype"},
    "reference_context": {"reference_context", "referencecontext"},
    "demand_level": {"demand_level", "demandlevel"},
    "monetization_proof": {"monetization_proof", "monetizationproof"},
    "market_saturation": {"market_saturation", "marketsaturation"},
    "differentiation": {"differentiation"},
}

FIELD_LIMITS = {
    "product_name": (3, 120),
    "problem": (10, 1500),
    "solution": (10, 1500),
    "cta": (2, 80),
    "reference_context": (5, 2000),
}


class ValidationError(Exception):
    pass


def _canonical_key(raw_key: str) -> str:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw_key).lower()
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    return normalized


def _alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for target_key, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            mapping[_canonical_key(alias)] = target_key
    return mapping


def _normalize_payload(raw: dict[str, Any]) -> dict[str, str]:
    alias_mapping = _alias_map()
    normalized: dict[str, str] = {}

    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        target = alias_mapping.get(_canonical_key(key))
        if not target:
            continue
        if not isinstance(value, str):
            raise ValidationError(f"Field '{target}' must be a string.")
        normalized[target] = normalize_text(value)

    missing = [field for field in REQUIRED_FIELDS if not normalized.get(field)]
    if missing:
        raise ValidationError(f"Missing required fields: {', '.join(missing)}")

    project_id = normalized["project_id"].lower()
    if len(project_id) < 3 or len(project_id) > 63:
        raise ValidationError("Field 'project_id' must be between 3 and 63 characters.")
    if not REPO_SLUG_REGEX.fullmatch(project_id):
        raise ValidationError(
            "Field 'project_id' must be a safe slug using lowercase letters, numbers, and hyphens."
        )
    normalized["project_id"] = project_id

    # Preserve optional scoring fields when present in the input.
    OPTIONAL_PASSTHROUGH = ("build_complexity", "speed_to_revenue")
    for opt_field in OPTIONAL_PASSTHROUGH:
        if opt_field in normalized:
            continue
        raw_value = raw.get(opt_field, "")
        if isinstance(raw_value, str) and raw_value.strip():
            normalized[opt_field] = normalize_text(raw_value)

    for field_name, (min_len, max_len) in FIELD_LIMITS.items():
        value = normalized[field_name]
        if len(value) < min_len or len(value) > max_len:
            raise ValidationError(f"Field '{field_name}' must be between {min_len} and {max_len} characters.")

    source_type = normalized["source_type"].upper()
    if source_type not in {"TREND", "COMPETITOR", "GAP", "EXISTING_PRODUCT"}:
        raise ValidationError(
            "Field 'source_type' must be one of: TREND, COMPETITOR, GAP, EXISTING_PRODUCT."
        )
    normalized["source_type"] = source_type

    demand_level = normalized["demand_level"].upper()
    if demand_level not in {"HIGH", "MEDIUM", "LOW"}:
        raise ValidationError("Field 'demand_level' must be one of: HIGH, MEDIUM, LOW.")
    normalized["demand_level"] = demand_level

    monetization_proof = normalized["monetization_proof"].upper()
    if monetization_proof not in {"YES", "NO"}:
        raise ValidationError("Field 'monetization_proof' must be one of: YES, NO.")
    normalized["monetization_proof"] = monetization_proof

    market_saturation = normalized["market_saturation"].upper()
    if market_saturation not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValidationError("Field 'market_saturation' must be one of: LOW, MEDIUM, HIGH.")
    normalized["market_saturation"] = market_saturation

    differentiation = normalized["differentiation"].upper()
    if differentiation not in {"STRONG", "WEAK"}:
        raise ValidationError("Field 'differentiation' must be one of: STRONG, WEAK.")
    normalized["differentiation"] = differentiation

    return normalized


def _load_brief(args: argparse.Namespace) -> dict[str, Any]:
    if args.brief_file:
        brief_path = Path(args.brief_file).expanduser().resolve()
        if not brief_path.is_file():
            raise ValidationError(f"--brief-file does not exist: {brief_path}")
        raw = brief_path.read_text(encoding="utf-8")
    else:
        raw = args.brief_json

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"BuildBrief JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("BuildBrief JSON must be an object.")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and normalize BuildBrief JSON")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--brief-json", help="BuildBrief JSON string")
    group.add_argument("--brief-file", help="Path to BuildBrief JSON file")
    parser.add_argument("--expected-project-id", default="", help="Optional expected project_id to enforce")
    parser.add_argument("--normalized-output", required=True, help="Path to write normalized brief JSON")
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    parser.add_argument("--dry-run", action="store_true", help="Validate only (still writes normalized output)")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id_for_log = args.expected_project_id.strip() or "unknown"
    result_file = args.result_file

    log_event(project_id=project_id_for_log, step=STEP_NAME, status="started", mode=mode)
    try:
        raw_brief = _load_brief(args)
        normalized_brief = _normalize_payload(raw_brief)

        expected_project_id = args.expected_project_id.strip().lower()
        if expected_project_id and normalized_brief["project_id"] != expected_project_id:
            raise ValidationError(
                f"Input project_id mismatch: workflow project_id='{expected_project_id}', "
                f"brief project_id='{normalized_brief['project_id']}'"
            )

        project_id = normalized_brief["project_id"]
        idempotency_key = stable_idempotency_key(project_id, normalized_brief)
        normalized_brief["idempotency_key"] = idempotency_key

        normalized_output_path = Path(args.normalized_output).expanduser().resolve()
        normalized_output_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_output_path.write_text(
            json.dumps(normalized_brief, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

        result_payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "idempotency_key": idempotency_key,
            "normalized_brief_path": str(normalized_output_path),
        }
        maybe_write_result(result_file, result_payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode=mode,
            idempotency_key=idempotency_key,
            normalized_brief_path=str(normalized_output_path),
        )
    except ValidationError as exc:
        error_message = str(exc)
        result_payload = {
            "project_id": project_id_for_log,
            "step": STEP_NAME,
            "status": "failed",
            "mode": mode,
            "error": error_message,
        }
        maybe_write_result(result_file, result_payload)
        log_event(
            project_id=project_id_for_log,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            error=error_message,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
