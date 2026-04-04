#!/usr/bin/env python3
"""
Generate payment links from business output data.

Supports providers: stripe, lemonsqueezy, gumroad.
Reads pricing_suggestion and monetization_model from business_output.json,
generates a payment link URL, and writes payment.config.json to the project directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result, write_json

STEP_NAME = "payment_link_generator"
SUPPORTED_PROVIDERS = ("stripe", "lemonsqueezy", "gumroad")
PROVIDER_ENV_KEYS = {
    "stripe": "STRIPE_PAYMENT_LINK",
    "lemonsqueezy": "LEMONSQUEEZY_CHECKOUT_URL",
    "gumroad": "GUMROAD_PRODUCT_URL",
}


class PaymentLinkError(Exception):
    pass


def _load_business_output(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PaymentLinkError(f"Business output file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PaymentLinkError(f"Invalid business output JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PaymentLinkError("Business output JSON must be an object.")
    return payload


def extract_primary_price(pricing_suggestion: str) -> float:
    """Extract the first dollar amount from a pricing suggestion string."""
    match = re.search(r"\$(\d+(?:\.\d{1,2})?)", pricing_suggestion)
    if match:
        return float(match.group(1))
    return 0.0


def _resolve_provider(preferred: str) -> str:
    """Return the first provider with a configured env var, starting with preferred."""
    if preferred and os.environ.get(PROVIDER_ENV_KEYS.get(preferred, ""), "").strip():
        return preferred
    for provider in SUPPORTED_PROVIDERS:
        env_key = PROVIDER_ENV_KEYS[provider]
        if os.environ.get(env_key, "").strip():
            return provider
    return preferred or "stripe"


def generate_payment_link(
    *,
    provider: str,
    project_id: str,
    product_name: str,
    pricing_value: float,
    monetization_model: str,
    dry_run: bool,
) -> str:
    """Generate a payment link URL for the given provider."""
    env_key = PROVIDER_ENV_KEYS.get(provider, "")
    configured_url = os.environ.get(env_key, "").strip() if env_key else ""

    if configured_url:
        separator = "&" if "?" in configured_url else "?"
        return f"{configured_url}{separator}client_reference_id={project_id}"

    if dry_run:
        return f"https://pay.example.com/{provider}/{project_id}?amount={pricing_value}"

    raise PaymentLinkError(
        f"No payment URL configured for provider '{provider}'. "
        f"Set {env_key} environment variable."
    )


def build_payment_config(
    *,
    business_output: dict[str, Any],
    provider: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Build payment configuration from business output data."""
    project_id = str(business_output.get("project_id", "")).strip()
    if not project_id:
        raise PaymentLinkError("Business output missing 'project_id'.")

    product_name = str(business_output.get("headline", "")).strip()
    if not product_name:
        product_name = project_id

    pricing_suggestion = str(business_output.get("pricing_suggestion", "")).strip()
    if not pricing_suggestion:
        raise PaymentLinkError("Business output missing 'pricing_suggestion'.")

    monetization_model = str(business_output.get("monetization_model", "")).strip()
    if not monetization_model:
        raise PaymentLinkError("Business output missing 'monetization_model'.")

    pricing_value = extract_primary_price(pricing_suggestion)
    resolved_provider = _resolve_provider(provider)

    payment_link = generate_payment_link(
        provider=resolved_provider,
        project_id=project_id,
        product_name=product_name,
        pricing_value=pricing_value,
        monetization_model=monetization_model,
        dry_run=dry_run,
    )

    return {
        "project_id": project_id,
        "payment_link": payment_link,
        "payment_provider": resolved_provider,
        "pricing_value": pricing_value,
        "pricing_display": pricing_suggestion,
        "monetization_model": monetization_model,
        "product_name": product_name,
        "cta": str(business_output.get("CTA", "Buy Now")).strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate payment link from business output")
    parser.add_argument("--business-output-file", required=True, help="Path to business_output.json")
    parser.add_argument("--project-dir", default="", help="Path to project directory for writing payment.config.json")
    parser.add_argument("--provider", default="stripe", choices=SUPPORTED_PROVIDERS, help="Payment provider")
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    parser.add_argument("--dry-run", action="store_true", help="Generate config without requiring live credentials")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id_for_log = "unknown"

    log_event(project_id=project_id_for_log, step=STEP_NAME, status="started", mode=mode)
    try:
        business_output = _load_business_output(Path(args.business_output_file).expanduser().resolve())
        payment_config = build_payment_config(
            business_output=business_output,
            provider=args.provider,
            dry_run=args.dry_run,
        )
        project_id_for_log = payment_config["project_id"]

        if args.project_dir:
            project_dir = Path(args.project_dir).expanduser().resolve()
            if not project_dir.is_dir():
                raise PaymentLinkError(f"--project-dir does not exist: {project_dir}")
            config_path = project_dir / "payment.config.json"
            write_json(config_path, payment_config)

        result_payload = {
            "project_id": payment_config["project_id"],
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "payment_link": payment_config["payment_link"],
            "payment_provider": payment_config["payment_provider"],
            "pricing_value": payment_config["pricing_value"],
        }
        maybe_write_result(args.result_file, result_payload)
        log_event(
            project_id=payment_config["project_id"],
            step=STEP_NAME,
            status="success",
            mode=mode,
            payment_link=payment_config["payment_link"],
            payment_provider=payment_config["payment_provider"],
            pricing_value=payment_config["pricing_value"],
        )
        print(json.dumps(payment_config, ensure_ascii=True))
    except PaymentLinkError as exc:
        error_message = str(exc)
        maybe_write_result(
            args.result_file,
            {
                "project_id": project_id_for_log,
                "step": STEP_NAME,
                "status": "failed",
                "mode": mode,
                "error": error_message,
            },
        )
        log_event(
            project_id=project_id_for_log,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            error=error_message,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
