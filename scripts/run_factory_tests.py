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
    print("==> [1/9] Running script syntax checks")
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
        "scripts/payment_link_generator.py",
        "scripts/feedback_processor.py",
        "scripts/validate_build_readiness.py",
        "scripts/run_factory_tests.py",
    ]
    run_command([sys.executable, "-m", "py_compile", *scripts], expect_success=True)


def payload_schema_check() -> None:
    print("==> [2/9] Validating test payload schemas")
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
    print("==> [3/9] Running idea source + scoring tests")
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
    print("==> [4/9] Running business gate + lifecycle state tests")
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
    print("==> [5/9] Running happy-path dry-run execution tests")
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
    print("==> [6/9] Running monitor/scale/portfolio tests")
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
    print("==> [7/9] Running negative guard tests")
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


def payment_and_feedback_tests() -> None:
    print("==> [8/9] Running payment link + feedback + build readiness tests")
    with tempfile.TemporaryDirectory(prefix="factory-payment-") as tmp_dir:
        tmp = Path(tmp_dir)
        business_output = tmp / "business_output.json"
        payment_result = tmp / "payment_result.json"
        feedback_log = tmp / "feedback_log.json"
        feedback_result = tmp / "feedback_result.json"
        readiness_result = tmp / "readiness_result.json"

        # Create a business output file to feed into payment generator.
        business_data = {
            "project_id": "test-pay-001",
            "headline": "Test Payment Product: Solve payment testing needs.",
            "CTA": "Buy Now",
            "monetization_model": "subscription",
            "pricing_suggestion": "$19/month starter, $49/month growth",
            "offer_structure": "Free trial -> Starter plan -> Growth plan with annual discount.",
            "gtm_plan": [],
            "conversion_hints": {},
            "problem": "Need payment testing",
            "solution": "Automated payment test",
        }
        business_output.write_text(
            json.dumps(business_data, indent=2) + "\n", encoding="utf-8"
        )

        # --- Payment link generator (dry-run) ---
        template_copy = tmp / "project"
        shutil.copytree(TEMPLATE_DIR, template_copy)

        run_command(
            [
                sys.executable,
                "scripts/payment_link_generator.py",
                "--business-output-file",
                str(business_output),
                "--project-dir",
                str(template_copy),
                "--provider",
                "stripe",
                "--result-file",
                str(payment_result),
                "--dry-run",
            ],
            expect_success=True,
        )
        payment = read_json(payment_result)
        if payment.get("status") != "success":
            raise TestFailure("payment_link_generator did not succeed")
        if not str(payment.get("payment_link", "")).strip():
            raise TestFailure("payment_link_generator did not emit payment_link")
        if not str(payment.get("payment_provider", "")).strip():
            raise TestFailure("payment_link_generator did not emit payment_provider")

        # Verify payment.config.json was written to project dir.
        payment_config = read_json(template_copy / "payment.config.json")
        if not str(payment_config.get("payment_link", "")).strip():
            raise TestFailure("payment.config.json missing payment_link")
        if float(payment_config.get("pricing_value", 0)) <= 0:
            raise TestFailure("payment.config.json pricing_value must be positive")

        # --- Feedback processor ---
        feedback_input = tmp / "feedback_input.json"
        feedback_entries = [
            {"feedback_type": "too_expensive", "project_id": "test-pay-001"},
            {"feedback_type": "not_clear", "project_id": "test-pay-001"},
            {"feedback_type": "too_expensive", "project_id": "test-pay-001"},
        ]
        feedback_input.write_text(json.dumps(feedback_entries), encoding="utf-8")

        run_command(
            [
                sys.executable,
                "scripts/feedback_processor.py",
                "--feedback-file",
                str(feedback_input),
                "--log-file",
                str(feedback_log),
                "--result-file",
                str(feedback_result),
                "--project-id",
                "test-pay-001",
            ],
            expect_success=True,
        )
        fb_result = read_json(feedback_result)
        if fb_result.get("status") != "success":
            raise TestFailure("feedback_processor did not succeed")
        if int(fb_result.get("entries_processed", 0)) != 3:
            raise TestFailure("feedback_processor should have processed 3 entries")
        signals = fb_result.get("signals", {})
        if not isinstance(signals, dict):
            raise TestFailure("feedback_processor must emit signals dict")

        # Verify feedback_log.json was written.
        fb_log = read_json(feedback_log)
        if not isinstance(fb_log.get("entries"), list):
            raise TestFailure("feedback_log.json missing entries array")
        if not isinstance(fb_log.get("aggregation"), dict):
            raise TestFailure("feedback_log.json missing aggregation")

        # --- Build readiness validation (VALID case) ---
        run_command(
            [
                sys.executable,
                "scripts/validate_build_readiness.py",
                "--project-dir",
                str(template_copy),
                "--project-id",
                "test-pay-001",
                "--result-file",
                str(readiness_result),
            ],
            expect_success=True,
        )
        readiness = read_json(readiness_result)
        if readiness.get("build_status") != "VALID":
            raise TestFailure(
                f"validate_build_readiness should be VALID, got: {readiness.get('build_status')}. "
                f"Failures: {readiness.get('failures')}"
            )

        # --- Build readiness validation (INVALID case — missing payment) ---
        invalid_project = tmp / "invalid-project"
        shutil.copytree(TEMPLATE_DIR, invalid_project)
        invalid_result = tmp / "invalid_readiness.json"
        run_command(
            [
                sys.executable,
                "scripts/validate_build_readiness.py",
                "--project-dir",
                str(invalid_project),
                "--project-id",
                "test-invalid",
                "--result-file",
                str(invalid_result),
            ],
            expect_success=False,
        )
        invalid_readiness = read_json(invalid_result)
        if invalid_readiness.get("build_status") != "INVALID":
            raise TestFailure("validate_build_readiness should be INVALID for missing payment")


