#!/usr/bin/env python3
"""
Produce simplified portfolio summary buckets: IGNORE / WATCH / SCALE.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from state_store import StateStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate simplified portfolio summary")
    parser.add_argument("--state-db", required=True, help="Path to lifecycle SQLite database")
    parser.add_argument("--result-file", required=True, help="Path to write portfolio summary JSON")
    parser.add_argument(
        "--max-items-per-category",
        type=int,
        default=5,
        help="Maximum number of projects per IGNORE/WATCH/SCALE bucket",
    )
    args = parser.parse_args()

    max_per_category = max(1, int(args.max_items_per_category))
    store = StateStore(args.state_db)
    signals = store.list_monitoring_signals(limit=1000)

    buckets = {"IGNORE": [], "WATCH": [], "SCALE": []}

    for item in signals:
        decision = str(item.get("portfolio_decision", "")).upper()
        project_entry = {
            "project_id": item.get("project_id", ""),
            "run_id": item.get("run_id", ""),
            "run_attempt": item.get("run_attempt", ""),
            "traffic_signal": item.get("traffic_signal", ""),
            "activation_metric": item.get("activation_metric", ""),
            "revenue_signal_status": item.get("revenue_signal_status", ""),
        }
        if decision == "KILL_CANDIDATE":
            if len(buckets["IGNORE"]) < max_per_category:
                buckets["IGNORE"].append(project_entry)
        elif decision == "OPTIMIZE_CANDIDATE":
            if len(buckets["WATCH"]) < max_per_category:
                buckets["WATCH"].append(project_entry)
        elif decision == "SCALE_CANDIDATE":
            if len(buckets["SCALE"]) < max_per_category:
                buckets["SCALE"].append(project_entry)

    payload = {
        "IGNORE": buckets["IGNORE"],
        "WATCH": buckets["WATCH"],
        "SCALE": buckets["SCALE"],
        "max_items_per_category": max_per_category,
    }

    output_path = Path(args.result_file).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
