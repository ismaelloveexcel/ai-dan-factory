#!/usr/bin/env python3
"""
Deterministic scoring engine for AI-DAN business gate decisions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factory_utils import maybe_write_result

ALLOWED_SOURCE_TYPES = {"TREND", "COMPETITOR", "GAP", "EXISTING_PRODUCT"}
ALLOWED_DEMAND_LEVELS = {"HIGH", "MEDIUM", "LOW"}
ALLOWED_MONETIZATION_PROOF = {"YES", "NO"}
ALLOWED_SATURATION = {"LOW", "MEDIUM", "HIGH"}
ALLOWED_DIFFERENTIATION = {"STRONG", "WEAK"}
ALLOWED_COMPLEXITY = {"LOW", "MEDIUM", "HIGH"}
ALLOWED_SPEED_TO_REVENUE = {"FAST", "MEDIUM", "SLOW"}


class ScoringError(Exception):
    pass


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ScoringError(f"Missing required field '{key}'.")
    return value.strip()


def load_brief(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ScoringError(f"Brief file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScoringError(f"Brief JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScoringError("Brief JSON must be an object.")
    return payload


def normalize_contract(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "project_id": _required_str(payload, "project_id").lower(),
        "source_type": _required_str(payload, "source_type").upper(),
        "reference_context": _required_str(payload, "reference_context"),
        "demand_level": _required_str(payload, "demand_level").upper(),
        "monetization_proof": _required_str(payload, "monetization_proof").upper(),
        "market_saturation": _required_str(payload, "market_saturation").upper(),
        "differentiation": _required_str(payload, "differentiation").upper(),
        "build_complexity": str(payload.get("build_complexity", "MEDIUM")).strip().upper(),
        "speed_to_revenue": str(payload.get("speed_to_revenue", "MEDIUM")).strip().upper(),
    }


def validate_sets(contract: dict[str, str]) -> None:
    if contract["source_type"] not in ALLOWED_SOURCE_TYPES:
        raise ScoringError("source_type must be TREND/COMPETITOR/GAP/EXISTING_PRODUCT.")
    if contract["demand_level"] not in ALLOWED_DEMAND_LEVELS:
        raise ScoringError("demand_level must be HIGH/MEDIUM/LOW.")
    if contract["monetization_proof"] not in ALLOWED_MONETIZATION_PROOF:
        raise ScoringError("monetization_proof must be YES/NO.")
    if contract["market_saturation"] not in ALLOWED_SATURATION:
        raise ScoringError("market_saturation must be LOW/MEDIUM/HIGH.")
    if contract["differentiation"] not in ALLOWED_DIFFERENTIATION:
        raise ScoringError("differentiation must be STRONG/WEAK.")
    if contract["build_complexity"] not in ALLOWED_COMPLEXITY:
        raise ScoringError("build_complexity must be LOW/MEDIUM/HIGH.")
    if contract["speed_to_revenue"] not in ALLOWED_SPEED_TO_REVENUE:
        raise ScoringError("speed_to_revenue must be FAST/MEDIUM/SLOW.")
    if len(contract["reference_context"]) < 5:
        raise ScoringError("reference_context must contain at least 5 characters.")


def apply_hard_rules(contract: dict[str, str]) -> tuple[bool, str]:
    if contract["demand_level"] == "LOW":
        return False, "LOW demand is automatically rejected."
    if contract["monetization_proof"] == "NO":
        return False, "Monetization proof is required (NO => reject)."
    if contract["market_saturation"] == "HIGH" and contract["differentiation"] == "WEAK":
        return False, "HIGH saturation with WEAK differentiation is automatically rejected."
    return True, ""


def score_breakdown(contract: dict[str, str]) -> dict[str, int]:
    demand_map = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    saturation_map = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    monetization_map = {"NO": 0, "YES": 2}
    complexity_map = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    speed_map = {"SLOW": 0, "MEDIUM": 1, "FAST": 2}

    return {
        "market_demand": demand_map[contract["demand_level"]],
        "competition_saturation": saturation_map[contract["market_saturation"]],
        "monetization_potential": monetization_map[contract["monetization_proof"]],
        "build_complexity_reverse": complexity_map[contract["build_complexity"]],
        "speed_to_revenue": speed_map[contract["speed_to_revenue"]],
    }


def decision_from_score(total: int) -> tuple[str, str]:
    if total < 6:
        return "REJECT", "Score below 6."
    if total < 8:
        return "HOLD", "Score is 6-7."
    return "APPROVE", "Score is 8-10."


def evaluate(contract: dict[str, str]) -> dict[str, Any]:
    validate_sets(contract)
    pass_hard_rules, hard_reason = apply_hard_rules(contract)
    breakdown = score_breakdown(contract)
    total = sum(breakdown.values())
    scored_decision, scored_reason = decision_from_score(total)
    if pass_hard_rules:
        decision, reason = scored_decision, scored_reason
    else:
        decision, reason = "REJECT", hard_reason
    return {
        "decision": decision,
        "score": total,
        "reason": reason,
        "score_breakdown": breakdown,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate scoring for business gate")
    parser.add_argument("--brief-file", required=True, help="Path to brief JSON")
    parser.add_argument("--result-file", default="", help="Path to write scoring result")
    args = parser.parse_args()

    try:
        brief = load_brief(Path(args.brief_file).expanduser().resolve())
        contract = normalize_contract(brief)
        result = evaluate(contract)
        payload = {
            "project_id": contract["project_id"],
            "source_type": contract["source_type"],
            "reference_context": contract["reference_context"],
            **result,
        }
        maybe_write_result(args.result_file, payload)
        print(json.dumps(payload, ensure_ascii=True))
    except ScoringError as exc:
        payload = {
            "project_id": "unknown",
            "decision": "REJECT",
            "score": 0,
            "reason": str(exc),
            "score_breakdown": {},
        }
        maybe_write_result(args.result_file, payload)
        print(json.dumps(payload, ensure_ascii=True))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
