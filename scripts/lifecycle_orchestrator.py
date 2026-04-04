#!/usr/bin/env python3
"""
Strict lifecycle orchestrator for AI-DAN factory state transitions.
"""

from __future__ import annotations

import argparse
import json

from state_store import FactoryStateStore, StageTransitionError


def parse_metadata(raw: str) -> dict[str, object]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[error] Invalid metadata JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("[error] metadata-json must be a JSON object")
    return data


def transition_status(to_state: str) -> str:
    return "failed" if to_state in {"rejected", "hold", "killed"} else "success"


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce strict lifecycle transitions")
    parser.add_argument("--state-db", required=True, help="Path to lifecycle SQLite database")
    parser.add_argument("--project-id", required=True, help="Project identifier")
    parser.add_argument("--run-id", required=True, help="Workflow run id")
    parser.add_argument("--run-attempt", required=True, help="Workflow run attempt")
    parser.add_argument("--to-state", required=True, help="Target state")
    parser.add_argument("--reason", default="", help="Transition reason")
    parser.add_argument("--workflow-url", default="", help="Workflow URL")
    parser.add_argument("--timestamp-utc", required=True, help="UTC timestamp")
    parser.add_argument("--metadata-json", default="{}", help="Optional metadata JSON")
    args = parser.parse_args()

    project_id = args.project_id.strip().lower()
    run_id = args.run_id.strip()
    run_attempt = args.run_attempt.strip()
    to_state = args.to_state.strip().lower()
    timestamp_utc = args.timestamp_utc.strip()
    reason = args.reason.strip() or f"Transitioned to {to_state}"
    metadata = parse_metadata(args.metadata_json)

    if not project_id or not run_id or not run_attempt or not to_state or not timestamp_utc:
        raise SystemExit("[error] project-id, run-id, run-attempt, to-state, timestamp-utc are required")

    store = FactoryStateStore(args.state_db)
    current = store.get_run(run_id, run_attempt)
    if current is None:
        if to_state != "idea":
            raise SystemExit("[error] First lifecycle state for a run must be 'idea'")
        try:
            store.initialize_run(
                run_id=run_id,
                run_attempt=run_attempt,
                project_id=project_id,
                initial_state="idea",
                workflow_url=args.workflow_url.strip(),
            )
        except StageTransitionError as exc:
            raise SystemExit(f"[error] {exc}") from exc
        print(
            json.dumps(
                {
                    "project_id": project_id,
                    "run_id": run_id,
                    "run_attempt": run_attempt,
                    "from_state": "idea",
                    "to_state": "idea",
                    "status": "success",
                    "timestamp_utc": timestamp_utc,
                },
                ensure_ascii=True,
            )
        )
        return

    from_state = str(current["state"]).strip().lower()
    try:
        store.record_transition(
            project_id=project_id,
            from_state=from_state,
            to_state=to_state,
            status=transition_status(to_state),
            reason=reason,
            run_id=run_id,
            run_attempt=run_attempt,
            workflow_url=args.workflow_url.strip(),
            timestamp_utc=timestamp_utc,
            metadata=metadata,
        )
    except StageTransitionError as exc:
        raise SystemExit(f"[error] {exc}") from exc

    print(
        json.dumps(
            {
                "project_id": project_id,
                "run_id": run_id,
                "run_attempt": run_attempt,
                "from_state": from_state,
                "to_state": to_state,
                "status": "success",
                "timestamp_utc": timestamp_utc,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
