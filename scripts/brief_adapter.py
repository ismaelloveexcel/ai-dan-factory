#!/usr/bin/env python3
"""
Brief adapter — converts AI-DAN Managing Director BuildBrief (Repo 1 schema)
to the AI-DAN Factory BuildBrief v1 (Repo 2 schema).

The Managing Director sends a Pydantic-serialized BuildBrief with fields like:
  schema_version, idea_id, hypothesis, target_user, problem, solution,
  mvp_scope, acceptance_criteria, landing_page_requirements, command_bundle,
  feature_flags, validation_score, risk_flags, monetization_model, cta, pricing_hint

The Factory expects a flat JSON with fields like:
  project_id, product_name, problem, solution, cta, source_type,
  reference_context, demand_level, monetization_proof, market_saturation,
  differentiation, build_complexity, speed_to_revenue, target_user

This adapter bridges the gap so the two repos can communicate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def adapt_brief(md_brief: dict[str, Any]) -> dict[str, Any]:
    """Convert a Managing Director BuildBrief to a Factory BuildBrief v1.

    Args:
        md_brief: The JSON-decoded BuildBrief from the Managing Director.

    Returns:
        A Factory-compatible BuildBrief v1 dict.
    """
    # If the brief already has Factory-native fields, pass through
    if "source_type" in md_brief and "demand_level" in md_brief:
        return md_brief

    # Extract command_bundle for business package signals
    cmd = md_brief.get("command_bundle", {})
    business_pkg = cmd.get("business_package", {})
    score_data = cmd.get("score", {})
    breakdown = score_data.get("breakdown", {})

    # --- Map fields ---

    project_id = md_brief.get("project_id", "")

    # product_name: from hypothesis or idea title
    product_name = (
        md_brief.get("product_name")
        or md_brief.get("hypothesis", "")[:120]
        or project_id
    )

    problem = md_brief.get("problem", "")
    solution = md_brief.get("solution", "")
    cta = md_brief.get("cta", "Get Started")

    # source_type inference from command_bundle or default
    source_type = _infer_source_type(md_brief, business_pkg)

    # reference_context: combine hypothesis + market truth
    market_truth = cmd.get("market_truth", {})
    reference_context = _build_reference_context(md_brief, market_truth)

    # demand_level from validation_score or market truth
    demand_level = _infer_demand_level(md_brief, breakdown, market_truth)

    # monetization_proof from monetization_model
    monetization_model = md_brief.get("monetization_model", "unspecified")
    monetization_proof = "YES" if monetization_model not in ("unspecified", "", None) else "NO"

    # If business package has pricing, it's proven
    if business_pkg.get("pricing_model") or business_pkg.get("price_range"):
        monetization_proof = "YES"

    # market_saturation from breakdown
    market_saturation = _infer_saturation(breakdown)

    # differentiation from risk_flags and score
    differentiation = _infer_differentiation(md_brief, breakdown)

    # build_complexity from mvp_scope length
    mvp_scope = md_brief.get("mvp_scope", [])
    build_complexity = "LOW" if len(mvp_scope) <= 2 else ("MEDIUM" if len(mvp_scope) <= 4 else "HIGH")

    # speed_to_revenue from pricing_hint
    speed_to_revenue = _infer_speed(md_brief, business_pkg)

    # target_user passthrough
    target_user = md_brief.get("target_user", "")

    factory_brief: dict[str, Any] = {
        "project_id": project_id,
        "product_name": product_name,
        "problem": problem,
        "solution": solution,
        "cta": cta,
        "source_type": source_type,
        "reference_context": reference_context,
        "demand_level": demand_level,
        "monetization_proof": monetization_proof,
        "market_saturation": market_saturation,
        "differentiation": differentiation,
        "build_complexity": build_complexity,
        "speed_to_revenue": speed_to_revenue,
        "target_user": target_user,
    }

    # Preserve MD-specific fields for audit trail
    factory_brief["_md_idea_id"] = md_brief.get("idea_id", "")
    factory_brief["_md_correlation_id"] = md_brief.get("correlation_id", "")
    factory_brief["_md_schema_version"] = md_brief.get("schema_version", "")

    return factory_brief


def _infer_source_type(md_brief: dict[str, Any], business_pkg: dict[str, Any]) -> str:
    """Infer source_type from available signals."""
    # Check if explicitly provided
    if md_brief.get("source_type") in ("TREND", "COMPETITOR", "GAP", "EXISTING_PRODUCT"):
        return md_brief["source_type"]

    # Infer from GTM strategy
    gtm = business_pkg.get("gtm_strategy", "")
    hypothesis = md_brief.get("hypothesis", "").lower()

    if "competitor" in hypothesis or "alternative" in hypothesis:
        return "COMPETITOR"
    if "gap" in hypothesis or "missing" in hypothesis or "underserved" in hypothesis:
        return "GAP"
    if "existing" in hypothesis or "improve" in hypothesis:
        return "EXISTING_PRODUCT"
    return "TREND"


def _build_reference_context(md_brief: dict[str, Any], market_truth: dict[str, Any]) -> str:
    """Build reference_context from hypothesis and market truth."""
    parts = []
    if md_brief.get("hypothesis"):
        parts.append(md_brief["hypothesis"])
    if market_truth.get("reason"):
        parts.append(market_truth["reason"])
    if md_brief.get("pricing_hint"):
        parts.append(f"Pricing: {md_brief['pricing_hint']}")
    if md_brief.get("target_user"):
        parts.append(f"Target: {md_brief['target_user']}")

    context = ". ".join(parts)
    return context[:2000] if context else "Derived from AI-DAN Managing Director analysis."


def _infer_demand_level(
    md_brief: dict[str, Any],
    breakdown: dict[str, Any],
    market_truth: dict[str, Any],
) -> str:
    """Infer demand_level from validation_score and breakdown."""
    if md_brief.get("demand_level") in ("HIGH", "MEDIUM", "LOW"):
        return md_brief["demand_level"]

    # From validation score (0.0-1.0)
    score = md_brief.get("validation_score", 0.0)
    if score >= 0.7:
        return "HIGH"
    if score >= 0.4:
        return "MEDIUM"

    # From market_demand breakdown
    md_score = breakdown.get("market_demand", 0)
    if md_score >= 1.5:
        return "HIGH"
    if md_score >= 1.0:
        return "MEDIUM"

    return "MEDIUM"  # Safe default to avoid immediate reject


def _infer_saturation(breakdown: dict[str, Any]) -> str:
    """Infer market_saturation from competition breakdown."""
    comp = breakdown.get("competition_saturation", 1.0)
    if comp >= 1.5:
        return "LOW"
    if comp >= 0.5:
        return "MEDIUM"
    return "HIGH"


def _infer_differentiation(md_brief: dict[str, Any], breakdown: dict[str, Any]) -> str:
    """Infer differentiation strength."""
    if md_brief.get("differentiation") in ("STRONG", "WEAK"):
        return md_brief["differentiation"]

    risk_flags = md_brief.get("risk_flags", [])
    if any("competition" in r.lower() or "crowded" in r.lower() for r in risk_flags):
        return "WEAK"

    # From total score if available
    total = sum(breakdown.get(k, 0) for k in breakdown)
    if total >= 7:
        return "STRONG"
    return "STRONG"  # Optimistic default since MD already approved


def _infer_speed(md_brief: dict[str, Any], business_pkg: dict[str, Any]) -> str:
    """Infer speed_to_revenue."""
    if md_brief.get("speed_to_revenue") in ("FAST", "MEDIUM", "SLOW"):
        return md_brief["speed_to_revenue"]

    pricing = business_pkg.get("pricing_model", "")
    if "subscription" in pricing.lower() or "saas" in pricing.lower():
        return "FAST"
    if "freemium" in pricing.lower():
        return "MEDIUM"
    return "MEDIUM"


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert MD BuildBrief to Factory BuildBrief v1")
    parser.add_argument("--input", required=True, help="Path to MD BuildBrief JSON")
    parser.add_argument("--output", required=True, help="Path to write Factory BuildBrief JSON")
    args = parser.parse_args()

    try:
        md_brief = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        print(f"[brief_adapter] Failed to read input: {exc}", file=sys.stderr)
        return 1

    factory_brief = adapt_brief(md_brief)

    Path(args.output).write_text(
        json.dumps(factory_brief, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"[brief_adapter] Adapted brief written to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
