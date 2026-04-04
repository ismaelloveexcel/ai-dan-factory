#!/usr/bin/env python3
"""
Automated non-destructive test suite for ai-dan-factory.

This script validates:
- script syntax
- happy-path dry-run execution across all factory steps
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
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
TEMPLATE_DIR = ROOT / "templates" / "saas-template"
LIVE_TEST_BRIEF = ROOT / "test_data" / "live_test_brief.json"


class TestFailure(Exception):
    pass


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


def assert_step_success(path: Path, step_name: str) -> dict[str, object]:
    payload = read_json(path)
    status = str(payload.get("status", ""))
    mode = str(payload.get("mode", ""))
    if status != "success":
        raise TestFailure(f"{step_name} did not succeed. status={status} file={path}")
    if mode != "dry_run":
        raise TestFailure(f"{step_name} should run in dry_run mode during tests. mode={mode}")
    return payload


def compile_check() -> None:
    print("==> [1/4] Running script syntax checks")
    scripts = [
        "scripts/factory_utils.py",
        "scripts/validate_brief.py",
        "scripts/create_project.py",
        "scripts/inject_brief.py",
        "scripts/deploy.py",
        "scripts/run_factory_tests.py",
    ]
    run_command([sys.executable, "-m", "py_compile", *scripts], expect_success=True)


def happy_path_dry_run() -> None:
    print("==> [2/4] Running happy-path dry-run tests")
    if not LIVE_TEST_BRIEF.is_file():
        raise TestFailure(f"Missing test payload: {LIVE_TEST_BRIEF}")

    with tempfile.TemporaryDirectory(prefix="factory-tests-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        normalized = tmp_path / "normalized.json"
        validate_result = tmp_path / "validate_brief.json"
        create_result = tmp_path / "create_repo.json"
        inject_result = tmp_path / "inject_brief.json"
        deploy_result = tmp_path / "deploy.json"
        template_copy = tmp_path / "template-copy"
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
        validate_payload = assert_step_success(validate_result, "validate_brief")
        idempotency_key = str(validate_payload.get("idempotency_key", "")).strip()
        if not idempotency_key:
            raise TestFailure("validate_brief did not emit idempotency_key")

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
        create_payload = assert_step_success(create_result, "create_repo")
        if not bool(create_payload.get("simulated")):
            raise TestFailure("create_repo dry-run should be marked simulated=true")

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
        inject_payload = assert_step_success(inject_result, "inject_brief")
        files_written = inject_payload.get("files_written", [])
        if not isinstance(files_written, list) or len(files_written) != 2:
            raise TestFailure("inject_brief should report two files_written values")

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
        deploy_payload = assert_step_success(deploy_result, "deploy")
        if str(deploy_payload.get("deployment_status", "")) != "simulated":
            raise TestFailure("deploy dry-run should emit deployment_status=simulated")


def negative_guard_tests() -> None:
    print("==> [3/4] Running negative guard tests")
    with tempfile.TemporaryDirectory(prefix="factory-tests-negative-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        invalid_brief = tmp_path / "invalid_brief.json"
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
                str(tmp_path / "normalized.json"),
                "--result-file",
                str(tmp_path / "validate_failed.json"),
                "--dry-run",
            ],
            expect_success=False,
        )

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

        # Use valid normalized brief but mismatched --project-id to confirm consistency guard.
        normalized = tmp_path / "normalized_valid.json"
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
        template_copy = tmp_path / "template-copy"
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


def payload_schema_check() -> None:
    print("==> [4/4] Validating live test payload schema")
    payload = read_json(LIVE_TEST_BRIEF)
    for field in ("project_id", "product_name", "problem", "solution", "cta"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise TestFailure(f"Payload field '{field}' must be a non-empty string.")


def main() -> None:
    try:
        compile_check()
        payload_schema_check()
        happy_path_dry_run()
        negative_guard_tests()
        print("\nAll factory automation tests passed.")
    except TestFailure as exc:
        print(f"\nTEST FAILURE: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
