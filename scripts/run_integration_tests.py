#!/usr/bin/env python3
"""
Integration tests — validates the cross-repo contract between
AI-DAN Managing Director (Repo 1) and AI-DAN Factory (Repo 2).

Tests:
  1. brief_adapter correctly converts MD BuildBrief → Factory BuildBrief v1
  2. Adapted briefs pass validate_brief.py
  3. factory_callback.py CLI runs in dry-run mode
  4. All required Factory BuildBrief v1 fields are present after adaptation
  5. Round-trip: MD brief → adapt → validate → orchestrator dry-run
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
MD_BRIEF = ROOT / "test_data" / "md_format_brief.json"


class IntegrationTestFailure(Exception):
    pass


def run(args: list[str], *, expect_success: bool = True, env_overrides: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
    if env_overrides:
        for k, v in env_overrides.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, env=env)
    cmd = " ".join(args)
    print(f"\n$ {cmd}")
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if expect_success and result.returncode != 0:
        raise IntegrationTestFailure(f"Command failed ({result.returncode}): {cmd}")
    if not expect_success and result.returncode == 0:
        raise IntegrationTestFailure(f"Command unexpectedly succeeded: {cmd}")
    return result


def test_brief_adapter_conversion() -> None:
    """Test 1: brief_adapter converts MD → Factory schema correctly."""
    print("==> [1/5] brief_adapter: MD → Factory conversion")

    sys.path.insert(0, str(SCRIPTS))
    from brief_adapter import adapt_brief
    from factory_run_contract import BUILD_BRIEF_V1_REQUIRED_FIELDS

    md_brief = json.loads(MD_BRIEF.read_text(encoding="utf-8"))
    factory_brief = adapt_brief(md_brief)

    # Check all required fields are present and non-empty
    for field in BUILD_BRIEF_V1_REQUIRED_FIELDS:
        val = factory_brief.get(field)
        if not val or (isinstance(val, str) and not val.strip()):
            raise IntegrationTestFailure(
                f"Adapted brief missing required field: {field}"
            )

    # Check MD audit trail fields preserved
    if not factory_brief.get("_md_idea_id"):
        raise IntegrationTestFailure("Adapted brief missing _md_idea_id audit field")
    if not factory_brief.get("_md_schema_version"):
        raise IntegrationTestFailure("Adapted brief missing _md_schema_version audit field")

    # Spot-check specific mappings
    assert factory_brief["project_id"] == "md-schema-test-001", "project_id mismatch"
    assert factory_brief["demand_level"] == "HIGH", f"demand_level expected HIGH, got {factory_brief['demand_level']}"
    assert factory_brief["monetization_proof"] == "YES", "monetization_proof should be YES"
    assert factory_brief["source_type"] in ("TREND", "COMPETITOR", "GAP", "EXISTING_PRODUCT"), f"bad source_type: {factory_brief['source_type']}"

    print("  ✓ All required fields present, audit trail preserved, mappings correct")


def test_adapted_brief_passes_validation() -> None:
    """Test 2: Adapted brief passes validate_brief.py."""
    print("==> [2/5] validate_brief accepts adapted MD brief")

    sys.path.insert(0, str(SCRIPTS))
    from brief_adapter import adapt_brief

    md_brief = json.loads(MD_BRIEF.read_text(encoding="utf-8"))
    factory_brief = adapt_brief(md_brief)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=tempfile.gettempdir()
    ) as f:
        json.dump(factory_brief, f, ensure_ascii=True)
        adapted_path = f.name

    try:
        with tempfile.TemporaryDirectory(prefix="factory-integration-") as tmp:
            result_file = Path(tmp) / "validate_result.json"
            normalized_file = Path(tmp) / "normalized.json"
            run([
                sys.executable,
                "scripts/validate_brief.py",
                "--brief-file", adapted_path,
                "--expected-project-id", factory_brief["project_id"],
                "--normalized-output", str(normalized_file),
                "--result-file", str(result_file),
            ])

            if result_file.is_file():
                result = json.loads(result_file.read_text(encoding="utf-8"))
                if result.get("status") not in ("success", "valid"):
                    raise IntegrationTestFailure(
                        f"validate_brief returned status={result.get('status')}: {result.get('error', '')}"
                    )
            print("  ✓ Adapted brief passes validate_brief.py")
    finally:
        Path(adapted_path).unlink(missing_ok=True)


def test_callback_dry_run() -> None:
    """Test 3: factory_callback.py runs in dry-run mode without errors."""
    print("==> [3/5] factory_callback dry-run mode")

    with tempfile.TemporaryDirectory(prefix="factory-cb-") as tmp:
        result_file = Path(tmp) / "callback_result.json"
        run([
            sys.executable,
            "scripts/factory_callback.py",
            "--project-id", "integration-test-001",
            "--correlation-id", "corr-test-001",
            "--callback-url", "https://example.com/factory/callback",
            "--status", "succeeded",
            "--run-id", "12345",
            "--result-file", str(result_file),
            "--dry-run",
        ])

        if result_file.is_file():
            result = json.loads(result_file.read_text(encoding="utf-8"))
            if result.get("status") != "success":
                raise IntegrationTestFailure(
                    f"factory_callback dry-run failed: {result.get('error', '')}"
                )
        print("  ✓ factory_callback.py dry-run succeeds")


def test_brief_adapter_cli() -> None:
    """Test 4: brief_adapter CLI converts file correctly."""
    print("==> [4/5] brief_adapter CLI round-trip")

    with tempfile.TemporaryDirectory(prefix="factory-adapt-") as tmp:
        output_path = Path(tmp) / "adapted.json"
        run([
            sys.executable,
            "scripts/brief_adapter.py",
            "--input", str(MD_BRIEF),
            "--output", str(output_path),
        ])

        if not output_path.is_file():
            raise IntegrationTestFailure("brief_adapter CLI did not produce output file")

        adapted = json.loads(output_path.read_text(encoding="utf-8"))

        sys.path.insert(0, str(SCRIPTS))
        from factory_run_contract import BUILD_BRIEF_V1_REQUIRED_FIELDS

        for field in BUILD_BRIEF_V1_REQUIRED_FIELDS:
            if not adapted.get(field):
                raise IntegrationTestFailure(f"CLI output missing required field: {field}")

        print("  ✓ brief_adapter CLI produces valid Factory BuildBrief v1")


def test_native_brief_passthrough() -> None:
    """Test 5: A brief already in Factory-native format passes through unchanged."""
    print("==> [5/5] Native brief passthrough")

    sys.path.insert(0, str(SCRIPTS))
    from brief_adapter import adapt_brief

    native_brief = {
        "project_id": "native-001",
        "product_name": "Native Test",
        "problem": "Test problem",
        "solution": "Test solution",
        "cta": "Sign Up",
        "source_type": "TREND",
        "reference_context": "Test context",
        "demand_level": "HIGH",
        "monetization_proof": "YES",
        "market_saturation": "LOW",
        "differentiation": "STRONG",
    }

    result = adapt_brief(native_brief)
    # Should pass through without adding _md_ fields
    if result.get("_md_idea_id"):
        raise IntegrationTestFailure("Native brief should not get _md_ audit fields")

    for k, v in native_brief.items():
        if result.get(k) != v:
            raise IntegrationTestFailure(f"Native brief field {k} changed: {v} → {result.get(k)}")

    print("  ✓ Native briefs pass through unchanged")


def main() -> int:
    tests = [
        test_brief_adapter_conversion,
        test_adapted_brief_passes_validation,
        test_callback_dry_run,
        test_brief_adapter_cli,
        test_native_brief_passthrough,
    ]

    passed = 0
    failed = 0
    errors: list[str] = []

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except (IntegrationTestFailure, AssertionError) as exc:
            failed += 1
            errors.append(f"{test_fn.__name__}: {exc}")
            print(f"  ✗ FAILED: {exc}", file=sys.stderr)
        except Exception as exc:
            failed += 1
            errors.append(f"{test_fn.__name__}: {type(exc).__name__}: {exc}")
            print(f"  ✗ ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)

    print(f"\n{'=' * 60}")
    print(f"Integration Tests: {passed} passed, {failed} failed, {passed + failed} total")
    if errors:
        print("\nFailures:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("All integration tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
