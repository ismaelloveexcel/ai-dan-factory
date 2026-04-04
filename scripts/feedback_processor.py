#!/usr/bin/env python3
"""
Process and store user feedback signals.

Reads feedback entries, aggregates by type, generates pricing/offer
improvement signals, and writes structured output to feedback_log.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result, utc_timestamp, write_json

STEP_NAME = "feedback_processor"
VALID_FEEDBACK_TYPES = ("too_expensive", "not_clear", "not_needed", "other")


class FeedbackProcessingError(Exception):
    pass


def _load_feedback_log(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return list(data.get("entries", []))
    if isinstance(data, list):
        return data
    return []


def validate_feedback_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a single feedback entry."""
    feedback_type = str(entry.get("feedback_type", "")).strip().lower()
    if feedback_type not in VALID_FEEDBACK_TYPES:
        raise FeedbackProcessingError(
            f"Invalid feedback_type '{feedback_type}'. Must be one of: {', '.join(VALID_FEEDBACK_TYPES)}"
        )
    project_id = str(entry.get("project_id", "")).strip()
    if not project_id:
        raise FeedbackProcessingError("Feedback entry missing 'project_id'.")
    return {
        "feedback_type": feedback_type,
        "project_id": project_id,
        "timestamp": str(entry.get("timestamp", "")).strip() or utc_timestamp(),
        "metadata": entry.get("metadata", {}),
    }


def aggregate_feedback(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Count feedback entries by type."""
    counts: dict[str, int] = {ft: 0 for ft in VALID_FEEDBACK_TYPES}
    for entry in entries:
        ft = entry.get("feedback_type", "")
        if ft in counts:
            counts[ft] += 1
    return counts


def derive_signals(aggregation: dict[str, int], total: int) -> dict[str, Any]:
    """Derive pricing and offer improvement signals from feedback aggregation."""
    signals: dict[str, Any] = {
        "pricing_adjustment": "none",
        "clarity_improvement": False,
        "demand_concern": False,
        "total_feedback": total,
    }
    if total == 0:
        return signals

    too_expensive_ratio = aggregation.get("too_expensive", 0) / total
    not_clear_ratio = aggregation.get("not_clear", 0) / total
    not_needed_ratio = aggregation.get("not_needed", 0) / total

    if too_expensive_ratio >= 0.4:
        signals["pricing_adjustment"] = "reduce"
    elif too_expensive_ratio >= 0.2:
        signals["pricing_adjustment"] = "review"

    if not_clear_ratio >= 0.3:
        signals["clarity_improvement"] = True

    if not_needed_ratio >= 0.4:
        signals["demand_concern"] = True

    return signals


def process_feedback(
    *,
    new_entries: list[dict[str, Any]],
    existing_log_path: Path | None = None,
) -> dict[str, Any]:
    """Process new feedback entries and merge with existing log."""
    existing_entries = _load_feedback_log(existing_log_path) if existing_log_path else []
    validated_new: list[dict[str, Any]] = []
    for entry in new_entries:
        validated_new.append(validate_feedback_entry(entry))

    all_entries = existing_entries + validated_new
    aggregation = aggregate_feedback(all_entries)
    total = sum(aggregation.values())
    signals = derive_signals(aggregation, total)

    return {
        "entries": all_entries,
        "aggregation": aggregation,
        "signals": signals,
        "updated_at": utc_timestamp(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Process and store user feedback signals")
    parser.add_argument("--feedback-file", default="", help="Path to incoming feedback JSON (array of entries)")
    parser.add_argument("--feedback-json", default="", help="Inline feedback JSON string (array of entries)")
    parser.add_argument("--log-file", required=True, help="Path to feedback_log.json (read + write)")
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    parser.add_argument("--project-id", default="", help="Project identifier for logging")
    args = parser.parse_args()

    project_id = args.project_id.strip() or "unknown"
    log_event(project_id=project_id, step=STEP_NAME, status="started", mode="production")

    try:
        new_entries: list[dict[str, Any]] = []
        if args.feedback_file:
            feedback_path = Path(args.feedback_file).expanduser().resolve()
            if not feedback_path.is_file():
                raise FeedbackProcessingError(f"Feedback file not found: {feedback_path}")
            raw = json.loads(feedback_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                new_entries = raw
            elif isinstance(raw, dict):
                new_entries = [raw]
            else:
                raise FeedbackProcessingError("Feedback file must contain a JSON array or object.")
        elif args.feedback_json:
            raw = json.loads(args.feedback_json)
            if isinstance(raw, list):
                new_entries = raw
            elif isinstance(raw, dict):
                new_entries = [raw]
            else:
                raise FeedbackProcessingError("Feedback JSON must be an array or object.")

        log_path = Path(args.log_file).expanduser().resolve()
        result = process_feedback(
            new_entries=new_entries,
            existing_log_path=log_path if log_path.is_file() else None,
        )
        write_json(log_path, result)

        result_payload = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "entries_processed": len(new_entries),
            "total_entries": len(result["entries"]),
            "signals": result["signals"],
        }
        maybe_write_result(args.result_file, result_payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode="production",
            entries_processed=len(new_entries),
            total_entries=len(result["entries"]),
        )
        print(json.dumps(result_payload, ensure_ascii=True))
    except (FeedbackProcessingError, json.JSONDecodeError) as exc:
        error_message = str(exc)
        maybe_write_result(
            args.result_file,
            {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "failed",
                "error": error_message,
            },
        )
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="failed",
            mode="production",
            error=error_message,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
