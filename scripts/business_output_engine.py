#!/usr/bin/env python3
"""
Generate business_output.json from an approved brief.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factory_utils import maybe_write_result, normalize_text


class BusinessOutputError(Exception):
    pass


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BusinessOutputError(f"Missing required field '{key}'.")
    return normalize_text(value)


def _load_brief(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BusinessOutputError(f"Brief file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BusinessOutputError(f"Invalid brief JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BusinessOutputError("Brief JSON must be an object.")
    return payload


def _pricing_from_signals(demand_level: str, saturation: str, differentiation: str) -> tuple[str, str]:
    if demand_level == "HIGH" and differentiation == "STRONG":
        return "subscription", "$19/month starter, $49/month growth"
    if saturation == "HIGH":
        return "one-time", "$29 launch offer + optional $9 support upsell"
    return "subscription", "$9/month entry + $29/month pro"


def _offer_structure(model: str) -> str:
    if model == "subscription":
        return "Free trial -> Starter plan -> Growth plan with annual discount."
    return "One-time purchase with onboarding upsell and optional support add-on."


def _gtm_plan(source_type: str) -> list[dict[str, str]]:
    if source_type == "TREND":
        return [
            {"channel": "SEO", "action": "Publish trend-focused comparison page and capture demand intent."},
            {"channel": "X/Twitter", "action": "Ship build-in-public launch thread with CTA to landing page."},
        ]
    if source_type == "COMPETITOR":
        return [
            {"channel": "Google Search Ads", "action": "Bid on competitor alternatives keywords with clear pricing edge."},
            {"channel": "Reddit", "action": "Share practical migration guide in relevant communities."},
        ]
    if source_type == "GAP":
        return [
            {"channel": "Product Hunt", "action": "Launch focused niche positioning with early adopter offer."},
            {"channel": "Email", "action": "Partner newsletter placements in the niche."},
        ]
    return [
        {"channel": "LinkedIn", "action": "Publish problem-solution narrative for B2B audience."},
        {"channel": "YouTube Shorts", "action": "Demonstrate quick outcomes and direct to CTA."},
    ]


def _target_user_from_source(source_type: str) -> str:
    """Identify primary target user segment based on source type."""
    user_map = {
        "TREND": "Tech-savvy early adopters and innovators tracking emerging solutions",
        "COMPETITOR": "Frustrated users of existing tools seeking a better alternative",
        "GAP": "Underserved professionals in niche markets with unmet needs",
        "EXISTING_PRODUCT": "Current users and adjacent product users ready to upgrade",
    }
    return user_map.get(source_type, user_map["TREND"])


def _distribution_plan(source_type: str, product_name: str) -> str:
    """Generate a one-paragraph distribution plan summary."""
    plan_map = {
        "TREND": (
            f"Launch {product_name} with a build-in-public campaign on X/Twitter, "
            f"publish SEO-optimized comparison content, and submit to Product Hunt "
            f"within the first week. Target tech newsletters for featured placement."
        ),
        "COMPETITOR": (
            f"Position {product_name} as the simpler alternative in competitor forums, "
            f"run targeted Google Ads on 'alternative to' keywords, and publish "
            f"migration guides on Reddit and relevant communities."
        ),
        "GAP": (
            f"Launch {product_name} on Product Hunt and BetaList, partner with niche "
            f"newsletters for early coverage, and build community presence in "
            f"Discord/Slack groups where the target audience gathers."
        ),
        "EXISTING_PRODUCT": (
            f"Re-engage existing users with {product_name} upgrade campaign, "
            f"publish LinkedIn thought leadership content, and create demo videos "
            f"for YouTube targeting B2B decision makers."
        ),
    }
    return plan_map.get(source_type, plan_map["TREND"])


def build_business_output(brief: dict[str, Any]) -> dict[str, Any]:
    project_id = _required_str(brief, "project_id").lower()
    product_name = _required_str(brief, "product_name")
    problem = _required_str(brief, "problem")
    solution = _required_str(brief, "solution")
    cta = _required_str(brief, "cta")
    source_type = _required_str(brief, "source_type").upper()
    demand_level = _required_str(brief, "demand_level").upper()
    saturation = _required_str(brief, "market_saturation").upper()
    differentiation = _required_str(brief, "differentiation").upper()

    monetization_model, pricing_suggestion = _pricing_from_signals(demand_level, saturation, differentiation)
    offer_structure = _offer_structure(monetization_model)
    gtm_plan = _gtm_plan(source_type)

    headline = f"{product_name}: {solution}"

    target_user = _target_user_from_source(source_type)
    distribution_plan = _distribution_plan(source_type, product_name)

    return {
        "project_id": project_id,
        "headline": headline,
        "CTA": cta,
        "monetization_model": monetization_model,
        "pricing_suggestion": pricing_suggestion,
        "offer_structure": offer_structure,
        "gtm_plan": gtm_plan,
        "target_user": target_user,
        "monetization_method": monetization_model,
        "pricing_hint": pricing_suggestion,
        "distribution_plan": distribution_plan,
        "conversion_hints": {
            "cta_optimization": f"Use action-first CTA matching buyer intent: '{cta}'.",
            "offer_framing": "Lead with time-to-value and concrete outcome before feature list.",
            "objection_handling": "Address setup effort, ROI timeline, and migration risk in FAQ.",
        },
        "problem": problem,
        "solution": solution,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate business output artifact")
    parser.add_argument("--brief-file", required=True, help="Path to normalized brief JSON")
    parser.add_argument("--output-file", required=True, help="Path to write business_output.json")
    parser.add_argument("--result-file", default="", help="Optional step result JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Generate output payload but do not persist file")
    args = parser.parse_args()

    try:
        brief = _load_brief(Path(args.brief_file).expanduser().resolve())
        payload = build_business_output(brief)
        output_path = Path(args.output_file).expanduser().resolve()
        if not args.dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        maybe_write_result(
            args.result_file,
            {
                "project_id": payload["project_id"],
                "step": "business_output",
                "status": "success",
                "mode": "dry_run" if args.dry_run else "production",
                "output_file": str(output_path),
                "simulated": args.dry_run,
            },
        )
        print(json.dumps(payload, ensure_ascii=True))
    except BusinessOutputError as exc:
        maybe_write_result(
            args.result_file,
            {
                "project_id": "unknown",
                "step": "business_output",
                "status": "failed",
                "mode": "dry_run" if args.dry_run else "production",
                "error": str(exc),
            },
        )
        raise SystemExit(f"[error] {exc}") from exc


if __name__ == "__main__":
    main()
