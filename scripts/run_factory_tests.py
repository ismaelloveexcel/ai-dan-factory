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
- repo discovery scoring, selection and fallback behavior

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
    print("==> [1/11] Running script syntax checks")
    scripts = [
        "scripts/factory_utils.py",
        "scripts/factory_run_contract.py",
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
        "scripts/quality_gate.py",
        "scripts/build_economics.py",
        "scripts/distribution_engine.py",
        "scripts/build_control.py",
        "scripts/ai_enhance.py",
        "scripts/repo_discovery_engine.py",
        "scripts/factory_orchestrator.py",
        "scripts/run_factory_tests.py",
    ]
    run_command([sys.executable, "-m", "py_compile", *scripts], expect_success=True)


def payload_schema_check() -> None:
    print("==> [2/11] Validating test payload schemas")
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
    print("==> [3/11] Running idea source + scoring tests")
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
    print("==> [4/11] Running business gate + lifecycle state tests")
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
    print("==> [5/11] Running happy-path dry-run execution tests")
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
    print("==> [6/11] Running monitor/scale/portfolio tests")
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
    print("==> [7/11] Running negative guard tests")
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


def quality_economics_distribution_tests() -> None:
    print("==> [8/11] Running quality gate + build economics + distribution tests")
    with tempfile.TemporaryDirectory(prefix="factory-qed-") as tmp_dir:
        tmp = Path(tmp_dir)

        # Create normalized brief for testing
        normalized = tmp / "normalized.json"
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

        # Generate business output
        business_output = tmp / "business_output.json"
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

        # Test AI enhancement (dry-run, no API key)
        ai_copy_result = tmp / "ai_copy.json"
        run_command(
            [
                sys.executable,
                "scripts/ai_enhance.py",
                "--brief-file",
                str(normalized),
                "--result-file",
                str(ai_copy_result),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )
        ai_copy = read_json(ai_copy_result)
        if ai_copy.get("quality_level") != "reduced":
            raise TestFailure("ai_enhance dry-run should produce reduced quality level")
        if not isinstance(ai_copy.get("ai_copy"), dict):
            raise TestFailure("ai_enhance must produce ai_copy dict")

        # Test quality gate
        quality_result = tmp / "quality_gate.json"
        run_command(
            [
                sys.executable,
                "scripts/quality_gate.py",
                "--brief-file",
                str(normalized),
                "--business-output-file",
                str(business_output),
                "--health-status",
                "simulated",
                "--result-file",
                str(quality_result),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )
        quality = read_json(quality_result)
        score = int(quality.get("quality_score", 0))
        if score < 0 or score > 12:
            raise TestFailure("quality_gate score must be between 0 and 12")
        if quality.get("quality_decision") not in ("BLOCK", "IMPROVE", "PROCEED"):
            raise TestFailure("quality_gate decision must be BLOCK/IMPROVE/PROCEED")

        # Test build economics
        economics_result = tmp / "build_economics.json"
        run_command(
            [
                sys.executable,
                "scripts/build_economics.py",
                "--brief-file",
                str(normalized),
                "--result-file",
                str(economics_result),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )
        economics = read_json(economics_result)
        if economics.get("economics_decision") not in ("REJECT", "HOLD", "PRIORITIZE"):
            raise TestFailure("build_economics decision must be REJECT/HOLD/PRIORITIZE")
        roi = float(economics.get("roi", 0))
        if roi < 0:
            raise TestFailure("build_economics ROI cannot be negative for valid brief")

        # Test distribution engine
        distribution_result = tmp / "distribution.json"
        run_command(
            [
                sys.executable,
                "scripts/distribution_engine.py",
                "--brief-file",
                str(normalized),
                "--business-output-file",
                str(business_output),
                "--deployment-url",
                "https://example.com/test-001",
                "--result-file",
                str(distribution_result),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )
        distribution = read_json(distribution_result)
        if not distribution.get("landing_content"):
            raise TestFailure("distribution must include landing_content")
        if not distribution.get("first_post"):
            raise TestFailure("distribution must include first_post")
        outreach = distribution.get("outreach_targets")
        if not isinstance(outreach, list) or len(outreach) < 5:
            raise TestFailure("distribution must include at least 5 outreach targets")

        # Test build control
        state_db = tmp / "control_state.sqlite"
        control_result = tmp / "build_control.json"
        run_command(
            [
                sys.executable,
                "scripts/build_control.py",
                "--brief-file",
                str(normalized),
                "--state-db",
                str(state_db),
                "--business-score",
                "8",
                "--result-file",
                str(control_result),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )
        control = read_json(control_result)
        if control.get("control_decision") not in ("ALLOWED", "BLOCKED"):
            raise TestFailure("build_control decision must be ALLOWED/BLOCKED")
        if not control.get("priority"):
            raise TestFailure("build_control must include priority")


def e2e_simulation_tests() -> None:
    print("==> [9/11] Running end-to-end pipeline simulation")
    with tempfile.TemporaryDirectory(prefix="factory-e2e-") as tmp_dir:
        tmp = Path(tmp_dir)
        state_db = tmp / "e2e_state.sqlite"
        normalized = tmp / "normalized.json"
        business_output = tmp / "business_output.json"
        template_copy = tmp / "template-copy"
        shutil.copytree(TEMPLATE_DIR, template_copy)

        # Step 1: Validate brief
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
                str(tmp / "validate.json"),
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 2: Initialize lifecycle
        run_command(
            [
                sys.executable,
                "scripts/lifecycle_orchestrator.py",
                "--state-db",
                str(state_db),
                "--project-id",
                "test-001",
                "--run-id",
                "e2e-001",
                "--run-attempt",
                "1",
                "--to-state",
                "idea",
                "--reason",
                "E2E test init",
                "--timestamp-utc",
                utc_now(),
            ],
            expect_success=True,
        )

        # Step 3: Business gate
        run_command(
            [
                sys.executable,
                "scripts/validate_business_gate.py",
                "--brief-file",
                str(normalized),
                "--result-file",
                str(tmp / "gate.json"),
                "--state-db",
                str(state_db),
                "--workflow-run-id",
                "e2e-001",
                "--workflow-run-attempt",
                "1",
                "--workflow-url",
                "https://example/e2e",
                "--timestamp-utc",
                utc_now(),
            ],
            expect_success=True,
        )
        gate = read_json(tmp / "gate.json")
        if gate.get("decision") != "APPROVE":
            raise TestFailure(f"E2E: Expected APPROVE for live_test_brief, got {gate.get('decision')}")

        # Step 4: Build economics
        run_command(
            [
                sys.executable,
                "scripts/build_economics.py",
                "--brief-file",
                str(normalized),
                "--result-file",
                str(tmp / "economics.json"),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 5: Build control
        run_command(
            [
                sys.executable,
                "scripts/build_control.py",
                "--brief-file",
                str(normalized),
                "--state-db",
                str(state_db),
                "--business-score",
                str(gate.get("score", 0)),
                "--result-file",
                str(tmp / "control.json"),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 5.5: Repo discovery (dry-run)
        run_command(
            [
                sys.executable,
                "scripts/repo_discovery_engine.py",
                "--brief-file",
                str(normalized),
                "--project-id",
                "test-001",
                "--result-file",
                str(tmp / "discovery.json"),
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 6: Lifecycle to building
        run_command(
            [
                sys.executable,
                "scripts/lifecycle_orchestrator.py",
                "--state-db",
                str(state_db),
                "--project-id",
                "test-001",
                "--run-id",
                "e2e-001",
                "--run-attempt",
                "1",
                "--to-state",
                "building",
                "--reason",
                "E2E build stage",
                "--timestamp-utc",
                utc_now(),
            ],
            expect_success=True,
        )

        # Step 7: Create repo (dry-run)
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
                "--result-file",
                str(tmp / "create.json"),
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 8: AI enhance (dry-run)
        run_command(
            [
                sys.executable,
                "scripts/ai_enhance.py",
                "--brief-file",
                str(normalized),
                "--result-file",
                str(tmp / "ai_copy.json"),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 9: Inject brief (dry-run)
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
                "--result-file",
                str(tmp / "inject.json"),
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 10: Generate business output
        run_command(
            [
                sys.executable,
                "scripts/business_output_engine.py",
                "--brief-file",
                str(normalized),
                "--output-file",
                str(business_output),
                "--result-file",
                str(tmp / "bo_result.json"),
            ],
            expect_success=True,
        )

        # Step 11: Deploy (dry-run)
        run_command(
            [
                sys.executable,
                "scripts/deploy.py",
                "--project-id",
                "test-001",
                "--result-file",
                str(tmp / "deploy.json"),
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 12: Health check (dry-run)
        run_command(
            [
                sys.executable,
                "scripts/deploy_health_check.py",
                "--project-id",
                "test-001",
                "--deployment-url",
                "https://example.com/test-001",
                "--result-file",
                str(tmp / "health.json"),
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 13: Quality gate
        run_command(
            [
                sys.executable,
                "scripts/quality_gate.py",
                "--brief-file",
                str(normalized),
                "--business-output-file",
                str(business_output),
                "--health-status",
                "simulated",
                "--result-file",
                str(tmp / "quality.json"),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )

        # Step 14: Distribution
        run_command(
            [
                sys.executable,
                "scripts/distribution_engine.py",
                "--brief-file",
                str(normalized),
                "--business-output-file",
                str(business_output),
                "--deployment-url",
                "https://example.com/test-001",
                "--result-file",
                str(tmp / "distribution.json"),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=True,
        )

        # Verify all result files exist
        expected_files = [
            "validate.json",
            "gate.json",
            "economics.json",
            "control.json",
            "discovery.json",
            "create.json",
            "inject.json",
            "bo_result.json",
            "deploy.json",
            "health.json",
            "quality.json",
            "distribution.json",
        ]
        for f in expected_files:
            path = tmp / f
            if not path.is_file():
                raise TestFailure(f"E2E: Missing expected result file: {f}")

        print("  E2E simulation: SUCCESS (all 15 steps completed)")


def repo_discovery_tests() -> None:
    """Test repo discovery scoring, selection logic, fallback, and CLI."""
    print("==> [10/11] Running repo discovery + template selection tests")

    # --- Import scoring/selection functions directly for unit tests. --------
    sys.path.insert(0, str(ROOT / "scripts"))
    import repo_discovery_engine as rde  # noqa: E402

    # 1. build_search_query produces meaningful queries.
    brief = {
        "product_name": "AI Dashboard Builder",
        "problem": "Users need a simple dashboard for analytics",
        "solution": "An AI-powered analytics dashboard starter kit",
    }
    query = rde.build_search_query(brief)
    if not query or len(query) < 5:
        raise TestFailure(f"build_search_query returned empty/short query: {query!r}")
    if "template" not in query.lower() and "starter" not in query.lower():
        raise TestFailure(f"build_search_query missing template/starter bias: {query!r}")
    print(f"  build_search_query OK: {query!r}")

    # 2. score_candidate: archived repos get 0.
    archived_repo = {
        "full_name": "user/old-project",
        "description": "Archived starter",
        "stars": 500,
        "language": "JavaScript",
        "updated_at": "2020-01-01T00:00:00Z",
        "topics": ["template"],
        "html_url": "https://github.com/user/old-project",
        "is_template": True,
        "archived": True,
        "fork": False,
        "open_issues_count": 0,
        "license": "MIT",
        "size": 1000,
    }
    score_archived = rde.score_candidate(archived_repo, search_query=query)
    if score_archived != 0.0:
        raise TestFailure(f"Archived repo should score 0, got {score_archived}")
    print("  score_candidate (archived=0): OK")

    # 3. score_candidate: forked repos get 0.
    fork_repo = dict(archived_repo, archived=False, fork=True, full_name="user/forked")
    score_fork = rde.score_candidate(fork_repo, search_query=query)
    if score_fork != 0.0:
        raise TestFailure(f"Forked repo should score 0, got {score_fork}")
    print("  score_candidate (fork=0): OK")

    # 4. score_candidate: good template scores higher than plain repo.
    good_template = {
        "full_name": "user/dashboard-template",
        "description": "AI-powered analytics dashboard starter kit template",
        "stars": 200,
        "language": "JavaScript",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "topics": ["template", "dashboard", "starter"],
        "html_url": "https://github.com/user/dashboard-template",
        "is_template": True,
        "archived": False,
        "fork": False,
        "open_issues_count": 5,
        "license": "MIT",
        "size": 5000,
    }
    plain_repo = {
        "full_name": "user/random-tool",
        "description": "A utility tool",
        "stars": 10,
        "language": "Python",
        "updated_at": "2023-01-01T00:00:00Z",
        "topics": [],
        "html_url": "https://github.com/user/random-tool",
        "is_template": False,
        "archived": False,
        "fork": False,
        "open_issues_count": 50,
        "license": "",
        "size": 200000,
    }
    score_good = rde.score_candidate(good_template, search_query=query, preferred_language="JavaScript")
    score_plain = rde.score_candidate(plain_repo, search_query=query, preferred_language="JavaScript")
    if score_good <= score_plain:
        raise TestFailure(
            f"Good template ({score_good}) should outscore plain repo ({score_plain})"
        )
    print(f"  score_candidate (good={score_good} > plain={score_plain}): OK")

    # 5. select_template: no candidates → USE_INTERNAL_TEMPLATE.
    sel_empty = rde.select_template([], search_query=query)
    if sel_empty["selection_mode"] != rde.MODE_USE_INTERNAL:
        raise TestFailure(
            f"Expected USE_INTERNAL_TEMPLATE with empty candidates, got {sel_empty['selection_mode']}"
        )
    print("  select_template (no candidates → USE_INTERNAL_TEMPLATE): OK")

    # 6. select_template: no internal template, no candidates → BUILD_MINIMAL_INTERNAL.
    sel_minimal = rde.select_template([], search_query=query, has_internal_template=False)
    if sel_minimal["selection_mode"] != rde.MODE_BUILD_MINIMAL:
        raise TestFailure(
            f"Expected BUILD_MINIMAL_INTERNAL, got {sel_minimal['selection_mode']}"
        )
    print("  select_template (no template → BUILD_MINIMAL_INTERNAL): OK")

    # 7. select_template: high-scoring external repo → REUSE_EXTERNAL_TEMPLATE.
    #    We need a repo whose score exceeds EXTERNAL_PREFERENCE_THRESHOLD (70).
    #    Craft one that maxes every dimension.
    perfect_repo = {
        "full_name": "org/dashboard-template-starter",
        "description": "AI-powered analytics dashboard starter kit template boilerplate",
        "stars": 10000,
        "language": "JavaScript",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "topics": ["template", "dashboard", "starter", "analytics", "ai"],
        "html_url": "https://github.com/org/dashboard-template-starter",
        "is_template": True,
        "archived": False,
        "fork": False,
        "open_issues_count": 2,
        "license": "MIT",
        "size": 3000,
    }
    score_perfect = rde.score_candidate(perfect_repo, search_query=query, preferred_language="JavaScript")
    if score_perfect < rde.EXTERNAL_PREFERENCE_THRESHOLD:
        raise TestFailure(
            f"Perfect repo scored {score_perfect}, expected >= {rde.EXTERNAL_PREFERENCE_THRESHOLD}"
        )
    sel_reuse = rde.select_template(
        [perfect_repo],
        search_query=query,
        preferred_language="JavaScript",
    )
    if sel_reuse["selection_mode"] != rde.MODE_REUSE_EXTERNAL:
        raise TestFailure(
            f"Expected REUSE_EXTERNAL_TEMPLATE, got {sel_reuse['selection_mode']}"
        )
    print(f"  select_template (high-score {score_perfect} → REUSE_EXTERNAL_TEMPLATE): OK")

    # 8. select_template: low-scoring candidates → USE_INTERNAL_TEMPLATE.
    sel_low = rde.select_template([plain_repo], search_query=query)
    if sel_low["selection_mode"] != rde.MODE_USE_INTERNAL:
        raise TestFailure(
            f"Expected USE_INTERNAL_TEMPLATE for low-score candidates, got {sel_low['selection_mode']}"
        )
    print("  select_template (low-score → USE_INTERNAL_TEMPLATE): OK")

    # 9. CLI dry-run produces valid result file.
    with tempfile.TemporaryDirectory(prefix="factory-discovery-") as tmp_dir:
        tmp = Path(tmp_dir)
        result_file = tmp / "discovery.json"

        run_command(
            [
                sys.executable,
                "scripts/repo_discovery_engine.py",
                "--brief-file",
                str(LIVE_TEST_BRIEF),
                "--project-id",
                "test-001",
                "--result-file",
                str(result_file),
                "--dry-run",
            ],
            expect_success=True,
        )
        result = read_json(result_file)
        if result.get("status") != "success":
            raise TestFailure(f"repo_discovery dry-run did not succeed: {result}")
        if result.get("selection_mode") not in (
            rde.MODE_REUSE_EXTERNAL,
            rde.MODE_USE_INTERNAL,
            rde.MODE_BUILD_MINIMAL,
        ):
            raise TestFailure(f"Invalid selection_mode: {result.get('selection_mode')}")
        required_keys = {
            "search_query", "repos_considered", "selection_mode",
            "selection_reason", "selected_repo", "timestamp",
        }
        missing = required_keys - set(result.keys())
        if missing:
            raise TestFailure(f"Result missing keys: {missing}")
        print("  CLI dry-run result: OK")

    # 10. CLI with missing brief file fails gracefully.
    with tempfile.TemporaryDirectory(prefix="factory-discovery-") as tmp_dir:
        tmp = Path(tmp_dir)
        run_command(
            [
                sys.executable,
                "scripts/repo_discovery_engine.py",
                "--brief-file",
                str(tmp / "nonexistent.json"),
                "--project-id",
                "test-001",
                "--result-file",
                str(tmp / "fail.json"),
                "--dry-run",
            ],
            expect_success=False,
        )
        print("  CLI missing-brief failure: OK")

    # --- Fixture tests: hard exclusion filters ---

    # 11. Stale repos (>365 days) are excluded.
    stale_repo = {
        "full_name": "user/stale-starter",
        "description": "A starter template last updated 2 years ago",
        "stars": 300,
        "language": "JavaScript",
        "updated_at": "2022-01-01T00:00:00Z",
        "topics": ["template", "starter"],
        "html_url": "https://github.com/user/stale-starter",
        "is_template": True,
        "archived": False,
        "fork": False,
        "open_issues_count": 5,
        "license": "MIT",
        "size": 2000,
    }
    score_stale = rde.score_candidate(stale_repo, search_query=query)
    if score_stale != 0.0:
        raise TestFailure(f"Stale repo should score 0, got {score_stale}")
    print("  score_candidate (stale=0): OK")

    # 12. Oversized repos are excluded.
    oversized_repo = {
        "full_name": "user/mega-monorepo",
        "description": "Huge monorepo with everything",
        "stars": 5000,
        "language": "JavaScript",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "topics": ["template"],
        "html_url": "https://github.com/user/mega-monorepo",
        "is_template": False,
        "archived": False,
        "fork": False,
        "open_issues_count": 10,
        "license": "MIT",
        "size": 600_000,
    }
    score_oversized = rde.score_candidate(oversized_repo, search_query=query)
    if score_oversized != 0.0:
        raise TestFailure(f"Oversized repo should score 0, got {score_oversized}")
    print("  score_candidate (oversized=0): OK")

    # 13. List-only repos (awesome-*) are excluded.
    awesome_repo = {
        "full_name": "user/awesome-dashboards",
        "description": "A curated list of dashboard tools and resources",
        "stars": 8000,
        "language": "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "topics": ["awesome", "awesome-list", "dashboard"],
        "html_url": "https://github.com/user/awesome-dashboards",
        "is_template": False,
        "archived": False,
        "fork": False,
        "open_issues_count": 20,
        "license": "MIT",
        "size": 500,
    }
    score_awesome = rde.score_candidate(awesome_repo, search_query=query)
    if score_awesome != 0.0:
        raise TestFailure(f"List-only repo should score 0, got {score_awesome}")
    print("  score_candidate (list-repo=0): OK")

    # --- Fixture tests: 3 realistic selection scenarios ---

    # 14. Realistic scenario: good external template selected.
    #     Simulates a Next.js SaaS dashboard template with strong signals.
    realistic_external = {
        "full_name": "vercel/next-saas-starter",
        "description": "Next.js SaaS starter template with auth, billing, and dashboard",
        "stars": 4500,
        "language": "TypeScript",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "topics": ["template", "nextjs", "saas", "starter", "dashboard"],
        "html_url": "https://github.com/vercel/next-saas-starter",
        "is_template": True,
        "archived": False,
        "fork": False,
        "open_issues_count": 12,
        "license": "MIT",
        "size": 8000,
    }
    realistic_query = "SaaS dashboard billing template OR starter"
    sel_realistic = rde.select_template(
        [realistic_external],
        search_query=realistic_query,
        preferred_language="TypeScript",
    )
    if sel_realistic["selection_mode"] != rde.MODE_REUSE_EXTERNAL:
        raise TestFailure(
            f"Realistic external: expected REUSE_EXTERNAL_TEMPLATE, got {sel_realistic['selection_mode']} "
            f"(score={sel_realistic['selected_score']})"
        )
    if sel_realistic["selected_repo"]["full_name"] != "vercel/next-saas-starter":
        raise TestFailure(
            f"Realistic external: expected vercel/next-saas-starter, got {sel_realistic['selected_repo']['full_name']}"
        )
    print(f"  fixture: external template selected (score={sel_realistic['selected_score']}): OK")

    # 15. Realistic scenario: candidates exist but are rejected → internal template.
    mediocre_candidates = [
        {
            "full_name": "user/old-dashboard",
            "description": "A basic dashboard project",
            "stars": 15,
            "language": "JavaScript",
            "updated_at": "2024-06-01T00:00:00Z",
            "topics": [],
            "html_url": "https://github.com/user/old-dashboard",
            "is_template": False,
            "archived": False,
            "fork": False,
            "open_issues_count": 80,
            "license": "",
            "size": 150000,
        },
        {
            "full_name": "user/misc-utils",
            "description": "Random utility functions",
            "stars": 5,
            "language": "Python",
            "updated_at": "2024-01-01T00:00:00Z",
            "topics": [],
            "html_url": "https://github.com/user/misc-utils",
            "is_template": False,
            "archived": False,
            "fork": False,
            "open_issues_count": 30,
            "license": "",
            "size": 50000,
        },
    ]
    sel_rejected = rde.select_template(
        mediocre_candidates,
        search_query=realistic_query,
        preferred_language="TypeScript",
    )
    if sel_rejected["selection_mode"] != rde.MODE_USE_INTERNAL:
        raise TestFailure(
            f"Realistic internal fallback: expected USE_INTERNAL_TEMPLATE, got {sel_rejected['selection_mode']}"
        )
    print("  fixture: candidates rejected → USE_INTERNAL_TEMPLATE: OK")

    # 16. Realistic scenario: API failure → empty candidates → safe fallback.
    #     Simulates by calling select_template with empty list (what main() does on API error).
    sel_api_fail = rde.select_template(
        [],
        search_query=realistic_query,
        has_internal_template=True,
    )
    if sel_api_fail["selection_mode"] != rde.MODE_USE_INTERNAL:
        raise TestFailure(
            f"API failure fallback: expected USE_INTERNAL_TEMPLATE, got {sel_api_fail['selection_mode']}"
        )
    # Also verify with no internal template → BUILD_MINIMAL_INTERNAL.
    sel_api_fail_no_tmpl = rde.select_template(
        [],
        search_query=realistic_query,
        has_internal_template=False,
    )
    if sel_api_fail_no_tmpl["selection_mode"] != rde.MODE_BUILD_MINIMAL:
        raise TestFailure(
            f"API failure (no internal): expected BUILD_MINIMAL_INTERNAL, got {sel_api_fail_no_tmpl['selection_mode']}"
        )
    print("  fixture: API failure → safe fallback: OK")

    # --- Enriched search query tests ---

    # 17. build_search_query uses additional fields when present.
    enriched_brief = {
        "product_name": "QuickInvoice",
        "problem": "Freelancers struggle with invoicing",
        "solution": "Automated invoice generator",
        "target_user": "freelancers",
        "product_type": "SaaS tool",
        "preferred_language": "TypeScript",
    }
    enriched_query = rde.build_search_query(enriched_brief)
    # Should include at least one token from target_user / product_type fields.
    query_lower = enriched_query.lower()
    has_enrichment = "freelancer" in query_lower or "saas" in query_lower or "typescript" in query_lower
    if not has_enrichment:
        raise TestFailure(
            f"Enriched query should include target_user/product_type/language tokens: {enriched_query!r}"
        )
    print(f"  build_search_query enriched fields: OK ({enriched_query!r})")

    print("  Repo discovery tests: ALL PASSED")


def orchestrator_tests() -> None:
    """Test that factory_orchestrator module is importable and its CLI handles dry-run."""
    print("==> [11/11] Running factory orchestrator tests")

    # 1. Import check — verify the module exposes the expected contract constants.
    sys.path.insert(0, str(ROOT / "scripts"))
    import factory_orchestrator as fo  # noqa: E402
    import factory_run_contract as frc  # noqa: E402

    # Contract version
    if not isinstance(frc.CONTRACT_VERSION, str) or not frc.CONTRACT_VERSION.strip():
        raise TestFailure(f"CONTRACT_VERSION must be a non-empty string, got {frc.CONTRACT_VERSION!r}")
    if frc.CONTRACT_VERSION != fo.CONTRACT_VERSION:
        raise TestFailure(
            f"CONTRACT_VERSION mismatch: factory_run_contract={frc.CONTRACT_VERSION!r}, "
            f"factory_orchestrator={fo.CONTRACT_VERSION!r}"
        )
    print(f"  contract_version={fo.CONTRACT_VERSION!r}: OK")

    # BuildBrief v1 required fields
    for field in fo.BUILD_BRIEF_V1_REQUIRED_FIELDS:
        if not isinstance(field, str) or not field.strip():
            raise TestFailure(f"BUILD_BRIEF_V1_REQUIRED_FIELDS contains invalid entry: {field!r}")
    if "project_id" not in fo.BUILD_BRIEF_V1_REQUIRED_FIELDS:
        raise TestFailure("BUILD_BRIEF_V1_REQUIRED_FIELDS missing 'project_id'")
    if "product_name" not in fo.BUILD_BRIEF_V1_REQUIRED_FIELDS:
        raise TestFailure("BUILD_BRIEF_V1_REQUIRED_FIELDS missing 'product_name'")

    # FactoryRunResult v1 keys
    for key in fo.FACTORY_RUN_RESULT_V1_KEYS:
        if not isinstance(key, str) or not key.strip():
            raise TestFailure(f"FACTORY_RUN_RESULT_V1_KEYS contains invalid entry: {key!r}")
    for required_key in ("contract_version", "project_id", "status", "run_mode",
                         "steps", "deployment", "quality_result"):
        if required_key not in fo.FACTORY_RUN_RESULT_V1_KEYS:
            raise TestFailure(f"FACTORY_RUN_RESULT_V1_KEYS missing '{required_key}'")
    print("  contract constants: OK")

    # 2. Verify factory_orchestrator re-exports match factory_run_contract
    if fo.BUILD_BRIEF_V1_REQUIRED_FIELDS != frc.BUILD_BRIEF_V1_REQUIRED_FIELDS:
        raise TestFailure("BUILD_BRIEF_V1_REQUIRED_FIELDS mismatch between orchestrator and contract module")
    if fo.FACTORY_RUN_RESULT_V1_KEYS != frc.FACTORY_RUN_RESULT_V1_KEYS:
        raise TestFailure("FACTORY_RUN_RESULT_V1_KEYS mismatch between orchestrator and contract module")
    print("  contract re-exports consistent: OK")

    # 3. CLI dry-run: missing brief file should exit non-zero gracefully.
    with tempfile.TemporaryDirectory(prefix="factory-orchestrator-") as tmp_dir:
        tmp = Path(tmp_dir)
        run_command(
            [
                sys.executable,
                "scripts/factory_orchestrator.py",
                "--brief-file",
                str(tmp / "nonexistent.json"),
                "--project-id",
                "test-001",
                "--dry-run",
            ],
            expect_success=False,
        )
    print("  CLI missing-brief exit: OK")

    print("  Orchestrator tests: ALL PASSED")


def main() -> None:
    try:
        compile_check()
        payload_schema_check()
        idea_source_and_scoring_tests()
        business_gate_and_lifecycle_tests()
        full_dry_run_pipeline()
        monitoring_and_summary_tests()
        negative_guard_tests()
        quality_economics_distribution_tests()
        e2e_simulation_tests()
        repo_discovery_tests()
        orchestrator_tests()
        print("\nAll factory automation tests passed.")
    except TestFailure as exc:
        print(f"\nTEST FAILURE: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
