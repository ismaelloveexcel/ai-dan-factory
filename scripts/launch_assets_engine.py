#!/usr/bin/env python3
"""
Launch Assets Engine — generate sales collateral after a successful deploy.

Given the product brief and live deployment URL, generates:
  1. X (Twitter) launch post  — hook + problem + solution + CTA + URL
  2. LinkedIn launch post     — professional angle, more context
  3. Cold outreach email      — short, direct, personalised template
  4. Launch checklist         — ordered actions for the first 48 h

Outputs:
  - LAUNCH_ASSETS.md  (human-readable, injected into the generated repo)
  - <result-file>.json (machine-readable for callbacks and the Managing Director)

Falls back to deterministic templates when OPENAI_API_KEY is not set,
marking quality_level as "reduced".  The operator gets usable copy either way.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result

STEP_NAME = "launch_assets"


class LaunchAssetsError(Exception):
    pass


# ---------------------------------------------------------------------------
# Brief helpers
# ---------------------------------------------------------------------------

def _required_str(brief: dict[str, Any], key: str) -> str:
    value = brief.get(key, "")
    if not value:
        raise LaunchAssetsError(f"Brief is missing required field: '{key}'")
    return str(value).strip()


def _optional_str(brief: dict[str, Any], key: str, default: str = "") -> str:
    return str(brief.get(key, default) or default).strip()


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def _call_openai(prompt: str, api_key: str, max_tokens: int = 900) -> str:
    body = json.dumps({
        "model": "gpt-3.5-turbo",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a direct-response copywriter who writes launch posts and cold emails "
                    "for solo founders. Write clear, specific, conversational copy. "
                    "No corporate speak. No fluff. No emojis unless explicitly requested. "
                    "Output valid JSON only, with no markdown fencing."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.75,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return str(result["choices"][0]["message"]["content"]).strip()
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        raise LaunchAssetsError(f"OpenAI API call failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _build_launch_prompt(
    brief: dict[str, Any],
    deployment_url: str,
) -> str:
    product_name = _required_str(brief, "product_name")
    problem = _required_str(brief, "problem")
    solution = _required_str(brief, "solution")
    target_audience = _optional_str(brief, "target_audience", "solo founders and small teams")
    pricing = _optional_str(brief, "pricing", "")
    cta = _optional_str(brief, "cta", "Try it free")

    pricing_line = f"Pricing: {pricing}" if pricing else ""

    return f"""
Product: {product_name}
Problem it solves: {problem}
Solution: {solution}
Target audience: {target_audience}
{pricing_line}
CTA: {cta}
Live URL: {deployment_url}

Write launch copy for a solo founder's first launch. Return JSON with exactly these keys:

{{
  "x_post": "<tweet under 280 characters. Hook first. Mention the problem. Solution. URL at end. Conversational.>",
  "linkedin_post": "<150-250 word LinkedIn post. Start with a bold opening line. Problem → solution → what makes it different → CTA with URL. Professional but human.>",
  "cold_email_subject": "<email subject line under 8 words. Curiosity or benefit.>",
  "cold_email_body": "<email body, 80-120 words. Address the problem they know they have. What this does. One specific action. No fluff.>",
  "product_hunt_tagline": "<tagline under 60 characters for Product Hunt>",
  "reddit_title": "<Reddit post title, sounds like a real person sharing a tool they built, under 100 characters>"
}}
""".strip()


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------

def _fallback_assets(brief: dict[str, Any], deployment_url: str) -> dict[str, Any]:
    """Deterministic copy when OpenAI is unavailable. Usable, not perfect."""
    product_name = _optional_str(brief, "product_name", "this product")
    problem = _optional_str(brief, "problem", "a real problem")
    solution = _optional_str(brief, "solution", "a better way")
    target_audience = _optional_str(brief, "target_audience", "founders")
    cta = _optional_str(brief, "cta", "Try it free")

    return {
        "x_post": (
            f"Just launched {product_name} — {problem}. "
            f"{solution}. Built for {target_audience}. "
            f"{cta}: {deployment_url}"
        )[:280],
        "linkedin_post": (
            f"I just launched {product_name}.\n\n"
            f"The problem: {problem}\n\n"
            f"The solution: {solution}\n\n"
            f"Built for {target_audience} who want results without the complexity.\n\n"
            f"{cta}: {deployment_url}"
        ),
        "cold_email_subject": f"{product_name} — built for {target_audience}",
        "cold_email_body": (
            f"Hi [Name],\n\n"
            f"I built {product_name} to solve {problem}.\n\n"
            f"It {solution}.\n\n"
            f"Worth 2 minutes of your time: {deployment_url}\n\n"
            f"Happy to answer any questions.\n\n"
            f"[Your name]"
        ),
        "product_hunt_tagline": f"{product_name} — {solution[:50]}",
        "reddit_title": f"I built {product_name} to solve {problem[:60]}",
    }


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------

LAUNCH_CHECKLIST = [
    ("1h", "Post the X (Twitter) launch post — paste it exactly"),
    ("1h", "Post the LinkedIn post"),
    ("2h", "Post in 2-3 relevant Reddit communities using the Reddit title"),
    ("2h", "Direct message 10 people in your target audience with the cold email"),
    ("3h", "Submit to Product Hunt (schedule for 12:01 AM PST on launch day)"),
    ("Day 1", "Reply to every comment and DM personally — do not delegate this"),
    ("Day 1", "Check Stripe for any payments — if zero, do outreach, not more posting"),
    ("Day 2", "Email anyone who signed up but didn't pay — ask what stopped them"),
    ("Day 3", "Review traffic vs signups vs payments — kill, iterate, or scale"),
    ("Week 1", "If 0 paying customers: talk to 5 target users, find the real objection"),
    ("Week 1", "If 1+ paying customer: double down — ask for a referral and a testimonial"),
]


def _build_checklist_md(checklist: list[tuple[str, str]]) -> str:
    lines = ["## Launch Checklist\n"]
    for timing, action in checklist:
        lines.append(f"- **{timing}** — {action}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def _build_launch_assets_md(
    assets: dict[str, Any],
    deployment_url: str,
    product_name: str,
    quality_level: str,
) -> str:
    quality_note = (
        ""
        if quality_level == "ai"
        else "\n> ⚠️ AI copy generation was skipped (OPENAI_API_KEY not set). "
             "These are deterministic templates — edit before posting.\n"
    )

    return f"""# 🚀 Launch Assets — {product_name}

