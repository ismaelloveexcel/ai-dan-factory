#!/usr/bin/env python3
"""
generate_video_concept.py - AI-powered promo video script generator.

Uses Grok (real-time web) → OpenAI → template fallback to generate a JSON
concept file for the MoviePy video renderer.
"""
import argparse
import json
import os
import sys

import httpx


def grok_concept(product: str, tagline: str, url: str, region: str) -> dict:
    api_key = os.environ.get("GROK_API_KEY") or os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("No GROK_API_KEY set")
    prompt = f"""You are a viral social media video director.
Create a punchy 30-second promo video script for:
- Product: {product}
- Tagline: {tagline}
- URL: {url}
- Target Region: {region}

Return ONLY valid JSON with this exact structure:
{{
  "hook": "Opening hook sentence (max 8 words, grabs attention)",
  "problem": "Pain point we solve (1 sentence)",
  "solution": "What the product does (1 sentence)",
  "cta": "Call to action (max 6 words)",
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "tone": "fun|urgent|inspirational|professional",
  "bg_color": "#hex (brand/region-appropriate)",
  "accent_color": "#hex"
}}"""
    resp = httpx.post(
        "https://api.x.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "grok-beta", "messages": [{"role": "user", "content": prompt}], "temperature": 0.8},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])


def openai_concept(product: str, tagline: str, url: str, region: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("No OPENAI_API_KEY set")
    prompt = f"""Create a viral 30-second promo video script for:
- Product: {product}
- Tagline: {tagline}
- URL: {url}
- Region: {region}

Return ONLY valid JSON:
{{
  "hook": "Opening hook (max 8 words)",
  "problem": "Pain point (1 sentence)",
  "solution": "What it does (1 sentence)",
  "cta": "Call to action (max 6 words)",
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "tone": "fun",
  "bg_color": "#1a0533",
  "accent_color": "#7c3aed"
}}"""
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.8},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])


def template_concept(product: str, tagline: str, url: str, region: str) -> dict:
    return {
        "hook": f"Introducing {product}",
        "problem": "Tired of the same old solutions?",
        "solution": tagline or f"{product} changes everything.",
        "cta": f"Try {product} free today",
        "hashtags": [product.lower().replace(" ", ""), "startup", "innovation", region.lower(), "ai"],
        "tone": "fun",
        "bg_color": "#1a0533",
        "accent_color": "#7c3aed",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", required=True)
    parser.add_argument("--tagline", default="")
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--region", default="global")
    parser.add_argument("--output", default="artifacts/video_concept.json")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    concept = None
    for fn in [grok_concept, openai_concept]:
        try:
            concept = fn(args.product, args.tagline, args.url, args.region)
            print(f"✓ Concept generated via {fn.__name__}")
            break
        except Exception as e:
            print(f"  {fn.__name__} failed: {e}", file=sys.stderr)

    if concept is None:
        concept = template_concept(args.product, args.tagline, args.url, args.region)
        print("✓ Using template concept (no AI keys set)")

    concept["product"] = args.product
    concept["tagline"] = args.tagline
    concept["url"] = args.url
    concept["region"] = args.region

    with open(args.output, "w") as f:
        json.dump(concept, f, indent=2)

    print(f"✓ Concept saved to {args.output}")
    print(json.dumps(concept, indent=2))


if __name__ == "__main__":
    main()
