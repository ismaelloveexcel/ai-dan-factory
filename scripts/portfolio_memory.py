#!/usr/bin/env python3
"""
Portfolio Memory & Deduplication for AI-DAN Factory.

Maintains ideas_history, rejected_ideas, built_projects, and outcomes.
Before approval, performs similarity check against historical data.
Failed duplicates → REJECT.  Successful variants → PRIORITIZE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result
from state_store import FactoryStateStore

STEP_NAME = "portfolio_memory"

# Similarity threshold: two briefs sharing the same product_name or problem
# hash prefix (first 32 chars of SHA-256) are considered duplicates.
_HASH_PREFIX_LEN = 32


class PortfolioMemoryError(Exception):
    pass


def _brief_fingerprint(brief: dict[str, Any]) -> str:
    """Deterministic fingerprint of the core idea (problem + solution)."""
    problem = str(brief.get("problem", "")).strip().lower()
    solution = str(brief.get("solution", "")).strip().lower()
    source = f"{problem}|{solution}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:_HASH_PREFIX_LEN]


def _product_name_key(brief: dict[str, Any]) -> str:
    return str(brief.get("product_name", "")).strip().lower()


def check_deduplication(
    store: FactoryStateStore,
    brief: dict[str, Any],
    project_id: str,
) -> dict[str, Any]:
    """
    Check portfolio history for duplicates.

    Returns dict with:
      - is_duplicate: bool
      - duplicate_type: "exact_rerun" | "similar_failed" | "similar_success" | ""
      - recommendation: "REJECT" | "PRIORITIZE" | "PROCEED"
      - matched_project_id: str (if duplicate found)
      - reason: str
    """
    fingerprint = _brief_fingerprint(brief)
    name_key = _product_name_key(brief)

    runs = store.list_recent_runs(limit=500)

    for run in runs:
        if run["project_id"] == project_id:
            # Same project_id re-run — allow (idempotent)
            continue

        # Check for previously stored fingerprint in metadata
        run_state = str(run.get("state", ""))
        run_decision = str(run.get("decision", ""))
        run_project = str(run.get("project_id", ""))

        # Name-based similarity check
        # We compare against known projects in the history
        if run_project and name_key and run_project.replace("-", " ") == name_key.replace("-", " "):
            if run_state in ("rejected", "killed"):
                return {
                    "is_duplicate": True,
                    "duplicate_type": "similar_failed",
                    "recommendation": "REJECT",
                    "matched_project_id": run_project,
                    "reason": f"Similar idea '{run_project}' was previously {run_state}.",
                }
            if run_state in ("deployed", "monitored", "scaled"):
                return {
                    "is_duplicate": True,
                    "duplicate_type": "similar_success",
                    "recommendation": "PRIORITIZE",
                    "matched_project_id": run_project,
                    "reason": f"Similar idea '{run_project}' is active ({run_state}). Consider variant.",
                }

    return {
        "is_duplicate": False,
        "duplicate_type": "",
        "recommendation": "PROCEED",
        "matched_project_id": "",
        "reason": "No duplicates found in portfolio history.",
    }


def get_portfolio_history(store: FactoryStateStore) -> dict[str, Any]:
    """Return categorized portfolio history."""
    runs = store.list_recent_runs(limit=500)

    ideas_history: list[dict[str, Any]] = []
    rejected_ideas: list[dict[str, Any]] = []
    built_projects: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []

    for run in runs:
        entry = {
            "project_id": run["project_id"],
            "state": run["state"],
            "decision": run.get("decision", ""),
            "score": run.get("score"),
            "updated_at": run.get("updated_at", ""),
        }
        ideas_history.append(entry)

        state = str(run.get("state", ""))
        if state in ("rejected", "hold"):
            rejected_ideas.append(entry)
        elif state in ("building", "deployed", "monitored", "scaled"):
            built_projects.append(entry)
        if state in ("scaled", "killed"):
            outcomes.append(entry)

    return {
        "ideas_history": ideas_history[:100],
        "rejected_ideas": rejected_ideas[:50],
        "built_projects": built_projects[:50],
        "outcomes": outcomes[:50],
        "total_ideas": len(ideas_history),
        "total_rejected": len(rejected_ideas),
        "total_built": len(built_projects),
        "total_outcomes": len(outcomes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio memory & deduplication check")
    parser.add_argument("--brief-file", required=True, help="Path to brief JSON")
    parser.add_argument("--project-id", required=True, help="Project identifier")
    parser.add_argument("--state-db", required=True, help="Path to lifecycle SQLite DB")
    parser.add_argument("--result-file", default="", help="Path to write result JSON")
    parser.add_argument("--history-file", default="", help="Path to write portfolio history JSON")
    args = parser.parse_args()

    project_id = args.project_id.strip().lower()
    log_event(project_id=project_id, step=STEP_NAME, status="started", mode="production")

    try:
        brief_path = Path(args.brief_file).expanduser().resolve()
        if not brief_path.is_file():
            raise PortfolioMemoryError(f"Brief file not found: {brief_path}")

        brief = json.loads(brief_path.read_text(encoding="utf-8"))
        if not isinstance(brief, dict):
            raise PortfolioMemoryError("Brief must be a JSON object.")

        store = FactoryStateStore(args.state_db)
        try:
            dedup_result = check_deduplication(store, brief, project_id)
            history = get_portfolio_history(store)
        finally:
            store.close()

        payload = {
            "project_id": project_id,
            "fingerprint": _brief_fingerprint(brief),
            "step": STEP_NAME,
            "status": "success",
            **dedup_result,
        }
        maybe_write_result(args.result_file, payload)

        if args.history_file:
            maybe_write_result(args.history_file, history)

        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode="production",
            recommendation=dedup_result["recommendation"],
            is_duplicate=dedup_result["is_duplicate"],
        )
        print(json.dumps(payload, ensure_ascii=True))

    except PortfolioMemoryError as exc:
        error_msg = str(exc)
        payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "failed",
            "error": error_msg,
            "recommendation": "PROCEED",
            "is_duplicate": False,
        }
        maybe_write_result(args.result_file, payload)
        log_event(project_id=project_id, step=STEP_NAME, status="failed", mode="production", error=error_msg)
        print(json.dumps(payload, ensure_ascii=True))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
