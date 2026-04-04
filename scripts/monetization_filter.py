#!/usr/bin/env python3
"""
Monetization Priority Filter for AI-DAN Factory.

Enforces fast-revenue prioritization:
  - Prioritize: fast revenue (< 14 days), clear willingness to pay, simple delivery
  - Reject: unclear monetization, long revenue cycle, complex builds before validation

This filter runs BEFORE the scoring engine as an additional pre-gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result

STEP_NAME = "monetization_filter"


class MonetizationFilterError(Exception):
    pass


def evaluate_monetization_priority(brief: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate a brief's monetization priority.

    Returns:
      - priority: HIGH | MEDIUM | LOW
      - pass_filter: bool
      - reason: str
      - flags: list[str]
    """
    monetization_proof = str(brief.get("monetization_proof", "")).strip().upper()
    speed_to_revenue = str(brief.get("speed_to_revenue", "MEDIUM")).strip().upper()
    build_complexity = str(brief.get("build_complexity", "MEDIUM")).strip().upper()
    demand_level = str(brief.get("demand_level", "")).strip().upper()

    flags: list[str] = []
    score = 0

    # Fast revenue (< 14 days) → +3
    if speed_to_revenue == "FAST":
        score += 3
        flags.append("FAST_REVENUE")
    elif speed_to_revenue == "MEDIUM":
        score += 1
    else:
        flags.append("SLOW_REVENUE_CYCLE")

    # Clear willingness to pay → +3
    if monetization_proof == "YES":
        score += 3
        flags.append("MONETIZATION_PROVEN")
    else:
        flags.append("NO_MONETIZATION_PROOF")

    # Simple delivery → +2
    if build_complexity == "LOW":
        score += 2
        flags.append("SIMPLE_DELIVERY")
    elif build_complexity == "MEDIUM":
        score += 1
    else:
        flags.append("COMPLEX_BUILD")

    # High demand bonus → +1
    if demand_level == "HIGH":
        score += 1

    # Decision logic
    if monetization_proof != "YES":
        return {
            "priority": "LOW",
            "pass_filter": False,
            "reason": "Unclear monetization. Cannot proceed without monetization proof.",
            "flags": flags,
            "monetization_score": score,
        }

    if speed_to_revenue == "SLOW" and build_complexity == "HIGH":
        return {
            "priority": "LOW",
            "pass_filter": False,
            "reason": "Long revenue cycle with complex build. Validate before investing.",
            "flags": flags,
            "monetization_score": score,
        }

    if score >= 6:
        priority = "HIGH"
    elif score >= 4:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    return {
        "priority": priority,
        "pass_filter": priority != "LOW",
        "reason": f"Monetization priority: {priority} (score {score}/9).",
        "flags": flags,
        "monetization_score": score,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Monetization priority filter")
    parser.add_argument("--brief-file", required=True, help="Path to brief JSON")
    parser.add_argument("--result-file", default="", help="Path to write filter result JSON")
    args = parser.parse_args()

    project_id = "unknown"
    log_event(project_id=project_id, step=STEP_NAME, status="started", mode="production")

    try:
        brief_path = Path(args.brief_file).expanduser().resolve()
        if not brief_path.is_file():
            raise MonetizationFilterError(f"Brief file not found: {brief_path}")

        brief = json.loads(brief_path.read_text(encoding="utf-8"))
        if not isinstance(brief, dict):
            raise MonetizationFilterError("Brief must be a JSON object.")

        project_id = str(brief.get("project_id", "unknown")).strip().lower()
        result = evaluate_monetization_priority(brief)

        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            **result,
        }
        maybe_write_result(args.result_file, payload)

        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode="production",
            priority=result["priority"],
            pass_filter=result["pass_filter"],
        )
        print(json.dumps(payload, ensure_ascii=True))

    except MonetizationFilterError as exc:
        error_msg = str(exc)
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "error": error_msg,
            "pass_filter": False,
            "priority": "LOW",
        }
        maybe_write_result(args.result_file, payload)
        log_event(project_id=project_id, step=STEP_NAME, status="failed", mode="production", error=error_msg)
        print(json.dumps(payload, ensure_ascii=True))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
