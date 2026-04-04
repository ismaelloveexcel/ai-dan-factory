#!/usr/bin/env python3
"""
Normalize and validate factory-build workflow_dispatch input contract.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from factory_utils import log_event, maybe_write_result, write_json

STEP_NAME = "normalize_inputs"
PROJECT_SLUG_REGEX = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off", ""}


class InputContractError(Exception):
    pass


def parse_bool(name: str, raw_value: str) -> bool:
    value = (raw_value or "").strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise InputContractError(
        f"Invalid boolean-like value for '{name}': '{raw_value}'. "
        "Allowed: true/false/1/0/yes/no/on/off."
    )


def normalize_contract(args: argparse.Namespace) -> dict[str, object]:
    project_id = args.project_id.strip().lower()
    if not PROJECT_SLUG_REGEX.fullmatch(project_id):
        raise InputContractError(
            "Input 'project_id' must be a safe slug using lowercase letters, numbers, and hyphens."
        )

    dry_run_requested = parse_bool("dry_run", args.dry_run)
    tests_only_requested = parse_bool("run_automated_tests_only", args.run_automated_tests_only)
    deprecated_test_mode_requested = parse_bool("test_mode", args.test_mode)

    # Backward compatibility: test_mode=true acts like tests-only mode.
    tests_only_effective = tests_only_requested or deprecated_test_mode_requested
    dry_run_effective = dry_run_requested or tests_only_effective
    run_mode = "tests_only" if tests_only_effective else ("dry_run" if dry_run_effective else "production")

    build_brief_json = args.build_brief_json or ""
    if run_mode != "tests_only" and not build_brief_json.strip():
        raise InputContractError(
            "Input contract violation: 'build_brief_json' is required when run_automated_tests_only=false."
        )

    return {
        "project_id": project_id,
        "run_mode": run_mode,
        "dry_run_requested": dry_run_requested,
        "dry_run_effective": dry_run_effective,
        "run_automated_tests_only_requested": tests_only_requested,
        "run_automated_tests_only_effective": tests_only_effective,
        "deprecated_test_mode_requested": deprecated_test_mode_requested,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize factory-build workflow inputs")
    parser.add_argument("--project-id", required=True, help="Workflow project_id input")
    parser.add_argument("--build-brief-json", default="", help="Workflow build_brief_json input")
    parser.add_argument("--dry-run", required=True, help="Workflow dry_run input")
    parser.add_argument(
        "--run-automated-tests-only",
        default="false",
        help="Workflow run_automated_tests_only input",
    )
    parser.add_argument(
        "--test-mode",
        default="false",
        help="Deprecated alias for run_automated_tests_only",
    )
    parser.add_argument("--normalized-output", required=True, help="Path to write normalized contract JSON")
    parser.add_argument("--result-file", default="", help="Path to write step result JSON")
    args = parser.parse_args()

    project_for_log = args.project_id.strip().lower() or "unknown"
    log_event(project_id=project_for_log, step=STEP_NAME, status="started", mode="contract_validation")
    try:
        normalized = normalize_contract(args)
        write_json(
            path=Path(args.normalized_output).expanduser().resolve(),
            payload=normalized,
        )

        result_payload = {
            "project_id": normalized["project_id"],
            "step": STEP_NAME,
            "status": "success",
            "mode": "contract_validation",
            "run_mode": normalized["run_mode"],
            "run_automated_tests_only_effective": normalized["run_automated_tests_only_effective"],
            "dry_run_effective": normalized["dry_run_effective"],
            "deprecated_test_mode_requested": normalized["deprecated_test_mode_requested"],
            "normalized_output": args.normalized_output,
        }
        maybe_write_result(args.result_file, result_payload)
        log_event(
            project_id=str(normalized["project_id"]),
            step=STEP_NAME,
            status="success",
            mode="contract_validation",
            run_mode=str(normalized["run_mode"]),
            run_automated_tests_only_effective=normalized["run_automated_tests_only_effective"],
            dry_run_effective=normalized["dry_run_effective"],
            deprecated_test_mode_requested=normalized["deprecated_test_mode_requested"],
        )
    except InputContractError as exc:
        error_message = str(exc)
        maybe_write_result(
            args.result_file,
            {
                "project_id": project_for_log,
                "step": STEP_NAME,
                "status": "failed",
                "mode": "contract_validation",
                "error": error_message,
            },
        )
        log_event(
            project_id=project_for_log,
            step=STEP_NAME,
            status="failed",
            mode="contract_validation",
            error=error_message,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
