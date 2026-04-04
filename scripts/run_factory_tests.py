#!/usr/bin/env python3
"""
Automated non-destructive test suite for ai-dan-factory.

This script validates:
- script syntax
- happy-path dry-run execution across all factory steps
- unified business gate behavior
- lifecycle state transitions
- monitoring/portfolio outputs
- key failure guards (validation errors, missing secrets, project mismatch)

No external side effects are performed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "templates" / "saas-template"
LIVE_TEST_BRIEF = ROOT / "test_data" / "live_test_brief.json"
AIDAN_DRY_RUN_BRIEF = ROOT / "test_data" / "aidan_dry_run_brief.json"
AIDAN_LIVE_BRIEF = ROOT / "test_data" / "aidan_live_brief.json"
AUTONOMOUS_IDEAS = ROOT / "test_data" / "autonomous_ideas.json"


class TestFailure(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(
    args: Iterable[str],
    *,
    expect_success: bool,
    env_overrides: dict[str, str | None] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overrides:
        for key, value in env_overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value

    result = subprocess.run(
        list(args),
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )
    command_str = " ".join(args)
    print(f"\n$ {command_str}")
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)

    if expect_success and result.returncode != 0:
        raise TestFailure(f"Command failed unexpectedly ({result.returncode}): {command_str}")
    if not expect_success and result.returncode == 0:
        raise TestFailure(f"Command unexpectedly succeeded: {command_str}")
    return result


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise TestFailure(f"Expected JSON file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TestFailure(f"Invalid JSON file at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TestFailure(f"JSON file must contain an object: {path}")
    return data


def compile_check() -> None:
    print("==> [1/10] Running script syntax checks")
    scripts = [
        "scripts/factory_utils.py",
        "scripts/idea_source_engine.py",
        "scripts/state_store.py",
        "scripts/lifecycle_orchestrator.py",
        "scripts/scoring_engine.py",
        "scripts/validate_business_gate.py",
        "scripts/business_output_engine.py",
        "scripts/deploy_health_check.py",
        "scripts/emit_alert.py",
        "scripts/monitor_and_decide.py",
        "scripts/portfolio_summary.py",
        "scripts/normalize_workflow_inputs.py",
        "scripts/validate_brief.py",
        "scripts/create_project.py",
        "scripts/inject_brief.py",
        "scripts/deploy.py",
        "scripts/portfolio_memory.py",
        "scripts/revenue_loop.py",
        "scripts/monetization_filter.py",
        "scripts/run_factory_tests.py",
    ]
    run_command([sys.executable, "-m", "py_compile", *scripts], expect_success=True)


def payload_schema_check() -> None:
    print("==> [2/10] Validating test payload schemas")
    payloads = [LIVE_TEST_BRIEF, AIDAN_DRY_RUN_BRIEF, AIDAN_LIVE_BRIEF]
    required = (
        "project_id",
        "product_name",
        "problem",
        "solution",
        "cta",
        "source_type",
        "reference_context",
        "demand_level",
        "monetization_proof",
        "market_saturation",
        "differentiation",
    )
    for payload_path in payloads:
        payload = read_json(payload_path)
        for field in required:
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip():
                raise TestFailure(f"{payload_path.name} field '{field}' must be a non-empty string.")

    ideas = json.loads(AUTONOMOUS_IDEAS.read_text(encoding="utf-8"))
    if not isinstance(ideas, list) or not ideas:
        raise TestFailure("autonomous_ideas.json must contain a non-empty array")
    for idx, idea in enumerate(ideas):
        if not isinstance(idea, dict):
            raise TestFailure(f"autonomous_ideas.json entry {idx} must be an object")
        for field in required:
            value = idea.get(field)
            if not isinstance(value, str) or not value.strip():
                raise TestFailure(f"autonomous_ideas.json entry {idx} field '{field}' must be a non-empty string.")


def idea_source_and_scoring_tests() -> None:
    print("==> [3/10] Running idea source + scoring tests")
    with tempfile.TemporaryDirectory(prefix="factory-idea-source-") as tmp_dir:
        tmp = Path(tmp_dir)
        selected = tmp / "selected.json"
        source_result = tmp / "source_result.json"
        score_result = tmp / "score_result.json"

        run_command(
            [
                sys.executable,
                "scripts/idea_source_engine.py",
                "--ideas-file",
                str(AUTONOMOUS_IDEAS),
                "--selected-brief-file",
                str(selected),
                "--result-file",
                str(source_result),
                "--selection-seed",
                "test-seed",
            ],
            expect_success=True,
        )
        selected_brief = read_json(selected)
        if not str(selected_brief.get("project_id", "")).strip():
            raise TestFailure("idea_source_engine selected brief must include project_id")

        run_command(
            [
                sys.executable,
                "scripts/scoring_engine.py",
                "--brief-file",
                str(selected),
                "--result-file",
                str(score_result),
            ],
            expect_success=True,
        )
        score_payload = read_json(score_result)
        decision = str(score_payload.get("decision", ""))
        if decision not in {"APPROVE", "HOLD", "REJECT"}:
            raise TestFailure("scoring_engine decision must be APPROVE/HOLD/REJECT")
        score_value = int(score_payload.get("score", 0))
        if score_value < 0 or score_value > 10:
            raise TestFailure("scoring_engine score must be between 0 and 10")


def business_gate_and_lifecycle_tests() -> None:
    print("==> [4/10] Running business gate + lifecycle state tests")
    with tempfile.TemporaryDirectory(prefix="factory-gate-") as tmp_dir:
        tmp = Path(tmp_dir)
        state_db = tmp / "state.sqlite"
        gate_result = tmp / "gate.json"
        run_id = "test-run-1"
        run_attempt = "1"
        workflow_url = "https://github.com/example/actions/runs/1"
        timestamp = utc_now()

        run_command(
            [
                sys.executable,
                "scripts/lifecycle_orchestrator.py",
                "--state-db",
                str(state_db),
                "--project-id",
                "aidan-live-001",
                "--run-id",
                run_id,
                "--run-attempt",
                run_attempt,
                "--to-state",
                "idea",
                "--reason",
                "seed idea",
                "--timestamp-utc",
                utc_now(),
            ],
            expect_success=True,
        )

        run_command(
            [
                sys.executable,
                "scripts/validate_business_gate.py",
                "--brief-file",
                str(AIDAN_LIVE_BRIEF),
                "--result-file",
                str(gate_result),
                "--state-db",
                str(state_db),
                "--workflow-run-id",
                run_id,
                "--workflow-run-attempt",
                run_attempt,
                "--workflow-url",
                workflow_url,
                "--timestamp-utc",
                timestamp,
            ],
            expect_success=True,
        )
        gate = read_json(gate_result)
        if gate.get("decision") != "APPROVE":
            raise TestFailure("Expected APPROVE decision for aidan_live_brief")
        if float(gate.get("score", 0)) < 8:
            raise TestFailure("Expected score >= 8 for aidan_live_brief")

        # Transition progression checks.
        for to_state in ("building", "deployed", "monitored"):
            run_command(
                [
                    sys.executable,
                    "scripts/lifecycle_orchestrator.py",
                    "--state-db",
                    str(state_db),
                    "--project-id",
                    "aidan-live-001",
                    "--run-id",
                    run_id,
                    "--run-attempt",
                    run_attempt,
                    "--to-state",
                    to_state,
                    "--reason",
                    "test progression",
                    "--timestamp-utc",
                    utc_now(),
                ],
                expect_success=True,
            )

        # Illegal transition should fail.
        run_command(
            [
                sys.executable,
                "scripts/lifecycle_orchestrator.py",
                "--state-db",
                str(state_db),
                "--project-id",
                "aidan-live-001",
                "--run-id",
                run_id,
                "--run-attempt",
                run_attempt,
                "--to-state",
                "deployed",
                "--reason",
                "illegal",
                "--timestamp-utc",
                utc_now(),
            ],
            expect_success=False,
        )


def full_dry_run_pipeline() -> None:
    print("==> [5/10] Running happy-path dry-run execution tests")
    with tempfile.TemporaryDirectory(prefix="factory-tests-") as tmp_dir:
        tmp = Path(tmp_dir)
        normalized = tmp / "normalized.json"
        validate_result = tmp / "validate_brief.json"
        create_result = tmp / "create_repo.json"
        inject_result = tmp / "inject_brief.json"
        deploy_result = tmp / "deploy.json"
        business_output = tmp / "business_output.json"
        template_copy = tmp / "template-copy"
        shutil.copytree(TEMPLATE_DIR, template_copy)

        run_command(
            [
                sys.executable,
                "scripts/validate_brief.py",
                "--brief-file",
                str(LIVE_TEST_BRIEF),
                "--expected-project-id",
                "test-001",
                "--normalized-output",
                str(normalized),
                "--result-file",
                str(validate_result),
                "--dry-run",
            ],
            expect_success=True,
        )
        validate_payload = read_json(validate_result)
        if validate_payload.get("status") != "success":
            raise TestFailure("validate_brief did not succeed")
        idempotency_key = str(validate_payload.get("idempotency_key", "")).strip()
        if not idempotency_key:
            raise TestFailure("validate_brief did not emit idempotency_key")

        run_command(
            [
                sys.executable,
                "scripts/business_output_engine.py",
                "--brief-file",
                str(normalized),
                "--output-file",
                str(business_output),
                "--result-file",
                str(tmp / "business_output_result.json"),
            ],
            expect_success=True,
        )
        business = read_json(business_output)
        for field in (
            "headline",
            "CTA",
            "monetization_model",
            "pricing_suggestion",
            "offer_structure",
            "gtm_plan",
            "conversion_hints",
        ):
            if field not in business:
                raise TestFailure(f"business_output missing field '{field}'")

        run_command(
            [
                sys.executable,
                "scripts/create_project.py",
                "--project-id",
                "test-001",
                "--org",
                "example-org",
                "--template-owner",
                "example-owner",
                "--template-repo",
                "example-template",
                "--idempotency-key",
                idempotency_key,
                "--result-file",
                str(create_result),
                "--dry-run",
            ],
            expect_success=True,
        )

        run_command(
            [
                sys.executable,
                "scripts/inject_brief.py",
                "--project-id",
                "test-001",
                "--project-dir",
                str(template_copy),
                "--brief-file",
                str(normalized),
                "--idempotency-key",
                idempotency_key,
                "--result-file",
                str(inject_result),
                "--dry-run",
            ],
            expect_success=True,
        )

        run_command(
            [
                sys.executable,
                "scripts/deploy.py",
                "--project-id",
                "test-001",
                "--idempotency-key",
                idempotency_key,
                "--result-file",
                str(deploy_result),
                "--dry-run",
            ],
            expect_success=True,
        )


def monitoring_and_summary_tests() -> None:
    print("==> [6/10] Running monitor/scale/portfolio tests")
    with tempfile.TemporaryDirectory(prefix="factory-monitor-") as tmp_dir:
        tmp = Path(tmp_dir)
        state_db = tmp / "state.sqlite"
        monitor_result = tmp / "monitor.json"
        summary_file = tmp / "summary.json"

        # Seed run records.
        run_command(
            [
                sys.executable,
                "scripts/lifecycle_orchestrator.py",
                "--state-db",
                str(state_db),
                "--project-id",
                "proj-scale",
                "--run-id",
                "run-scale",
                "--run-attempt",
                "1",
                "--to-state",
                "idea",
                "--reason",
                "seed",
                "--timestamp-utc",
                utc_now(),
            ],
            expect_success=True,
        )
        for to_state in ("validated", "scored", "approved", "building", "deployed", "monitored"):
            run_command(
                [
                    sys.executable,
                    "scripts/lifecycle_orchestrator.py",
                    "--state-db",
                    str(state_db),
                    "--project-id",
                    "proj-scale",
                    "--run-id",
                    "run-scale",
                    "--run-attempt",
                    "1",
                    "--to-state",
                    to_state,
                    "--reason",
                    "seed",
                    "--timestamp-utc",
                    utc_now(),
                ],
                expect_success=True,
            )

        run_command(
            [
                sys.executable,
                "scripts/monitor_and_decide.py",
                "--state-db",
                str(state_db),
                "--run-id",
                "run-scale",
                "--run-attempt",
                "1",
                "--project-id",
                "proj-scale",
                "--traffic-signal",
                "HIGH",
                "--activation-metric",
                "HIGH",
                "--revenue-signal-status",
                "STRONG",
                "--result-file",
                str(monitor_result),
            ],
            expect_success=True,
        )
        monitor = read_json(monitor_result)
        if monitor.get("scale_candidate") is not True:
            raise TestFailure("Expected scale_candidate=true for HIGH/HIGH/STRONG")

        run_command(
            [
                sys.executable,
                "scripts/portfolio_summary.py",
                "--state-db",
                str(state_db),
                "--result-file",
                str(summary_file),
            ],
            expect_success=True,
        )
        summary = read_json(summary_file)
        for category in ("IGNORE", "WATCH", "SCALE"):
            items = summary.get(category)
            if not isinstance(items, list):
                raise TestFailure(f"portfolio summary category '{category}' missing list")
            if len(items) > 5:
                raise TestFailure(f"portfolio summary category '{category}' exceeds 5 items")


def negative_guard_tests() -> None:
    print("==> [7/10] Running negative guard tests")
    with tempfile.TemporaryDirectory(prefix="factory-tests-negative-") as tmp_dir:
        tmp = Path(tmp_dir)
        invalid_brief = tmp / "invalid_brief.json"
        invalid_brief.write_text(
            json.dumps(
                {
                    "project_id": "BAD-SLUG",
                    "product_name": "x",
                    "problem": "short",
                    "solution": "short",
                    "cta": "go",
                }
            ),
            encoding="utf-8",
        )

        run_command(
            [
                sys.executable,
                "scripts/validate_brief.py",
                "--brief-file",
                str(invalid_brief),
                "--expected-project-id",
                "bad-slug",
                "--normalized-output",
                str(tmp / "normalized.json"),
                "--result-file",
                str(tmp / "validate_failed.json"),
                "--dry-run",
            ],
            expect_success=False,
        )

        # Business gate should reject LOW demand.
        reject_brief = tmp / "reject_gate.json"
        reject_brief.write_text(
            json.dumps(
                {
                    "project_id": "reject-me-001",
                    "source_type": "TREND",
                    "reference_context": "sample source",
                    "demand_level": "LOW",
                    "monetization_proof": "YES",
                    "market_saturation": "LOW",
                    "differentiation": "STRONG",
                    "build_complexity": "LOW",
                    "speed_to_revenue": "FAST",
                }
            ),
            encoding="utf-8",
        )
        run_command(
            [
                sys.executable,
                "scripts/validate_business_gate.py",
                "--brief-file",
                str(reject_brief),
                "--result-file",
                str(tmp / "gate_reject.json"),
                "--state-db",
                str(tmp / "state.sqlite"),
                "--workflow-run-id",
                "run-reject",
                "--workflow-run-attempt",
                "1",
                "--workflow-url",
                "https://example/run-reject",
                "--timestamp-utc",
                utc_now(),
            ],
            expect_success=True,
        )
        gate_payload = read_json(tmp / "gate_reject.json")
        if gate_payload.get("decision") != "REJECT":
            raise TestFailure("Business gate should reject LOW demand.")

        run_command(
            [
                sys.executable,
                "scripts/create_project.py",
                "--project-id",
                "test-001",
                "--org",
                "example-org",
                "--template-owner",
                "example-owner",
                "--template-repo",
                "example-template",
            ],
            expect_success=False,
            env_overrides={"GITHUB_TOKEN": None},
        )

        run_command(
            [
                sys.executable,
                "scripts/deploy.py",
                "--project-id",
                "test-001",
            ],
            expect_success=False,
            env_overrides={"VERCEL_DEPLOY_HOOK_URL": None},
        )

        # Validate inject mismatch guard.
        normalized = tmp / "normalized_valid.json"
        run_command(
            [
                sys.executable,
                "scripts/validate_brief.py",
                "--brief-file",
                str(LIVE_TEST_BRIEF),
                "--expected-project-id",
                "test-001",
                "--normalized-output",
                str(normalized),
                "--dry-run",
            ],
            expect_success=True,
        )
        template_copy = tmp / "template-copy"
        shutil.copytree(TEMPLATE_DIR, template_copy)
        run_command(
            [
                sys.executable,
                "scripts/inject_brief.py",
                "--project-id",
                "different-project",
                "--project-dir",
                str(template_copy),
                "--brief-file",
                str(normalized),
                "--dry-run",
            ],
            expect_success=False,
        )


def portfolio_memory_tests() -> None:
    print("==> [8/10] Running portfolio memory + deduplication tests")
    with tempfile.TemporaryDirectory(prefix="factory-memory-") as tmp_str:
        tmp = Path(tmp_str)
        state_db = str(tmp / "state.sqlite")

        # Test dedup with no history — should PROCEED
        run_command(
            [
                sys.executable,
                "scripts/portfolio_memory.py",
                "--brief-file",
                str(LIVE_TEST_BRIEF),
                "--project-id",
                "test-001",
                "--state-db",
                state_db,
                "--result-file",
                str(tmp / "memory_result.json"),
                "--history-file",
                str(tmp / "history.json"),
            ],
            expect_success=True,
        )
        memory_result = read_json(tmp / "memory_result.json")
        if memory_result.get("recommendation") != "PROCEED":
            raise TestFailure("Portfolio memory should PROCEED with no history.")
        if memory_result.get("is_duplicate") is not False:
            raise TestFailure("Portfolio memory should not find duplicates with empty history.")

        history = read_json(tmp / "history.json")
        if "ideas_history" not in history:
            raise TestFailure("Portfolio history must contain ideas_history key.")
        if "rejected_ideas" not in history:
            raise TestFailure("Portfolio history must contain rejected_ideas key.")


def revenue_loop_tests() -> None:
    print("==> [9/10] Running revenue loop tests")
    with tempfile.TemporaryDirectory(prefix="factory-revenue-") as tmp_str:
        tmp = Path(tmp_str)

        # Test NO_TRACTION → AUTO_KILL
        run_command(
            [
                sys.executable,
                "scripts/revenue_loop.py",
                "--state-db",
                str(tmp / "state.sqlite"),
                "--project-id",
                "rev-test-001",
                "--traffic-signal",
                "LOW",
                "--activation-metric",
                "LOW",
                "--revenue-signal-status",
                "NONE",
                "--result-file",
                str(tmp / "rev_kill.json"),
            ],
            expect_success=True,
        )
        rev_kill = read_json(tmp / "rev_kill.json")
        if rev_kill.get("outcome") != "NO_TRACTION":
            raise TestFailure(f"Expected NO_TRACTION, got {rev_kill.get('outcome')}")
        if rev_kill.get("action") != "AUTO_KILL":
            raise TestFailure(f"Expected AUTO_KILL, got {rev_kill.get('action')}")

        # Test REVENUE_CONFIRMED → SCALE
        run_command(
            [
                sys.executable,
                "scripts/revenue_loop.py",
                "--state-db",
                str(tmp / "state2.sqlite"),
                "--project-id",
                "rev-test-002",
                "--traffic-signal",
                "HIGH",
                "--activation-metric",
                "HIGH",
                "--revenue-signal-status",
                "STRONG",
                "--result-file",
                str(tmp / "rev_scale.json"),
            ],
            expect_success=True,
        )
        rev_scale = read_json(tmp / "rev_scale.json")
        if rev_scale.get("outcome") != "REVENUE_CONFIRMED":
            raise TestFailure(f"Expected REVENUE_CONFIRMED, got {rev_scale.get('outcome')}")
        if rev_scale.get("action") != "SCALE":
            raise TestFailure(f"Expected SCALE, got {rev_scale.get('action')}")

        # Test INTEREST_ONLY → ITERATE
        run_command(
            [
                sys.executable,
                "scripts/revenue_loop.py",
                "--state-db",
                str(tmp / "state3.sqlite"),
                "--project-id",
                "rev-test-003",
                "--traffic-signal",
                "MEDIUM",
                "--activation-metric",
                "MEDIUM",
                "--revenue-signal-status",
                "WEAK",
                "--result-file",
                str(tmp / "rev_iterate.json"),
            ],
            expect_success=True,
        )
        rev_iterate = read_json(tmp / "rev_iterate.json")
        if rev_iterate.get("outcome") != "INTEREST_ONLY":
            raise TestFailure(f"Expected INTEREST_ONLY, got {rev_iterate.get('outcome')}")
        if rev_iterate.get("action") != "ITERATE":
            raise TestFailure(f"Expected ITERATE, got {rev_iterate.get('action')}")


def monetization_filter_tests() -> None:
    print("==> [10/10] Running monetization filter tests")
    with tempfile.TemporaryDirectory(prefix="factory-monet-") as tmp_str:
        tmp = Path(tmp_str)

        # Test with good brief — should pass
        run_command(
            [
                sys.executable,
                "scripts/monetization_filter.py",
                "--brief-file",
                str(LIVE_TEST_BRIEF),
                "--result-file",
                str(tmp / "monet_pass.json"),
            ],
            expect_success=True,
        )
        monet_pass = read_json(tmp / "monet_pass.json")
        if monet_pass.get("pass_filter") is not True:
            raise TestFailure("Monetization filter should pass for test brief with YES monetization.")
        if monet_pass.get("priority") not in ("HIGH", "MEDIUM"):
            raise TestFailure(f"Expected HIGH or MEDIUM priority, got {monet_pass.get('priority')}")

        # Test with no-monetization brief — should fail
        no_monet_brief = tmp / "no_monet.json"
        no_monet_brief.write_text(json.dumps({
            "project_id": "no-monet-001",
            "product_name": "Test No Monet",
            "problem": "Testing no monetization filter",
            "solution": "Just a test solution for filter",
            "cta": "Sign up",
            "source_type": "TREND",
            "reference_context": "Testing monetization filter behavior",
            "demand_level": "MEDIUM",
            "monetization_proof": "NO",
            "market_saturation": "MEDIUM",
            "differentiation": "STRONG",
        }, indent=2), encoding="utf-8")
        run_command(
            [
                sys.executable,
                "scripts/monetization_filter.py",
                "--brief-file",
                str(no_monet_brief),
                "--result-file",
                str(tmp / "monet_fail.json"),
            ],
            expect_success=True,
        )
        monet_fail = read_json(tmp / "monet_fail.json")
        if monet_fail.get("pass_filter") is not False:
            raise TestFailure("Monetization filter should fail for brief with NO monetization proof.")


def main() -> None:
    try:
        compile_check()
        payload_schema_check()
        idea_source_and_scoring_tests()
        business_gate_and_lifecycle_tests()
        full_dry_run_pipeline()
        monitoring_and_summary_tests()
        negative_guard_tests()
        portfolio_memory_tests()
        revenue_loop_tests()
        monetization_filter_tests()
        print("\nAll factory automation tests passed.")
    except TestFailure as exc:
        print(f"\nTEST FAILURE: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
