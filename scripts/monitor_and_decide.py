#!/usr/bin/env python3
"""
Evaluate project signals and emit kill/optimize/scale candidates.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory_utils import maybe_write_result
from state_store import StageTransitionError, StateStore

ALLOWED_TRAFFIC = {"LOW", "MEDIUM", "HIGH"}
ALLOWED_ACTIVATION = {"LOW", "MEDIUM", "HIGH"}
ALLOWED_REVENUE = {"NONE", "WEAK", "STRONG"}


class MonitorDecisionError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decide(traffic_signal: str, activation_metric: str, revenue_signal_status: str) -> str:
    if traffic_signal == "LOW" and revenue_signal_status == "NONE":
        return "kill_candidate"
    if traffic_signal == "HIGH" and revenue_signal_status == "STRONG":
        return "scale_candidate"
    if activation_metric == "LOW" and revenue_signal_status in {"NONE", "WEAK"}:
        return "kill_candidate"
    if activation_metric == "MEDIUM" and revenue_signal_status == "WEAK":
        return "optimize_candidate"
    return "optimize_candidate"


def load_signal_data(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MonitorDecisionError(f"Signal file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MonitorDecisionError(f"Signal file JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise MonitorDecisionError("Signal file must contain a JSON object.")
    return payload


def normalize_signal(payload: dict[str, Any], field_name: str, allowed: set[str]) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise MonitorDecisionError(f"Missing or invalid field '{field_name}'.")
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise MonitorDecisionError(
            f"Field '{field_name}' must be one of {sorted(allowed)}. Got '{value}'."
        )
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate monitoring signals and emit portfolio decision")
    parser.add_argument("--state-db", required=True, help="Path to lifecycle SQLite database")
    parser.add_argument("--run-id", default="", help="Workflow run id")
    parser.add_argument("--run-attempt", default="", help="Workflow run attempt")
    parser.add_argument("--project-id", default="", help="Project identifier")
    parser.add_argument("--traffic-signal", default="", help="LOW/MEDIUM/HIGH")
    parser.add_argument("--activation-metric", default="", help="LOW/MEDIUM/HIGH")
    parser.add_argument("--revenue-signal-status", default="", help="NONE/WEAK/STRONG")
    parser.add_argument("--signal-file", default="", help="Optional path to monitor signals JSON")
    parser.add_argument("--result-file", default="", help="Path to write decision JSON")
    parser.add_argument("--timestamp-utc", default="", help="UTC timestamp")
    args = parser.parse_args()

    run_id = str(args.run_id).strip()
    run_attempt = str(args.run_attempt).strip()
    project_id = str(args.project_id).strip().lower()
    timestamp_utc = str(args.timestamp_utc).strip() or utc_now()

    signal_payload: dict[str, Any] = {}
    if args.signal_file:
        signal_payload = load_signal_data(Path(args.signal_file).expanduser().resolve())

    traffic_signal = str(args.traffic_signal or signal_payload.get("traffic_signal", "")).strip().upper()
    activation_metric = str(args.activation_metric or signal_payload.get("activation_metric", "")).strip().upper()
    revenue_signal_status = str(
        args.revenue_signal_status or signal_payload.get("revenue_signal_status", "")
    ).strip().upper()

    if not run_id:
        run_id = str(signal_payload.get("run_id", "")).strip()
    if not run_attempt:
        run_attempt = str(signal_payload.get("run_attempt", "")).strip()
    if not project_id:
        project_id = str(signal_payload.get("project_id", "")).strip().lower()

    if not run_id or not run_attempt or not project_id:
        raise SystemExit("[error] run-id, run-attempt, and project-id are required")

    try:
        if traffic_signal not in ALLOWED_TRAFFIC:
            raise MonitorDecisionError("traffic_signal must be LOW/MEDIUM/HIGH")
        if activation_metric not in ALLOWED_ACTIVATION:
            raise MonitorDecisionError("activation_metric must be LOW/MEDIUM/HIGH")
        if revenue_signal_status not in ALLOWED_REVENUE:
            raise MonitorDecisionError("revenue_signal_status must be NONE/WEAK/STRONG")

        portfolio_decision = decide(traffic_signal, activation_metric, revenue_signal_status)

        store = StateStore(args.state_db)
        store.record_monitoring_signal(
            run_id=run_id,
            run_attempt=run_attempt,
            project_id=project_id,
            traffic_signal=traffic_signal,
            activation_metric=activation_metric,
            revenue_signal_status=revenue_signal_status,
            portfolio_decision=portfolio_decision,
            timestamp_utc=timestamp_utc,
        )

        target_state = ""
        if portfolio_decision == "scale_candidate":
            target_state = "scaled"
        elif portfolio_decision == "kill_candidate":
            target_state = "killed"

        if target_state:
            try:
                store.transition(
                    run_id=run_id,
                    run_attempt=run_attempt,
                    project_id=project_id,
                    to_state=target_state,
                    reason=f"Monitoring decision: {portfolio_decision}",
                    metadata={
                        "traffic_signal": traffic_signal,
                        "activation_metric": activation_metric,
                        "revenue_signal_status": revenue_signal_status,
                        "portfolio_decision": portfolio_decision,
                    },
                    timestamp_utc=timestamp_utc,
                )
            except StageTransitionError:
                # Ignore transition when run is not at monitored yet; we still return candidate signals.
                pass

        payload = {
            "project_id": project_id,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "traffic_signal": traffic_signal,
            "activation_metric": activation_metric,
            "revenue_signal_status": revenue_signal_status,
            "portfolio_decision": portfolio_decision,
            "kill_candidate": portfolio_decision == "kill_candidate",
            "optimize_candidate": portfolio_decision == "optimize_candidate",
            "scale_candidate": portfolio_decision == "scale_candidate",
            "status": "success",
            "timestamp_utc": timestamp_utc,
        }
        maybe_write_result(args.result_file, payload)
        print(json.dumps(payload, ensure_ascii=True))
    except MonitorDecisionError as exc:
        payload = {
            "project_id": project_id,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "status": "failed",
            "error_summary": str(exc),
            "failure_reason": "monitor_signal_validation_failed",
            "timestamp_utc": timestamp_utc,
        }
        maybe_write_result(args.result_file, payload)
        print(json.dumps(payload, ensure_ascii=True))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
