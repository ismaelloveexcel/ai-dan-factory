#!/usr/bin/env python3
"""
Canonical execution contracts for AI-DAN factory runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

FACTORY_RUN_RESULT_VERSION = "FactoryRunResult.v1"
BUILD_BRIEF_VERSION = "BuildBrief.v1"

ALLOWED_RUN_STATUS = {"success", "failed"}
ALLOWED_STEP_STATUS = {"success", "failed", "skipped"}

CANONICAL_STEP_ORDER = [
    "normalize_inputs",
    "automated_tests_only",
    "lifecycle_idea",
    "validate_brief",
    "validate_business_gate",
    "build_economics",
    "build_control",
    "repo_discovery",
    "lifecycle_building",
    "create_repo",
    "inject_brief",
    "business_output",
    "deploy",
    "deploy_health",
    "quality_gate",
    "lifecycle_deployed",
    "lifecycle_monitored",
    "monitoring_decision",
    "distribution",
    "notify_director",
    "portfolio_summary",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_step(step_name: str, payload: dict[str, Any], run_mode: str) -> dict[str, Any]:
    status = str(payload.get("status", "skipped")).strip().lower()
    if status not in ALLOWED_STEP_STATUS:
        status = "failed"

    message = ""
    if status == "failed":
        message = str(payload.get("error", "")).strip() or str(payload.get("reason", "")).strip()

    step: dict[str, Any] = {
        "name": step_name,
        "status": status,
        "mode": str(payload.get("mode", run_mode)).strip() or run_mode,
    }
    if message:
        step["error"] = {"code": "STEP_FAILED", "message": message}
    return step


def empty_result(*, project_id: str, run_id: str, run_attempt: str, workflow_url: str, run_mode: str) -> dict[str, Any]:
    return {
        "contract_version": FACTORY_RUN_RESULT_VERSION,
        "build_brief_contract": BUILD_BRIEF_VERSION,
        "project_id": project_id,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "workflow_url": workflow_url,
        "timestamp_utc": utc_now(),
        "status": "failed",
        "run_mode": run_mode,
        "repo_url": "",
        "deployment_url": "",
        "deployment": {"status": "not_started", "url": ""},
        "idempotency_key": "",
        "steps": [],
        "error": {"code": "UNSPECIFIED_FAILURE", "message": "Execution did not complete."},
        "error_summary": "",
        "failure_reason": "",
        "quality": {
            "status": "not_available",
            "score": None,
            "decision": "not_available",
            "reason": "",
            "breakdown": {},
        },
        "execution_signals": {
            "kill_candidate": False,
            "optimize_candidate": False,
            "scale_candidate": False,
        },
        "result_artifact": {"name": "", "path": "factory-response.json"},
    }
