#!/usr/bin/env python3
"""
Emit deterministic alert payloads for factory failures.
"""

from __future__ import annotations

import argparse
import json

from factory_utils import maybe_write_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit structured alert payload")
    parser.add_argument("--project-id", required=True, help="Project id")
    parser.add_argument("--run-id", required=True, help="Workflow run id")
    parser.add_argument("--run-attempt", required=True, help="Workflow run attempt")
    parser.add_argument("--workflow-url", required=True, help="Workflow URL")
    parser.add_argument("--failure-reason", required=True, help="Concise failure reason")
    parser.add_argument("--error-summary", required=True, help="Expanded error summary")
    parser.add_argument("--result-file", required=True, help="Path for alert payload JSON")
    args = parser.parse_args()

    payload = {
        "project_id": args.project_id.strip().lower(),
        "run_id": args.run_id.strip(),
        "run_attempt": args.run_attempt.strip(),
        "workflow_url": args.workflow_url.strip(),
        "alert_type": "factory_failure",
        "failure_reason": args.failure_reason.strip(),
        "error_summary": args.error_summary.strip(),
    }
    maybe_write_result(args.result_file, payload)
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
