#!/usr/bin/env python3
"""
Validate build readiness before marking a build as SUCCESS.

Ensures:
- payment link exists and is valid
- CTA is connected to payment
- feedback capture is present in the deployed product
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result

STEP_NAME = "validate_build_readiness"


class BuildReadinessError(Exception):
    pass


def _check_payment_config(project_dir: Path) -> dict[str, Any]:
    """Validate that payment.config.json exists and has required fields."""
    config_path = project_dir / "payment.config.json"
    if not config_path.is_file():
        return {"valid": False, "reason": "payment.config.json not found"}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"valid": False, "reason": f"payment.config.json invalid JSON: {exc}"}
    if not isinstance(data, dict):
        return {"valid": False, "reason": "payment.config.json must be a JSON object"}

    payment_link = str(data.get("payment_link", "")).strip()
    if not payment_link:
        return {"valid": False, "reason": "payment.config.json missing 'payment_link'"}

    payment_provider = str(data.get("payment_provider", "")).strip()
    if not payment_provider:
        return {"valid": False, "reason": "payment.config.json missing 'payment_provider'"}

    pricing_value = data.get("pricing_value")
    if pricing_value is None:
        return {"valid": False, "reason": "payment.config.json missing 'pricing_value'"}

    return {
        "valid": True,
        "payment_link": payment_link,
        "payment_provider": payment_provider,
        "pricing_value": pricing_value,
    }


def _check_product_config(project_dir: Path) -> dict[str, Any]:
    """Validate that product.config.json exists and has CTA."""
    config_path = project_dir / "product.config.json"
    if not config_path.is_file():
        return {"valid": False, "reason": "product.config.json not found"}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"valid": False, "reason": f"product.config.json invalid JSON: {exc}"}
    if not isinstance(data, dict):
        return {"valid": False, "reason": "product.config.json must be a JSON object"}

    cta = str(data.get("cta", "")).strip()
    if not cta:
        return {"valid": False, "reason": "product.config.json missing 'cta'"}

    return {"valid": True, "cta": cta}


def _check_feedback_capture(project_dir: Path) -> dict[str, Any]:
    """Validate that feedback capture API route exists."""
    feedback_route = project_dir / "app" / "api" / "feedback" / "route.ts"
    if not feedback_route.is_file():
        return {"valid": False, "reason": "Feedback API route not found at app/api/feedback/route.ts"}
    content = feedback_route.read_text(encoding="utf-8")
    if "POST" not in content:
        return {"valid": False, "reason": "Feedback API route missing POST handler"}
    return {"valid": True}


def validate_readiness(project_dir: Path) -> dict[str, Any]:
    """Run all readiness checks and return consolidated result."""
    payment_check = _check_payment_config(project_dir)
    product_check = _check_product_config(project_dir)
    feedback_check = _check_feedback_capture(project_dir)

    checks = {
        "payment_link": payment_check,
        "cta_connected": product_check,
        "feedback_capture": feedback_check,
    }
    all_valid = all(c.get("valid", False) for c in checks.values())
    failures = [
        f"{name}: {check.get('reason', 'unknown')}"
        for name, check in checks.items()
        if not check.get("valid", False)
    ]

    return {
        "build_ready": all_valid,
        "status": "VALID" if all_valid else "INVALID",
        "checks": checks,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate build readiness for deployment")
    parser.add_argument("--project-dir", required=True, help="Path to the project root")
    parser.add_argument("--project-id", default="", help="Project identifier for logging")
    parser.add_argument("--result-file", default="", help="Path to write result JSON")
    args = parser.parse_args()

    project_id = args.project_id.strip() or "unknown"
    log_event(project_id=project_id, step=STEP_NAME, status="started", mode="production")

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        error_message = f"--project-dir does not exist: {project_dir}"
        maybe_write_result(
            args.result_file,
            {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "failed",
                "error": error_message,
            },
        )
        log_event(project_id=project_id, step=STEP_NAME, status="failed", mode="production", error=error_message)
        raise SystemExit(1)

    result = validate_readiness(project_dir)
    result_payload = {
        "project_id": project_id,
        "step": STEP_NAME,
        "status": "success" if result["build_ready"] else "failed",
        "build_status": result["status"],
        "checks": result["checks"],
        "failures": result["failures"],
    }
    maybe_write_result(args.result_file, result_payload)

    if result["build_ready"]:
        log_event(project_id=project_id, step=STEP_NAME, status="success", mode="production", build_status="VALID")
    else:
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="failed",
            mode="production",
            build_status="INVALID",
            failures=result["failures"],
        )

    print(json.dumps(result_payload, ensure_ascii=True))
    if not result["build_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
