#!/usr/bin/env python3
"""
AI enhancement module — optional OpenAI integration for high-quality copy.

Generates:
  - headline
  - subheading
  - product description
  - CTA text
  - short pitch
  - benefit bullets

Falls back to deterministic templates when OPENAI_API_KEY is not set,
marking output as reduced_quality.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result

STEP_NAME = "ai_enhance"


class AIEnhanceError(Exception):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AIEnhanceError(f"File not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AIEnhanceError(f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AIEnhanceError("JSON must be an object.")
    return payload


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AIEnhanceError(f"Missing required field '{key}'.")
    return value.strip()


def _call_openai(prompt: str, api_key: str) -> str:
    """Call OpenAI chat completions API. Returns raw text response."""
    import urllib.request
    import urllib.error

    body = json.dumps({
        "model": "gpt-3.5-turbo",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a conversion copywriter for SaaS products. "
                    "Write clear, benefit-driven copy. No fluff. No emojis. "
                    "Output valid JSON only, with no markdown fencing."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 600,
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return str(result["choices"][0]["message"]["content"]).strip()
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        raise AIEnhanceError(f"OpenAI API call failed: {exc}") from exc


def _build_prompt(brief: dict[str, Any]) -> str:
    """Build the prompt for AI-generated marketing copy."""
    product_name = _required_str(brief, "product_name")
    problem = _required_str(brief, "problem")
    solution = _required_str(brief, "solution")
    cta = _required_str(brief, "cta")

    return (
        f"Product: {product_name}\n"
        f"Problem: {problem}\n"
        f"Solution: {solution}\n"
        f"Current CTA: {cta}\n\n"
        "Generate marketing copy as a JSON object with these exact keys:\n"
        '- "headline": a short problem-to-solution headline (max 10 words)\n'
        '- "subheading": one sentence explaining the value\n'
        '- "description": a compelling 2-3 sentence product description\n'
        '- "cta_text": a clear action-oriented CTA button label (max 5 words)\n'
        '- "short_pitch": a 1-sentence elevator pitch\n'
        '- "benefit_bullets": array of 3 benefit statements (each max 8 words)\n'
        "\nReturn ONLY the JSON object, no extra text."
    )


def _fallback_copy(brief: dict[str, Any]) -> dict[str, Any]:
    """Generate deterministic fallback copy when OpenAI is unavailable."""
    product_name = _required_str(brief, "product_name")
    problem = _required_str(brief, "problem")
    solution = _required_str(brief, "solution")
    cta = _required_str(brief, "cta")

    return {
        "headline": f"{product_name} — {solution[:60]}",
        "subheading": f"Stop struggling with {problem[:80]}. There's a better way.",
        "description": (
            f"{product_name} solves {problem[:100]} "
            f"by providing {solution[:100]}. "
            f"Get started today and see results immediately."
        ),
        "cta_text": cta,
        "short_pitch": f"{product_name}: {solution[:100]}",
        "benefit_bullets": [
            f"Solve {problem[:40]} instantly",
            f"Built for speed and simplicity",
            f"Start seeing results from day one",
        ],
    }


def enhance(brief: dict[str, Any], api_key: str = "") -> dict[str, Any]:
    """Generate AI-enhanced copy, falling back to templates if no API key."""
    ai_enhanced = False
    quality_level = "reduced"

    if api_key:
        try:
            prompt = _build_prompt(brief)
            raw = _call_openai(prompt, api_key)
            # Strip markdown fencing if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()
            copy = json.loads(cleaned)
            if isinstance(copy, dict) and "headline" in copy:
                ai_enhanced = True
                quality_level = "ai_enhanced"
            else:
                copy = _fallback_copy(brief)
        except (AIEnhanceError, json.JSONDecodeError, KeyError):
            copy = _fallback_copy(brief)
    else:
        copy = _fallback_copy(brief)

    # Ensure all expected keys exist
    expected_keys = ["headline", "subheading", "description", "cta_text",
                     "short_pitch", "benefit_bullets"]
    fallback = _fallback_copy(brief)
    for key in expected_keys:
        if key not in copy or not copy[key]:
            copy[key] = fallback[key]

    return {
        "ai_copy": copy,
        "ai_enhanced": ai_enhanced,
        "quality_level": quality_level,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AI enhancement for product copy")
    parser.add_argument("--brief-file", required=True, help="Path to normalized brief JSON")
    parser.add_argument("--result-file", default="", help="Path to write AI copy result JSON")
    parser.add_argument("--project-id", default="", help="Project identifier for logging")
    parser.add_argument("--dry-run", action="store_true", help="Generate copy without API call")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id = args.project_id.strip() or "unknown"

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode=mode)

    try:
        brief = _load_json(Path(args.brief_file).expanduser().resolve())
        project_id = str(brief.get("project_id", project_id)).strip().lower()

        api_key = "" if args.dry_run else os.environ.get("OPENAI_API_KEY", "")
        result = enhance(brief, api_key=api_key)

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
            ai_enhanced=result["ai_enhanced"],
            quality_level=result["quality_level"],
        )
        print(json.dumps(payload, ensure_ascii=True))

    except AIEnhanceError as exc:
        error_message = str(exc)
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "mode": mode,
            "ai_enhanced": False,
            "quality_level": "failed",
            "error": error_message,
        }
        maybe_write_result(args.result_file, payload)
        log_event(project_id=project_id, step=STEP_NAME, status="failed", mode=mode, error=error_message)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
