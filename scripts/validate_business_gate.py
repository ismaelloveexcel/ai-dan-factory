#!/usr/bin/env python3
"""
Unified business gate for AI-DAN Factory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result
from scoring_engine import ScoringError, evaluate, normalize_contract
from state_store import FactoryStateStore, StageTransitionError

STEP_NAME = "validate_business_gate"

class BusinessGateError(Exception):
    pass


def _load_brief(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BusinessGateError(f"Brief file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BusinessGateError(f"Brief JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise BusinessGateError("Brief JSON must be an object.")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified business gate")
    parser.add_argument("--brief-file", required=True, help="Path to normalized brief JSON")
    parser.add_argument("--result-file", default="", help="Path to write gate result JSON")
    parser.add_argument("--state-db", required=True, help="Path to lifecycle SQLite DB")
    parser.add_argument("--workflow-run-id", required=True, help="GitHub run id")
    parser.add_argument("--workflow-run-attempt", required=True, help="GitHub run attempt")
    parser.add_argument("--workflow-url", default="", help="Workflow URL")
    parser.add_argument("--timestamp-utc", required=True, help="UTC timestamp")
    parser.add_argument("--run-mode", default="production", help="tests_only/dry_run/production")
    args = parser.parse_args()

    project_for_log = "unknown"
    log_event(project_id=project_for_log, step=STEP_NAME, status="started", mode=args.run_mode)

    try:
        brief = _load_brief(Path(args.brief_file).expanduser().resolve())
        contract = normalize_contract(brief)
        project_for_log = contract["project_id"]
        score_result = evaluate(contract)
        decision = str(score_result["decision"])
        total_score = int(score_result["score"])
        reason = str(score_result["reason"])
        score_breakdown = dict(score_result["score_breakdown"])

        payload = {
            "decision": decision,
            "score": total_score,
            "reason": reason,
            "validation_summary": {
                "demand_level": contract["demand_level"],
                "monetization_proof": contract["monetization_proof"],
                "saturation": contract["market_saturation"],
                "differentiation": contract["differentiation"],
            },
            "score_breakdown": score_breakdown,
            "project_id": contract["project_id"],
            "run_id": args.workflow_run_id,
            "run_attempt": args.workflow_run_attempt,
            "workflow_url": args.workflow_url,
            "timestamp_utc": args.timestamp_utc,
            "source_type": contract["source_type"],
            "reference_context": contract["reference_context"],
        }
        maybe_write_result(args.result_file, payload)

        store = FactoryStateStore(args.state_db)
        try:
            store.record_transition(
                project_id=contract["project_id"],
                from_state="idea",
                to_state="validated",
                status="success",
                reason="Business gate inputs validated.",
                run_id=args.workflow_run_id,
                run_attempt=args.workflow_run_attempt,
                workflow_url=args.workflow_url,
                timestamp_utc=args.timestamp_utc,
                metadata={
                    "source_type": contract["source_type"],
                    "demand_level": contract["demand_level"],
                    "monetization_proof": contract["monetization_proof"],
                },
            )
            store.record_transition(
                project_id=contract["project_id"],
                from_state="validated",
                to_state="scored",
                status="success",
                reason=f"Scored {total_score}/10.",
                run_id=args.workflow_run_id,
                run_attempt=args.workflow_run_attempt,
                workflow_url=args.workflow_url,
                timestamp_utc=args.timestamp_utc,
                metadata={"score": total_score, "score_breakdown": score_breakdown},
            )
            store.record_transition(
                project_id=contract["project_id"],
                from_state="scored",
                to_state="approved" if decision == "APPROVE" else ("hold" if decision == "HOLD" else "rejected"),
                status="success" if decision == "APPROVE" else "failed",
                reason=reason,
                run_id=args.workflow_run_id,
                run_attempt=args.workflow_run_attempt,
                workflow_url=args.workflow_url,
                timestamp_utc=args.timestamp_utc,
                metadata={"decision": decision, "score": total_score},
                decision=decision,
                score=float(total_score),
                run_mode=args.run_mode,
                failure_reason="" if decision == "APPROVE" else reason,
                error_summary="" if decision == "APPROVE" else reason,
            )
        except StageTransitionError as exc:
            raise BusinessGateError(f"Failed to persist gate transitions: {exc}") from exc
        finally:
            store.close()

        log_event(
            project_id=contract["project_id"],
            step=STEP_NAME,
            status="success",
            mode=args.run_mode,
            decision=decision,
            score=total_score,
        )
    except (BusinessGateError, ScoringError) as exc:
        error_message = str(exc)
        maybe_write_result(
            args.result_file,
            {
                "decision": "REJECT",
                "score": 0,
                "reason": error_message,
                "validation_summary": {
                    "demand_level": "UNKNOWN",
                    "monetization_proof": "UNKNOWN",
                    "saturation": "UNKNOWN",
                    "differentiation": "UNKNOWN",
                },
                "project_id": project_for_log,
                "run_id": args.workflow_run_id,
                "run_attempt": args.workflow_run_attempt,
                "workflow_url": args.workflow_url,
                "timestamp_utc": args.timestamp_utc,
            },
        )
        log_event(
            project_id=project_for_log,
            step=STEP_NAME,
            status="failed",
            mode=args.run_mode,
            error=error_message,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
