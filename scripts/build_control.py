#!/usr/bin/env python3
"""
Build control layer — enforces rate limits, queue priority, and duplicate prevention.

Controls:
  - max_builds_per_day
  - max_parallel_builds (active non-terminal builds)
  - queue priority (by revenue score)

Prevents:
  - overbuilding
  - duplicate execution (via idempotency_key)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result, utc_timestamp
from state_store import FactoryStateStore

STEP_NAME = "build_control"


class BuildControlError(Exception):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BuildControlError(f"File not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BuildControlError(f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BuildControlError("JSON must be an object.")
    return payload


def check_build_limits(store: FactoryStateStore, max_per_day: int) -> dict[str, Any]:
    """Check if daily build limit has been reached."""
    recent = store.list_recent_runs(limit=max_per_day + 10)
    today = utc_timestamp()[:10]
    today_builds = [
        r for r in recent
        if str(r.get("updated_at", ""))[:10] == today
    ]
    count = len(today_builds)
    allowed = count < max_per_day
    return {
        "builds_today": count,
        "max_per_day": max_per_day,
        "allowed": allowed,
        "reason": "" if allowed else f"Daily build limit reached: {count}/{max_per_day}",
    }


def check_idempotency(store: FactoryStateStore, project_id: str) -> dict[str, Any]:
    """Check if a build for this project already exists and is active."""
    existing = store.get_current_state(project_id)
    if existing is None:
        return {"duplicate": False, "existing_state": None}

    state = str(existing.get("state", ""))
    terminal_states = {"rejected", "hold", "scaled", "killed"}
    if state in terminal_states:
        return {"duplicate": False, "existing_state": state}

    return {
        "duplicate": True,
        "existing_state": state,
        "reason": f"Active build exists for '{project_id}' in state '{state}'.",
    }


def check_parallel_builds(store: FactoryStateStore, max_parallel: int) -> dict[str, Any]:
    """Check if the number of active (non-terminal) builds exceeds the limit."""
    recent = store.list_recent_runs(limit=max_parallel + 50)
    terminal_states = {"rejected", "hold", "scaled", "killed"}
    active = [r for r in recent if str(r.get("state", "")) not in terminal_states]
    count = len(active)
    allowed = count < max_parallel
    return {
        "active_builds": count,
        "max_parallel": max_parallel,
        "allowed": allowed,
        "reason": "" if allowed else f"Parallel build limit reached: {count}/{max_parallel}",
    }


def evaluate_priority(score: int, demand: str, speed: str) -> dict[str, Any]:
    """Compute queue priority from business signals."""
    priority_score = score
    if demand == "HIGH":
        priority_score += 2
    elif demand == "MEDIUM":
        priority_score += 1
    if speed == "FAST":
        priority_score += 2
    elif speed == "MEDIUM":
        priority_score += 1

    if priority_score >= 12:
        priority = "HIGH"
    elif priority_score >= 8:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    return {
        "priority": priority,
        "priority_score": priority_score,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build control and rate limiting")
    parser.add_argument("--brief-file", required=True, help="Path to normalized brief JSON")
    parser.add_argument("--state-db", required=True, help="Path to lifecycle SQLite DB")
    parser.add_argument("--business-score", type=int, default=0, help="Business gate score")
    parser.add_argument("--result-file", default="", help="Path to write control result JSON")
    parser.add_argument("--project-id", default="", help="Project identifier for logging")
    parser.add_argument("--dry-run", action="store_true", help="Check limits without blocking")
    args = parser.parse_args()

    mode = "dry_run" if args.dry_run else "production"
    project_id = args.project_id.strip() or "unknown"

    try:
        max_per_day = int(os.environ.get("MAX_BUILDS_PER_DAY", "20"))
    except ValueError:
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="warning",
            mode=mode,
            message="MAX_BUILDS_PER_DAY is malformed, defaulting to 20",
            env_var="MAX_BUILDS_PER_DAY",
            fallback_value=20,
        )
        max_per_day = 20
    try:
        max_parallel = int(os.environ.get("MAX_PARALLEL_BUILDS", "3"))
    except ValueError:
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="warning",
            mode=mode,
            message="MAX_PARALLEL_BUILDS is malformed, defaulting to 3",
            env_var="MAX_PARALLEL_BUILDS",
            fallback_value=3,
        )
        max_parallel = 3

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode=mode)

    try:
        brief = _load_json(Path(args.brief_file).expanduser().resolve())
        project_id = str(brief.get("project_id", project_id)).strip().lower()

        store = FactoryStateStore(args.state_db)
        try:
            limits = check_build_limits(store, max_per_day)
            idempotency = check_idempotency(store, project_id)
            parallel = check_parallel_builds(store, max_parallel)
        finally:
            store.close()

        demand = str(brief.get("demand_level", "MEDIUM")).strip().upper()
        speed = str(brief.get("speed_to_revenue", "MEDIUM")).strip().upper()
        priority = evaluate_priority(args.business_score, demand, speed)

        blocked = False
        block_reasons: list[str] = []

        if not limits["allowed"]:
            blocked = True
            block_reasons.append(str(limits["reason"]))

        if idempotency.get("duplicate"):
            blocked = True
            block_reasons.append(str(idempotency.get("reason", "Duplicate build detected.")))

        if not parallel["allowed"]:
            blocked = True
            block_reasons.append(str(parallel["reason"]))

        control_decision = "BLOCKED" if blocked and not args.dry_run else "ALLOWED"

        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "control_decision": control_decision,
            "block_reasons": block_reasons,
            "limits": limits,
            "idempotency_check": idempotency,
            "parallel_check": parallel,
            "priority": priority,
        }

        maybe_write_result(args.result_file, payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode=mode,
            control_decision=control_decision,
        )
        print(json.dumps(payload, ensure_ascii=True))

        if blocked and not args.dry_run:
            raise SystemExit(1)

    except BuildControlError as exc:
        error_message = str(exc)
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "mode": mode,
            "control_decision": "BLOCKED",
            "error": error_message,
        }
        maybe_write_result(args.result_file, payload)
        log_event(project_id=project_id, step=STEP_NAME, status="failed", mode=mode, error=error_message)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