**Live URL:** {deployment_url}
{quality_note}
---

## X (Twitter) Post

Copy and paste this. Post it now.

```
{assets["x_post"]}
```

---

## LinkedIn Post

```
{assets["linkedin_post"]}
```

---

## Cold Outreach Email

**Subject:** {assets["cold_email_subject"]}

```
{assets["cold_email_body"]}
```

---

## Product Hunt

**Tagline:** {assets["product_hunt_tagline"]}

---

## Reddit

**Title:** {assets["reddit_title"]}

---

{_build_checklist_md(LAUNCH_CHECKLIST)}

---

*Generated by AI-DAN Factory. Edit before posting — specificity beats generic every time.*
"""


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def generate_launch_assets(
    brief: dict[str, Any],
    deployment_url: str,
    project_id: str,
    mode: str,
) -> tuple[dict[str, Any], str]:
    """
    Generate launch assets from a build brief and deployment URL.

    Returns (assets_dict, quality_level) where quality_level is "ai" or "reduced".
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if mode == "dry_run" or not api_key:
        quality_level = "reduced"
        assets = _fallback_assets(brief, deployment_url)
        if mode != "dry_run" and not api_key:
            log_event(
                project_id=project_id,
                step=STEP_NAME,
                status="info",
                mode=mode,
                note="OPENAI_API_KEY not set — using deterministic fallback copy.",
            )
    else:
        try:
            prompt = _build_launch_prompt(brief, deployment_url)
            raw = _call_openai(prompt, api_key)
            parsed = json.loads(raw)
            # Merge with fallback to fill any missing keys
            fallback = _fallback_assets(brief, deployment_url)
            assets = {key: str(parsed.get(key, fallback[key])).strip() or fallback[key]
                      for key in fallback}
            quality_level = "ai"
        except (LaunchAssetsError, json.JSONDecodeError, KeyError) as exc:
            log_event(
                project_id=project_id,
                step=STEP_NAME,
                status="warning",
                mode=mode,
                note=f"AI generation failed, using fallback: {exc}",
            )
            assets = _fallback_assets(brief, deployment_url)
            quality_level = "reduced"

    return assets, quality_level


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate launch copy assets after a deploy")
    parser.add_argument("--brief-file", required=True, help="Path to build_brief JSON file")
    parser.add_argument("--deployment-url", required=True, help="Live URL of the deployed product")
    parser.add_argument("--project-id", required=True, help="Project identifier for logging")
    parser.add_argument("--output-dir", default="", help="Directory to write LAUNCH_ASSETS.md")
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic fallback, no API calls")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id = args.project_id.strip()

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode=mode)

    try:
        brief_path = Path(args.brief_file)
        if not brief_path.is_file():
            raise LaunchAssetsError(f"Brief file not found: {brief_path}")
        brief: dict[str, Any] = json.loads(brief_path.read_text(encoding="utf-8"))

        deployment_url = args.deployment_url.strip() or f"https://{project_id}.vercel.app"
        product_name = _optional_str(brief, "product_name", project_id)

        assets, quality_level = generate_launch_assets(
            brief=brief,
            deployment_url=deployment_url,
            project_id=project_id,
            mode=mode,
        )

        # Write LAUNCH_ASSETS.md
        md_content = _build_launch_assets_md(assets, deployment_url, product_name, quality_level)
        output_dir = Path(args.output_dir) if args.output_dir else None
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            md_path = output_dir / "LAUNCH_ASSETS.md"
            md_path.write_text(md_content, encoding="utf-8")
            log_event(
                project_id=project_id,
                step=STEP_NAME,
                status="info",
                mode=mode,
                launch_assets_md=str(md_path),
            )

        result_payload: dict[str, Any] = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "quality_level": quality_level,
            "deployment_url": deployment_url,
            "product_name": product_name,
            "assets": assets,
        }
        maybe_write_result(args.result_file, result_payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode=mode,
            quality_level=quality_level,
        )

    except LaunchAssetsError as exc:
        error_message = str(exc)
        maybe_write_result(
            args.result_file,
            {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "failed",
                "mode": mode,
                "error": error_message,
            },
        )
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            error=error_message,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
