#!/usr/bin/env python3
"""
Post-Launch Revenue Loop for AI-DAN Factory.

Evaluates post-deployment signals and classifies outcomes:
  - NO_TRACTION   → AUTO-KILL  (traffic LOW + revenue NONE)
  - INTEREST_ONLY → ITERATE    (some traffic but no revenue)
  - REVENUE_CONFIRMED → SCALE  (revenue signal detected)

Runs automatically as part of the monitoring workflow.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

from factory_utils import log_event, maybe_write_result
from state_store import FactoryStateStore, StageTransitionError

STEP_NAME = "revenue_loop"


class RevenueLoopError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_revenue_outcome(
    traffic_signal: str,
    activation_metric: str,
    revenue_signal_status: str,
) -> dict[str, Any]:
    """
    Classify the post-launch outcome.

    Returns:
      - outcome: NO_TRACTION | INTEREST_ONLY | REVENUE_CONFIRMED
      - action: AUTO_KILL | ITERATE | SCALE
      - reason: str
    """
    traffic = traffic_signal.strip().upper()
    activation = activation_metric.strip().upper()
    revenue = revenue_signal_status.strip().upper()

    # REVENUE_CONFIRMED: any strong revenue signal
    if revenue == "STRONG":
        return {
            "outcome": "REVENUE_CONFIRMED",
            "action": "SCALE",
            "reason": "Strong revenue signal confirmed. Ready to scale.",
        }

    # NO_TRACTION: low traffic + no revenue
    if traffic == "LOW" and revenue == "NONE":
        return {
            "outcome": "NO_TRACTION",
            "action": "AUTO_KILL",
            "reason": "No traffic and no revenue. Auto-kill recommended.",
        }

    # NO_TRACTION: low activation + no/weak revenue
    if activation == "LOW" and revenue in ("NONE", "WEAK"):
        return {
            "outcome": "NO_TRACTION",
            "action": "AUTO_KILL",
            "reason": "Low activation with no meaningful revenue. Auto-kill recommended.",
        }

    # INTEREST_ONLY: some traffic/activation but no strong revenue
    return {
        "outcome": "INTEREST_ONLY",
        "action": "ITERATE",
        "reason": "User interest detected but revenue not confirmed. Iterate on conversion.",
    }


def execute_revenue_action(
    store: FactoryStateStore,
    *,
    project_id: str,
    run_id: str,
    run_attempt: str,
    action: str,
    outcome: str,
    reason: str,
    timestamp_utc: str,
    workflow_url: str,
) -> str:
    """Execute the revenue loop action (state transition if applicable)."""
    target_state = ""
    if action == "AUTO_KILL":
        target_state = "killed"
    elif action == "SCALE":
        target_state = "scaled"

    if target_state:
        try:
            store.record_transition(
                project_id=project_id,
                from_state="monitored",
                to_state=target_state,
                status="success" if action == "SCALE" else "failed",
                reason=f"Revenue loop: {outcome} → {action}. {reason}",
                run_id=run_id,
                run_attempt=run_attempt,
                workflow_url=workflow_url,
                timestamp_utc=timestamp_utc,
                metadata={
                    "revenue_outcome": outcome,
                    "revenue_action": action,
                },
            )
            return target_state
        except StageTransitionError:
            # Run may not be at 'monitored' state yet; record decision without transition
            return ""
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-launch revenue loop evaluation")
    parser.add_argument("--state-db", required=True, help="Path to lifecycle SQLite DB")
    parser.add_argument("--project-id", required=True, help="Project identifier")
    parser.add_argument("--run-id", default="", help="Workflow run id")
    parser.add_argument("--run-attempt", default="", help="Workflow run attempt")
    parser.add_argument("--traffic-signal", required=True, help="LOW/MEDIUM/HIGH")
    parser.add_argument("--activation-metric", required=True, help="LOW/MEDIUM/HIGH")
    parser.add_argument("--revenue-signal-status", required=True, help="NONE/WEAK/STRONG")
    parser.add_argument("--workflow-url", default="", help="Workflow URL")
    parser.add_argument("--result-file", default="", help="Path to write result JSON")
    parser.add_argument("--timestamp-utc", default="", help="UTC timestamp override")
    args = parser.parse_args()

    project_id = args.project_id.strip().lower()
    timestamp_utc = args.timestamp_utc.strip() or utc_now()

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode="production")

    try:
        classification = classify_revenue_outcome(
            traffic_signal=args.traffic_signal,
            activation_metric=args.activation_metric,
            revenue_signal_status=args.revenue_signal_status,
        )

        new_state = ""
        if args.run_id and args.run_attempt:
            store = FactoryStateStore(args.state_db)
            try:
                new_state = execute_revenue_action(
                    store,
                    project_id=project_id,
                    run_id=args.run_id,
                    run_attempt=args.run_attempt,
                    action=classification["action"],
                    outcome=classification["outcome"],
                    reason=classification["reason"],
                    timestamp_utc=timestamp_utc,
                    workflow_url=args.workflow_url,
                )
            finally:
                store.close()

        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "traffic_signal": args.traffic_signal.strip().upper(),
            "activation_metric": args.activation_metric.strip().upper(),
            "revenue_signal_status": args.revenue_signal_status.strip().upper(),
            "outcome": classification["outcome"],
            "action": classification["action"],
            "reason": classification["reason"],
            "state_transitioned_to": new_state,
            "timestamp_utc": timestamp_utc,
        }
        maybe_write_result(args.result_file, payload)

        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode="production",
            outcome=classification["outcome"],
            action=classification["action"],
        )
        print(json.dumps(payload, ensure_ascii=True))

    except RevenueLoopError as exc:
        error_msg = str(exc)
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "error": error_msg,
            "timestamp_utc": timestamp_utc,
        }
        maybe_write_result(args.result_file, payload)
        log_event(project_id=project_id, step=STEP_NAME, status="failed", mode="production", error=error_msg)
        print(json.dumps(payload, ensure_ascii=True))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
