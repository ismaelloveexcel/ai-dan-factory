#!/usr/bin/env python3
"""
Idea source engine: select a deterministic brief from an idea pool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from factory_utils import maybe_write_result
from factory_run_contract import BUILD_BRIEF_V1_REQUIRED_FIELDS

REQUIRED_FIELDS = BUILD_BRIEF_V1_REQUIRED_FIELDS


class IdeaSourceError(Exception):
    pass


def load_ideas(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise IdeaSourceError(f"Ideas file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IdeaSourceError(f"Ideas JSON is invalid: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise IdeaSourceError("Ideas file must contain a non-empty array.")

    ideas: list[dict[str, Any]] = []
    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            raise IdeaSourceError(f"Idea index {idx} must be a JSON object.")
        missing = [field for field in REQUIRED_FIELDS if not isinstance(item.get(field), str) or not str(item[field]).strip()]
        if missing:
            raise IdeaSourceError(f"Idea index {idx} missing required fields: {', '.join(missing)}")
        ideas.append(item)
    return ideas


def choose_index(total: int, seed: str, forced_index: int | None) -> int:
    if total <= 0:
        raise IdeaSourceError("No ideas available for selection.")
    if forced_index is not None:
        return forced_index % total
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    value = int(digest[:12], 16)
    return value % total


def main() -> None:
    parser = argparse.ArgumentParser(description="Select deterministic idea payload from pool")
    parser.add_argument("--ideas-file", required=True, help="Path to JSON array of candidate briefs")
    parser.add_argument("--selected-brief-file", required=True, help="Path to write selected brief JSON")
    parser.add_argument("--result-file", default="", help="Optional result JSON path")
    parser.add_argument("--selection-seed", default="", help="Deterministic seed (defaults to run id + attempt)")
    parser.add_argument("--run-id", default="", help="Workflow run id used in seed")
    parser.add_argument("--run-attempt", default="", help="Workflow run attempt used in seed")
    parser.add_argument("--index", type=int, default=None, help="Force selection index (for deterministic tests)")
    args = parser.parse_args()

    try:
        ideas = load_ideas(Path(args.ideas_file).expanduser().resolve())
        seed = args.selection_seed.strip()
        if not seed:
            seed = f"{args.run_id.strip()}:{args.run_attempt.strip()}".strip(":")
        if not seed:
            seed = "0"
        selected_index = choose_index(len(ideas), seed, args.index)
        selected = ideas[selected_index]

        output_path = Path(args.selected_brief_file).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(selected, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

        payload = {
            "status": "success",
            "selected_index": selected_index,
            "total_ideas": len(ideas),
            "selection_seed": seed,
            "selected_project_id": str(selected.get("project_id", "")).strip().lower(),
            "selected_brief_file": str(output_path),
        }
        maybe_write_result(args.result_file, payload)
        print(json.dumps(payload, ensure_ascii=True))
    except IdeaSourceError as exc:
        payload = {
            "status": "failed",
            "error": str(exc),
            "selected_index": -1,
            "total_ideas": 0,
            "selection_seed": "",
            "selected_project_id": "",
            "selected_brief_file": "",
        }
        maybe_write_result(args.result_file, payload)
        print(json.dumps(payload, ensure_ascii=True))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
