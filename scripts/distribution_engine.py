#!/usr/bin/env python3
"""
Distribution execution engine — generates distribution content and tracks outreach.

Generates:
  - landing page content summary
  - first post content (social media)
  - outreach messages (5-10 targets)

Tracks:
  - distribution_status
  - content generated
  - targets identified
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result, utc_timestamp

STEP_NAME = "distribution"


class DistributionError(Exception):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DistributionError(f"File not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DistributionError(f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DistributionError("JSON must be an object.")
    return payload


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DistributionError(f"Missing required field '{key}'.")
    return value.strip()


def _generate_landing_content(brief: dict[str, Any], business_output: dict[str, Any]) -> dict[str, str]:
    """Generate landing page content summary."""
    product_name = _required_str(brief, "product_name")
    problem = _required_str(brief, "problem")
    solution = _required_str(brief, "solution")
    cta = _required_str(brief, "cta")

    headline = str(business_output.get("headline", f"{product_name}: {solution}"))
    pricing = str(business_output.get("pricing_suggestion", "Contact for pricing"))

    return {
        "headline": headline,
        "subheadline": f"Solve: {problem[:100]}",
        "value_proposition": solution[:200],
        "cta_text": cta,
        "pricing_summary": pricing,
    }


def _generate_first_post(brief: dict[str, Any], business_output: dict[str, Any]) -> dict[str, str]:
    """Generate social media launch post."""
    product_name = _required_str(brief, "product_name")
    problem = _required_str(brief, "problem")
    solution = _required_str(brief, "solution")
    cta = _required_str(brief, "cta")
    source_type = str(brief.get("source_type", "")).upper()

    gtm_plan = business_output.get("gtm_plan") or []
    primary_channel = gtm_plan[0]["channel"] if len(gtm_plan) > 0 else "Social Media"

    post_body = (
        f"Introducing {product_name}\n\n"
        f"Problem: {problem[:120]}\n"
        f"Solution: {solution[:120]}\n\n"
        f"{cta}\n\n"
        f"#launch #saas #buildinpublic"
    )

    return {
        "channel": primary_channel,
        "post_body": post_body,
        "post_type": "launch_announcement",
        "source_type": source_type,
    }


def _generate_outreach_targets(brief: dict[str, Any], business_output: dict[str, Any]) -> list[dict[str, str]]:
    """Generate outreach target list with personalized messages."""
    product_name = _required_str(brief, "product_name")
    problem = _required_str(brief, "problem")
    solution = _required_str(brief, "solution")
    source_type = str(brief.get("source_type", "TREND")).upper()

    channel_map = {
        "TREND": [
            {"segment": "Tech early adopters", "channel": "Twitter/X"},
            {"segment": "Newsletter curators", "channel": "Email"},
            {"segment": "Indie hackers", "channel": "IndieHackers"},
            {"segment": "Product hunters", "channel": "Product Hunt"},
            {"segment": "Tech bloggers", "channel": "Blog outreach"},
        ],
        "COMPETITOR": [
            {"segment": "Competitor users (frustrated)", "channel": "Reddit"},
            {"segment": "Review site commenters", "channel": "G2/Capterra"},
            {"segment": "Migration seekers", "channel": "Google Ads"},
            {"segment": "Comparison shoppers", "channel": "SEO"},
            {"segment": "Industry forums", "channel": "Forum outreach"},
        ],
        "GAP": [
            {"segment": "Niche community leaders", "channel": "Discord/Slack"},
            {"segment": "Underserved professionals", "channel": "LinkedIn"},
            {"segment": "Beta testers", "channel": "BetaList"},
            {"segment": "Niche newsletter subscribers", "channel": "Email"},
            {"segment": "Micro-influencers", "channel": "Social DM"},
        ],
        "EXISTING_PRODUCT": [
            {"segment": "Current power users", "channel": "In-app"},
            {"segment": "Churned customers", "channel": "Email"},
            {"segment": "Adjacent product users", "channel": "LinkedIn"},
            {"segment": "B2B decision makers", "channel": "LinkedIn"},
            {"segment": "Enterprise evaluators", "channel": "Email"},
        ],
    }

    targets = channel_map.get(source_type, channel_map["TREND"])

    outreach_message = (
        f"Hi — I built {product_name} to solve a specific problem: {problem[:80]}. "
        f"It works by {solution[:80]}. "
        f"Would love your feedback if this resonates."
    )

    return [
        {
            "target_segment": t["segment"],
            "channel": t["channel"],
            "message_template": outreach_message,
            "status": "generated",
        }
        for t in targets
    ]


def _generate_monetization_summary(brief: dict[str, Any], business_output: dict[str, Any]) -> dict[str, str]:
    """Generate a ready-to-use monetization summary for distribution."""
    product_name = _required_str(brief, "product_name")
    model = str(business_output.get("monetization_model", "subscription"))
    pricing = str(business_output.get("pricing_suggestion", "Contact for pricing"))
    target_user = str(business_output.get("target_user", "Professionals seeking better tools"))
    distribution_plan = str(business_output.get("distribution_plan", ""))

    return {
        "product_idea": product_name,
        "target_user": target_user,
        "monetization_method": model,
        "pricing_hint": pricing,
        "distribution_plan": distribution_plan or f"Launch {product_name} across primary channels with CTA-driven landing page.",
    }


def generate_distribution(
    brief: dict[str, Any],
    business_output: dict[str, Any],
    deployment_url: str = "",
) -> dict[str, Any]:
    """Generate full distribution package."""
    landing_content = _generate_landing_content(brief, business_output)
    first_post = _generate_first_post(brief, business_output)
    outreach_targets = _generate_outreach_targets(brief, business_output)
    monetization_summary = _generate_monetization_summary(brief, business_output)

    return {
        "landing_content": landing_content,
        "first_post": first_post,
        "outreach_targets": outreach_targets,
        "outreach_count": len(outreach_targets),
        "monetization_summary": monetization_summary,
        "deployment_url": deployment_url,
        "distribution_status": "content_generated",
        "tracking": {
            "impressions": 0,
            "clicks": 0,
            "responses": 0,
            "generated_at": utc_timestamp(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Distribution execution engine")
    parser.add_argument("--brief-file", required=True, help="Path to normalized brief JSON")
    parser.add_argument("--business-output-file", required=True, help="Path to business_output.json")
    parser.add_argument("--deployment-url", default="", help="Deployed product URL")
    parser.add_argument("--result-file", default="", help="Path to write distribution result JSON")
    parser.add_argument("--project-id", default="", help="Project identifier for logging")
    parser.add_argument("--dry-run", action="store_true", help="Generate content without executing")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id = args.project_id.strip() or "unknown"

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode=mode)

    try:
        brief = _load_json(Path(args.brief_file).expanduser().resolve())
        business_output = _load_json(Path(args.business_output_file).expanduser().resolve())
        project_id = str(brief.get("project_id", project_id)).strip().lower()

        result = generate_distribution(
            brief=brief,
            business_output=business_output,
            deployment_url=args.deployment_url,
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
            outreach_count=result["outreach_count"],
            distribution_status=result["distribution_status"],
        )
        print(json.dumps(payload, ensure_ascii=True))

    except DistributionError as exc:
        error_message = str(exc)
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "mode": mode,
            "distribution_status": "failed",
            "error": error_message,
        }
        maybe_write_result(args.result_file, payload)
        log_event(project_id=project_id, step=STEP_NAME, status="failed", mode=mode, error=error_message)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
