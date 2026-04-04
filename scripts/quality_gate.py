#!/usr/bin/env python3
"""
Product quality gate — evaluates deployed product quality before distribution.

Scores:
  - clarity (product messaging)
  - usability (CTA presence and structure)
  - ux_simplicity (landing page completeness)
  - perceived_value (monetization signals)
  - first_impression (overall readiness)

Output: QUALITY_SCORE (0–10)
  <6 → BLOCK distribution
  6–7 → improve (warn)
  ≥8 → proceed
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result

STEP_NAME = "quality_gate"


class QualityGateError(Exception):
    pass


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise QualityGateError(f"Missing required field '{key}'.")
    return value.strip()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise QualityGateError(f"File not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QualityGateError(f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise QualityGateError("JSON must be an object.")
    return payload


def _score_clarity(brief: dict[str, Any]) -> int:
    """Score product messaging clarity (0-2)."""
    score = 0
    product_name = str(brief.get("product_name", "")).strip()
    problem = str(brief.get("problem", "")).strip()
    solution = str(brief.get("solution", "")).strip()
    if product_name and len(product_name) >= 3:
        score += 1
    if problem and solution and len(problem) >= 10 and len(solution) >= 10:
        score += 1
    return score


def _score_usability(brief: dict[str, Any]) -> int:
    """Score CTA and usability signals (0-2)."""
    score = 0
    cta = str(brief.get("cta", "")).strip()
    if cta and len(cta) >= 2:
        score += 1
    if cta and len(cta) <= 40:
        score += 1
    return score


def _score_ux_simplicity(brief: dict[str, Any], business_output: dict[str, Any] | None) -> int:
    """Score landing page completeness and UX structure (0-2)."""
    score = 0
    has_brief_fields = all(
        str(brief.get(f, "")).strip()
        for f in ("product_name", "problem", "solution", "cta")
    )
    if has_brief_fields:
        score += 1
    if business_output and business_output.get("headline") and business_output.get("CTA"):
        score += 1
    return score


def _score_perceived_value(brief: dict[str, Any], business_output: dict[str, Any] | None) -> int:
    """Score monetization signals and perceived value (0-2)."""
    score = 0
    if str(brief.get("monetization_proof", "")).upper() == "YES":
        score += 1
    if business_output and business_output.get("pricing_suggestion") and business_output.get("monetization_model"):
        score += 1
    return score


def _score_first_impression(
    brief: dict[str, Any],
    business_output: dict[str, Any] | None,
    health_status: str,
) -> int:
    """Score overall readiness and first impression (0-2)."""
    score = 0
    if health_status in ("healthy", "simulated"):
        score += 1
    if business_output and business_output.get("gtm_plan"):
        score += 1
    return score


def evaluate_quality(
    brief: dict[str, Any],
    business_output: dict[str, Any] | None = None,
    health_status: str = "unknown",
) -> dict[str, Any]:
    """Run quality evaluation and return scored result."""
    breakdown = {
        "clarity": _score_clarity(brief),
        "usability": _score_usability(brief),
        "ux_simplicity": _score_ux_simplicity(brief, business_output),
        "perceived_value": _score_perceived_value(brief, business_output),
        "first_impression": _score_first_impression(brief, business_output, health_status),
    }
    total = sum(breakdown.values())

    if total < 6:
        decision = "BLOCK"
        reason = "Quality score below 6 — distribution blocked."
    elif total < 8:
        decision = "IMPROVE"
        reason = "Quality score 6-7 — improvements recommended before distribution."
    else:
        decision = "PROCEED"
        reason = "Quality score 8-10 — ready for distribution."

    return {
        "quality_score": total,
        "quality_decision": decision,
        "quality_reason": reason,
        "quality_breakdown": breakdown,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Product quality gate evaluation")
    parser.add_argument("--brief-file", required=True, help="Path to normalized brief JSON")
    parser.add_argument("--business-output-file", default="", help="Path to business_output.json")
    parser.add_argument("--health-status", default="unknown", help="Health check status")
    parser.add_argument("--result-file", default="", help="Path to write quality gate result JSON")
    parser.add_argument("--project-id", default="", help="Project identifier for logging")
    parser.add_argument("--dry-run", action="store_true", help="Run evaluation without blocking")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id = args.project_id.strip() or "unknown"

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode=mode)

    try:
        brief = _load_json(Path(args.brief_file).expanduser().resolve())
        project_id = str(brief.get("project_id", project_id)).strip().lower()

        business_output: dict[str, Any] | None = None
        if args.business_output_file:
            bo_path = Path(args.business_output_file).expanduser().resolve()
            if bo_path.is_file():
                business_output = _load_json(bo_path)

        result = evaluate_quality(
            brief=brief,
            business_output=business_output,
            health_status=args.health_status,
        )

        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            **result,
        }

        maybe_write_result(args.result_file, payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode=mode,
            quality_score=result["quality_score"],
            quality_decision=result["quality_decision"],
        )
        print(json.dumps(payload, ensure_ascii=True))

        if not args.dry_run and result["quality_decision"] == "BLOCK":
            raise SystemExit(1)

    except QualityGateError as exc:
        error_message = str(exc)
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "mode": mode,
            "quality_score": 0,
            "quality_decision": "BLOCK",
            "quality_reason": error_message,
            "quality_breakdown": {},
        }
        maybe_write_result(args.result_file, payload)
        log_event(project_id=project_id, step=STEP_NAME, status="failed", mode=mode, error=error_message)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