def payment_tracking_db_tests() -> None:
    print("==> [9/9] Running payment tracking + feedback DB tests")
    with tempfile.TemporaryDirectory(prefix="factory-payment-db-") as tmp_dir:
        tmp = Path(tmp_dir)
        state_db = tmp / "state.sqlite"

        # Import state_store directly for DB-level tests.
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import importlib
            state_store_mod = importlib.import_module("state_store")
            store = state_store_mod.FactoryStateStore(str(state_db))

            # Initialize a run first.
            store.initialize_run(
                run_id="pay-run-1",
                run_attempt="1",
                project_id="pay-test-001",
            )

            # Test payment tracking upsert + get.
            store.upsert_payment_tracking(
                run_id="pay-run-1",
                run_attempt="1",
                project_id="pay-test-001",
                payment_link="https://buy.stripe.com/test_pay",
                payment_provider="stripe",
                pricing_value=19.0,
                payment_attempted=True,
                payment_success=False,
                revenue_amount=0,
            )
            pt = store.get_payment_tracking("pay-run-1", "1")
            if pt is None:
                raise TestFailure("payment_tracking record not found after upsert")
            if pt["payment_link"] != "https://buy.stripe.com/test_pay":
                raise TestFailure("payment_tracking payment_link mismatch")
            if pt["payment_provider"] != "stripe":
                raise TestFailure("payment_tracking payment_provider mismatch")
            if pt["payment_attempted"] is not True:
                raise TestFailure("payment_tracking payment_attempted should be True")
            if pt["payment_success"] is not False:
                raise TestFailure("payment_tracking payment_success should be False")

            # Update to success.
            store.upsert_payment_tracking(
                run_id="pay-run-1",
                run_attempt="1",
                project_id="pay-test-001",
                payment_link="https://buy.stripe.com/test_pay",
                payment_provider="stripe",
                pricing_value=19.0,
                payment_attempted=True,
                payment_success=True,
                revenue_amount=19.0,
            )
            pt2 = store.get_payment_tracking("pay-run-1", "1")
            if pt2 is None:
                raise TestFailure("payment_tracking record missing after update")
            if pt2["payment_success"] is not True:
                raise TestFailure("payment_tracking payment_success should be True after update")
            if pt2["revenue_amount"] != 19.0:
                raise TestFailure("payment_tracking revenue_amount mismatch")

            # Test feedback insert + list.
            store.insert_feedback(
                project_id="pay-test-001",
                feedback_type="too_expensive",
                comment="",
            )
            store.insert_feedback(
                project_id="pay-test-001",
                feedback_type="not_clear",
                comment="needs better docs",
            )
            fb = store.list_feedback(project_id="pay-test-001")
            if len(fb) != 2:
                raise TestFailure(f"Expected 2 feedback entries, got {len(fb)}")
            fb_types = {entry["feedback_type"] for entry in fb}
            if fb_types != {"too_expensive", "not_clear"}:
                raise TestFailure(f"Unexpected feedback types: {fb_types}")

            store.close()
        finally:
            sys.path.pop(0)


def main() -> None:
    try:
        compile_check()
        payload_schema_check()
        idea_source_and_scoring_tests()
        business_gate_and_lifecycle_tests()
        full_dry_run_pipeline()
        monitoring_and_summary_tests()
        negative_guard_tests()
        payment_and_feedback_tests()
        payment_tracking_db_tests()
        print("\nAll factory automation tests passed.")
    except TestFailure as exc:
        print(f"\nTEST FAILURE: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
