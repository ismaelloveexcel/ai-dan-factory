#!/usr/bin/env python3
"""
Build economics evaluation — ROI gate before build execution.

Estimates:
  - build_cost (compute + time)
  - expected_return (based on demand/monetization signals)
  - roi (return / cost)

Rules:
  NEGATIVE ROI → REJECT
  LOW ROI (< threshold) → HOLD
  HIGH ROI → PRIORITIZE
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result

STEP_NAME = "build_economics"

# Cost estimates (relative units)
COMPLEXITY_COST = {"LOW": 1.0, "MEDIUM": 2.0, "HIGH": 4.0}
# Revenue potential multipliers
DEMAND_REVENUE = {"LOW": 0.5, "MEDIUM": 2.0, "HIGH": 5.0}
MONETIZATION_MULTIPLIER = {"YES": 2.0, "NO": 0.3}
SPEED_MULTIPLIER = {"FAST": 2.0, "MEDIUM": 1.0, "SLOW": 0.5}
DIFFERENTIATION_MULTIPLIER = {"STRONG": 1.5, "WEAK": 0.7}


class BuildEconomicsError(Exception):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BuildEconomicsError(f"File not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BuildEconomicsError(f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BuildEconomicsError("JSON must be an object.")
    return payload


def evaluate_economics(brief: dict[str, Any]) -> dict[str, Any]:
    """Calculate build economics from brief signals."""
    complexity = str(brief.get("build_complexity", "MEDIUM")).strip().upper()
    if complexity not in COMPLEXITY_COST:
        complexity = "MEDIUM"

    demand = str(brief.get("demand_level", "MEDIUM")).strip().upper()
    if demand not in DEMAND_REVENUE:
        demand = "MEDIUM"

    monetization = str(brief.get("monetization_proof", "NO")).strip().upper()
    if monetization not in MONETIZATION_MULTIPLIER:
        monetization = "NO"

    speed = str(brief.get("speed_to_revenue", "MEDIUM")).strip().upper()
    if speed not in SPEED_MULTIPLIER:
        speed = "MEDIUM"

    differentiation = str(brief.get("differentiation", "WEAK")).strip().upper()
    if differentiation not in DIFFERENTIATION_MULTIPLIER:
        differentiation = "WEAK"

    build_cost = COMPLEXITY_COST[complexity]
    expected_return = (
        DEMAND_REVENUE[demand]
        * MONETIZATION_MULTIPLIER[monetization]
        * SPEED_MULTIPLIER[speed]
        * DIFFERENTIATION_MULTIPLIER[differentiation]
    )

    roi = round(expected_return / build_cost, 2) if build_cost > 0 else 0.0

    min_roi = float(os.environ.get("MIN_ROI_THRESHOLD", "1.5"))

    if roi <= 0:
        decision = "REJECT"
        reason = "Negative or zero ROI — build rejected."
    elif roi < min_roi:
        decision = "HOLD"
        reason = f"ROI {roi} below threshold {min_roi} — build on hold."
    else:
        decision = "PRIORITIZE"
        reason = f"ROI {roi} meets threshold — build prioritized."

    return {
        "build_cost": build_cost,
        "expected_return": round(expected_return, 2),
        "roi": roi,
        "economics_decision": decision,
        "economics_reason": reason,
        "economics_breakdown": {
            "complexity": complexity,
            "demand": demand,
            "monetization": monetization,
            "speed": speed,
            "differentiation": differentiation,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build economics evaluation")
    parser.add_argument("--brief-file", required=True, help="Path to normalized brief JSON")
    parser.add_argument("--result-file", default="", help="Path to write economics result JSON")
    parser.add_argument("--project-id", default="", help="Project identifier for logging")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate without blocking")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id = args.project_id.strip() or "unknown"

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode=mode)

    try:
        brief = _load_json(Path(args.brief_file).expanduser().resolve())
        project_id = str(brief.get("project_id", project_id)).strip().lower()

        result = evaluate_economics(brief)

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
            roi=result["roi"],
            economics_decision=result["economics_decision"],
        )
        print(json.dumps(payload, ensure_ascii=True))

        if not args.dry_run and result["economics_decision"] == "REJECT":
            raise SystemExit(1)

    except BuildEconomicsError as exc:
        error_message = str(exc)
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "mode": mode,
            "economics_decision": "REJECT",
            "economics_reason": error_message,
            "roi": 0.0,
        }
        maybe_write_result(args.result_file, payload)
        log_event(project_id=project_id, step=STEP_NAME, status="failed", mode=mode, error=error_message)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
