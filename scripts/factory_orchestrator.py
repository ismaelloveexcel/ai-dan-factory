#!/usr/bin/env python3
"""
Factory execution orchestrator.

Moves orchestration responsibility from GitHub YAML into deterministic Python stages.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from factory_run_contract import (
    CANONICAL_STEP_ORDER,
    FACTORY_RUN_RESULT_VERSION,
    empty_result,
    normalize_step,
    utc_now,
)


@dataclass
class Context:
    repo_root: Path
    result_dir: Path
    brief_file: Path
    normalized_brief_file: Path
    normalized_inputs_file: Path
    tests_only_log_file: Path
    state_db: Path
    template_project_dir: Path
    project_id_raw: str
    build_brief_json: str
    dry_run_raw: str
    run_automated_tests_only_raw: str
    test_mode_raw: str
    run_id: str
    run_attempt: str
    workflow_url: str
    timestamp_utc: str
    result_artifact_name: str
    traffic_signal: str
    activation_metric: str
    revenue_signal_status: str
    github_repository_owner: str
    github_repository_name: str


class OrchestratorError(Exception):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _run_python(ctx: Context, args: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=ctx.repo_root,
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    return proc


def _result_path(ctx: Context, name: str) -> Path:
    return ctx.result_dir / f"{name}.json"


def input_stage(ctx: Context) -> dict[str, Any]:
    ctx.brief_file.write_text(ctx.build_brief_json or "", encoding="utf-8")
    out = _result_path(ctx, "normalize_inputs")
    proc = _run_python(
        ctx,
        [
            "scripts/normalize_workflow_inputs.py",
            "--project-id",
            ctx.project_id_raw,
            "--build-brief-json",
            ctx.build_brief_json,
            "--dry-run",
            ctx.dry_run_raw,
            "--run-automated-tests-only",
            ctx.run_automated_tests_only_raw,
            "--test-mode",
            ctx.test_mode_raw,
            "--normalized-output",
            str(ctx.normalized_inputs_file),
            "--result-file",
            str(out),
        ],
    )
    if proc.returncode != 0:
        raise OrchestratorError("Input contract normalization failed.")

    normalized = _read_json(ctx.normalized_inputs_file)
    if not normalized:
        raise OrchestratorError("Normalized input contract missing.")

    if str(normalized.get("run_mode", "")) == "tests_only":
        test_proc = _run_python(ctx, ["scripts/run_factory_tests.py"])
        ctx.tests_only_log_file.write_text(
            (test_proc.stdout or "") + ("\n" + test_proc.stderr if test_proc.stderr else ""),
            encoding="utf-8",
        )
        status = "success" if test_proc.returncode == 0 else "failed"
        payload = {
            "project_id": str(normalized.get("project_id", "unknown")),
            "step": "automated_tests_only",
            "status": status,
            "mode": "tests_only",
        }
        if status == "failed":
            payload["error"] = "Automated test suite failed. See tests_only.log."
        _write_json(_result_path(ctx, "automated_tests_only"), payload)
        if test_proc.returncode != 0:
            raise OrchestratorError(payload.get("error", "Automated tests failed."))
    return normalized


def gate_stage(ctx: Context, normalized_inputs: dict[str, Any]) -> tuple[dict[str, Any], str]:
    project_id = str(normalized_inputs["project_id"])
    run_mode = str(normalized_inputs["run_mode"])
    dry_run_effective = bool(normalized_inputs.get("dry_run_effective"))

    proc = _run_python(
        ctx,
        [
            "scripts/lifecycle_orchestrator.py",
            "--state-db",
            str(ctx.state_db),
            "--project-id",
            project_id,
            "--run-id",
            ctx.run_id,
            "--run-attempt",
            ctx.run_attempt,
            "--to-state",
            "idea",
            "--reason",
            "Initialized execution lifecycle state",
            "--workflow-url",
            ctx.workflow_url,
            "--timestamp-utc",
            ctx.timestamp_utc,
            "--metadata-json",
            json.dumps({"workflow_url": ctx.workflow_url}),
        ],
    )
    if proc.returncode == 0:
        _write_json(
            _result_path(ctx, "lifecycle_idea"),
            {
                "project_id": project_id,
                "step": "lifecycle_idea",
                "status": "success",
                "mode": run_mode,
            },
        )
    else:
        _write_json(
            _result_path(ctx, "lifecycle_idea"),
            {
                "project_id": project_id,
                "step": "lifecycle_idea",
                "status": "failed",
                "mode": run_mode,
                "error": (proc.stderr or proc.stdout or "").strip() or "Lifecycle initialization failed.",
            },
        )
        raise OrchestratorError(
            f"Lifecycle initialization failed with exit code {proc.returncode}."
        )

    validate_args = [
        "scripts/validate_brief.py",
        "--brief-file",
        str(ctx.brief_file),
        "--expected-project-id",
        project_id,
        "--normalized-output",
        str(ctx.normalized_brief_file),
        "--result-file",
        str(_result_path(ctx, "validate_brief")),
    ]
    if dry_run_effective:
        validate_args.append("--dry-run")
    if _run_python(ctx, validate_args).returncode != 0:
        raise OrchestratorError("BuildBrief validation failed.")

    gate_result_path = _result_path(ctx, "validate_business_gate")
    if _run_python(
        ctx,
        [
            "scripts/validate_business_gate.py",
            "--brief-file",
            str(ctx.normalized_brief_file),
            "--result-file",
            str(gate_result_path),
            "--state-db",
            str(ctx.state_db),
            "--workflow-run-id",
            ctx.run_id,
            "--workflow-run-attempt",
            ctx.run_attempt,
            "--workflow-url",
            ctx.workflow_url,
            "--timestamp-utc",
            ctx.timestamp_utc,
            "--run-mode",
            run_mode,
        ],
    ).returncode != 0:
        raise OrchestratorError("Business gate validation failed.")

    gate_data = _read_json(gate_result_path)
    score = str(gate_data.get("score", "0"))
    decision = str(gate_data.get("decision", ""))
    if decision != "APPROVE":
        reason = str(gate_data.get("reason", "Business gate decision was not APPROVE."))
        raise OrchestratorError(reason)

    econ_args = [
        "scripts/build_economics.py",
        "--brief-file",
        str(ctx.normalized_brief_file),
        "--result-file",
        str(_result_path(ctx, "build_economics")),
        "--project-id",
        project_id,
    ]
    if dry_run_effective:
        econ_args.append("--dry-run")
    if _run_python(ctx, econ_args).returncode != 0:
        raise OrchestratorError("Build economics stage failed.")

    if not dry_run_effective:
        econ_data = _read_json(_result_path(ctx, "build_economics"))
        if str(econ_data.get("economics_decision", "")).upper() == "HOLD":
            raise OrchestratorError("Build economics decision is HOLD; execution paused.")

    control_args = [
        "scripts/build_control.py",
        "--brief-file",
        str(ctx.normalized_brief_file),
        "--state-db",
        str(ctx.state_db),
        "--business-score",
        score,
        "--result-file",
        str(_result_path(ctx, "build_control")),
        "--project-id",
        project_id,
    ]
    if dry_run_effective:
        control_args.append("--dry-run")
    if _run_python(ctx, control_args).returncode != 0:
        raise OrchestratorError("Build control stage failed.")

    return gate_data, run_mode


def discovery_stage(ctx: Context, normalized_inputs: dict[str, Any]) -> dict[str, Any]:
    project_id = str(normalized_inputs["project_id"])
    dry_run_effective = bool(normalized_inputs.get("dry_run_effective"))

    args = [
        "scripts/repo_discovery_engine.py",
        "--brief-file",
        str(ctx.normalized_brief_file),
        "--project-id",
        project_id,
        "--result-file",
        str(_result_path(ctx, "repo_discovery")),
    ]
    if dry_run_effective:
        args.append("--dry-run")
    if _run_python(ctx, args).returncode != 0:
        raise OrchestratorError("Repo discovery stage failed.")
    return _read_json(_result_path(ctx, "repo_discovery"))


def repo_stage(ctx: Context, normalized_inputs: dict[str, Any], gate_data: dict[str, Any], discovery: dict[str, Any]) -> str:
    project_id = str(normalized_inputs["project_id"])
    run_mode = str(normalized_inputs["run_mode"])
    dry_run_effective = bool(normalized_inputs.get("dry_run_effective"))

    proc = _run_python(
        ctx,
        [
            "scripts/lifecycle_orchestrator.py",
            "--state-db",
            str(ctx.state_db),
            "--project-id",
            project_id,
            "--run-id",
            ctx.run_id,
            "--run-attempt",
            ctx.run_attempt,
            "--to-state",
            "building",
            "--reason",
            "Approved execution entered build stage",
            "--workflow-url",
            ctx.workflow_url,
            "--timestamp-utc",
            ctx.timestamp_utc,
            "--metadata-json",
            json.dumps({"score": gate_data.get("score", 0)}),
        ],
    )
    if proc.returncode == 0:
        _write_json(
            _result_path(ctx, "lifecycle_building"),
            {"project_id": project_id, "step": "lifecycle_building", "status": "success", "mode": run_mode},
        )
    else:
        _write_json(
            _result_path(ctx, "lifecycle_building"),
            {
                "project_id": project_id,
                "step": "lifecycle_building",
                "status": "failed",
                "mode": run_mode,
                "error": (proc.stderr or proc.stdout or "").strip() or "Lifecycle transition to building failed.",
            },
        )
        raise OrchestratorError(
            f"Failed to transition project {project_id} to building state (exit code {proc.returncode})."
        )

    normalized_brief = _read_json(ctx.normalized_brief_file)
    idempotency_key = str(normalized_brief.get("idempotency_key", ""))

    tmpl_owner = ctx.github_repository_owner
    tmpl_repo = ctx.github_repository_name
    selected_repo = str(discovery.get("selected_repo", ""))
    if str(discovery.get("selection_mode", "")) == "REUSE_EXTERNAL_TEMPLATE" and "/" in selected_repo:
        parts = selected_repo.split("/", 1)
        tmpl_owner, tmpl_repo = parts[0], parts[1]

    env = os.environ.copy()
    env["TEMPLATE_OWNER"] = tmpl_owner
    env["TEMPLATE_REPO"] = tmpl_repo

    args = [
        sys.executable,
        "scripts/create_project.py",
        "--project-id",
        project_id,
        "--org",
        ctx.github_repository_owner,
        "--template-owner",
        tmpl_owner,
        "--template-repo",
        tmpl_repo,
        "--idempotency-key",
        idempotency_key,
        "--result-file",
        str(_result_path(ctx, "create_repo")),
    ]
    if dry_run_effective:
        args.append("--dry-run")
    proc = subprocess.run(args, cwd=ctx.repo_root, env=env, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    if proc.returncode != 0:
        raise OrchestratorError("Repository creation stage failed.")

    if dry_run_effective:
        inject_args = [
            "scripts/inject_brief.py",
            "--project-id",
            project_id,
            "--project-dir",
            str(ctx.template_project_dir),
            "--brief-file",
            str(ctx.normalized_brief_file),
            "--idempotency-key",
            idempotency_key,
            "--result-file",
            str(_result_path(ctx, "inject_brief")),
            "--dry-run",
        ]
        if _run_python(ctx, inject_args).returncode != 0:
            raise OrchestratorError("Brief injection stage failed in dry-run mode.")
        return idempotency_key

    create_repo = _read_json(_result_path(ctx, "create_repo"))
    repo_url = str(create_repo.get("repo_url", "")).strip()
    if not repo_url:
        inject_args = [
            "scripts/inject_brief.py",
            "--project-id",
            project_id,
            "--project-dir",
            str(ctx.template_project_dir),
            "--brief-file",
            str(ctx.normalized_brief_file),
            "--idempotency-key",
            idempotency_key,
            "--result-file",
            str(_result_path(ctx, "inject_brief")),
        ]
        if _run_python(ctx, inject_args).returncode != 0:
            raise OrchestratorError("Brief injection fallback stage failed.")
        return idempotency_key

    workdir = Path(tempfile.mkdtemp(prefix=f"generated-repo-{ctx.run_id}-"))
    try:
        token = os.environ.get("FACTORY_GITHUB_TOKEN", "")
        clone_url = repo_url.replace("https://", f"https://x-access-token:{token}@") if token else repo_url
        clone_proc = subprocess.run(
            ["git", "clone", "--depth=1", clone_url, str(workdir)],
            cwd=ctx.repo_root,
            capture_output=True,
            text=True,
        )
        if clone_proc.returncode != 0:
            raise OrchestratorError("Failed to clone generated repository for injection.")

        inject_args = [
            "scripts/inject_brief.py",
            "--project-id",
            project_id,
            "--project-dir",
            str(workdir),
            "--brief-file",
            str(ctx.normalized_brief_file),
            "--idempotency-key",
            idempotency_key,
            "--result-file",
            str(_result_path(ctx, "inject_brief")),
        ]
        if _run_python(ctx, inject_args).returncode != 0:
            raise OrchestratorError("Brief injection stage failed.")

        subprocess.run(["git", "-C", str(workdir), "config", "user.email", "factory-bot@users.noreply.github.com"], check=False)
        subprocess.run(["git", "-C", str(workdir), "config", "user.name", "Factory Bot"], check=False)
        subprocess.run(["git", "-C", str(workdir), "add", "PRODUCT_BRIEF.md", "product.config.json"], check=False)
        diff_proc = subprocess.run(["git", "-C", str(workdir), "diff", "--cached", "--quiet"], check=False)
        if diff_proc.returncode != 0:
            subprocess.run(
                ["git", "-C", str(workdir), "commit", "-m", f"chore: inject product brief for {project_id}"],
                check=True,
            )
            subprocess.run(["git", "-C", str(workdir), "push"], check=True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return idempotency_key


def build_stage(ctx: Context) -> None:
    if _run_python(
        ctx,
        [
            "scripts/business_output_engine.py",
            "--brief-file",
            str(ctx.normalized_brief_file),
            "--output-file",
            str(_result_path(ctx, "business_output")),
            "--result-file",
            str(_result_path(ctx, "business_output_result")),
        ],
    ).returncode != 0:
        raise OrchestratorError("Business output stage failed.")


def deploy_stage(ctx: Context, normalized_inputs: dict[str, Any]) -> None:
    project_id = str(normalized_inputs["project_id"])
    run_mode = str(normalized_inputs["run_mode"])
    dry_run_effective = bool(normalized_inputs.get("dry_run_effective"))

    normalized_brief = _read_json(ctx.normalized_brief_file)
    idempotency_key = str(normalized_brief.get("idempotency_key", ""))

    deploy_args = [
        "scripts/deploy.py",
        "--project-id",
        project_id,
        "--idempotency-key",
        idempotency_key,
        "--result-file",
        str(_result_path(ctx, "deploy")),
    ]
    if dry_run_effective:
        deploy_args.append("--dry-run")
    if _run_python(ctx, deploy_args).returncode != 0:
        raise OrchestratorError("Deploy trigger stage failed.")

    deployment_url = str(_read_json(_result_path(ctx, "deploy")).get("deployment_url", ""))
    health_args = [
        "scripts/deploy_health_check.py",
        "--project-id",
        project_id,
        "--deployment-url",
        deployment_url,
        "--result-file",
        str(_result_path(ctx, "deploy_health")),
    ]
    if dry_run_effective:
        health_args.append("--dry-run")
    if _run_python(ctx, health_args).returncode != 0:
        raise OrchestratorError("Deployment health check failed.")

    for to_state, step in (("deployed", "lifecycle_deployed"), ("monitored", "lifecycle_monitored")):
        proc = _run_python(
            ctx,
            [
                "scripts/lifecycle_orchestrator.py",
                "--state-db",
                str(ctx.state_db),
                "--project-id",
                project_id,
                "--run-id",
                ctx.run_id,
                "--run-attempt",
                ctx.run_attempt,
                "--to-state",
                to_state,
                "--reason",
                f"Execution run entered {to_state} stage",
                "--workflow-url",
                ctx.workflow_url,
                "--timestamp-utc",
                ctx.timestamp_utc,
                "--metadata-json",
                json.dumps({"workflow_url": ctx.workflow_url}),
            ],
        )
        if proc.returncode == 0:
            _write_json(
                _result_path(ctx, step),
                {"project_id": project_id, "step": step, "status": "success", "mode": run_mode},
            )
        else:
            error_output = (proc.stderr or proc.stdout or "").strip() or f"Lifecycle transition to {to_state} failed."
            _write_json(
                _result_path(ctx, step),
                {
                    "project_id": project_id,
                    "step": step,
                    "status": "failed",
                    "mode": run_mode,
                    "error": error_output,
                },
            )
            raise OrchestratorError(f"Lifecycle transition to {to_state} failed.")

    if _run_python(
        ctx,
        [
            "scripts/monitor_and_decide.py",
            "--state-db",
            str(ctx.state_db),
            "--run-id",
            ctx.run_id,
            "--run-attempt",
            ctx.run_attempt,
            "--project-id",
            project_id,
            "--traffic-signal",
            ctx.traffic_signal,
            "--activation-metric",
            ctx.activation_metric,
            "--revenue-signal-status",
            ctx.revenue_signal_status,
            "--timestamp-utc",
            ctx.timestamp_utc,
            "--result-file",
            str(_result_path(ctx, "monitoring_decision")),
        ],
    ).returncode != 0:
        raise OrchestratorError("Monitoring recommendation stage failed.")


def quality_stage(ctx: Context, normalized_inputs: dict[str, Any]) -> None:
    project_id = str(normalized_inputs["project_id"])
    dry_run_effective = bool(normalized_inputs.get("dry_run_effective"))

    health_status = str(_read_json(_result_path(ctx, "deploy_health")).get("health_status", "unknown"))
    args = [
        "scripts/quality_gate.py",
        "--brief-file",
        str(ctx.normalized_brief_file),
        "--business-output-file",
        str(_result_path(ctx, "business_output")),
        "--health-status",
        health_status,
        "--result-file",
        str(_result_path(ctx, "quality_gate")),
        "--project-id",
        project_id,
    ]
    if dry_run_effective:
        args.append("--dry-run")
    if _run_python(ctx, args).returncode != 0:
        raise OrchestratorError("Quality gate failed.")


def report_stage(ctx: Context, normalized_inputs: dict[str, Any]) -> None:
    project_id = str(normalized_inputs["project_id"])
    dry_run_effective = bool(normalized_inputs.get("dry_run_effective"))

    business_output_file = _result_path(ctx, "business_output")
    distribution_args = [
        "scripts/distribution_engine.py",
        "--brief-file",
        str(ctx.normalized_brief_file),
        "--business-output-file",
        str(business_output_file),
        "--deployment-url",
        str(_read_json(_result_path(ctx, "deploy")).get("deployment_url", "")),
        "--result-file",
        str(_result_path(ctx, "distribution")),
        "--project-id",
        project_id,
    ]
    if dry_run_effective:
        distribution_args.append("--dry-run")

    if business_output_file.is_file():
        dist_proc = _run_python(ctx, distribution_args)
        if dist_proc.returncode != 0:
            _write_json(
                _result_path(ctx, "distribution"),
                {
                    "project_id": project_id,
                    "step": "distribution",
                    "status": "failed",
                    "mode": "dry_run" if dry_run_effective else "production",
                    "error": (dist_proc.stderr or dist_proc.stdout or "").strip() or "Distribution engine failed.",
                },
            )
    else:
        _write_json(
            _result_path(ctx, "distribution"),
            {
                "project_id": project_id,
                "step": "distribution",
                "status": "skipped",
                "mode": "dry_run" if dry_run_effective else "production",
                "reason": "No business output file available.",
            },
        )

    repo_url_val = str(_read_json(_result_path(ctx, "create_repo")).get("repo_url", ""))
    deploy_health = _read_json(_result_path(ctx, "deploy_health"))
    health_status = str(deploy_health.get("health_status", "unknown"))
    build_status = "succeeded" if health_status in {"healthy", "simulated", "tests_only"} else "failed"

    notify_args = [
        "scripts/notify_director.py",
        "--project-id",
        project_id,
        "--run-id",
        ctx.run_id,
        "--status",
        build_status,
        "--deploy-url",
        str(_read_json(_result_path(ctx, "deploy")).get("deployment_url", "")),
        "--repo-url",
        repo_url_val,
        "--result-file",
        str(_result_path(ctx, "notify_director")),
    ]
    if build_status == "failed":
        notify_args.extend(["--error", f"Build failed with health_status: {health_status}"])
    if dry_run_effective:
        notify_args.append("--dry-run")
    notify_proc = _run_python(ctx, notify_args)
    if notify_proc.returncode != 0:
        _write_json(
            _result_path(ctx, "notify_director"),
            {
                "project_id": project_id,
                "step": "notify_director",
                "status": "failed",
                "mode": "dry_run" if dry_run_effective else "production",
                "error": (notify_proc.stderr or notify_proc.stdout or "").strip() or "Notify director failed.",
            },
        )

    portfolio_proc = _run_python(
        ctx,
        [
            "scripts/portfolio_summary.py",
            "--state-db",
            str(ctx.state_db),
            "--result-file",
            str(_result_path(ctx, "portfolio_summary")),
        ],
    )
    if portfolio_proc.returncode != 0:
        _write_json(
            _result_path(ctx, "portfolio_summary"),
            {
                "project_id": project_id,
                "step": "portfolio_summary",
                "status": "failed",
                "mode": "dry_run" if dry_run_effective else "production",
                "error": (portfolio_proc.stderr or portfolio_proc.stdout or "").strip() or "Portfolio summary failed.",
            },
        )


def finalize_result(ctx: Context, run_mode: str, orchestrator_error: str = "") -> dict[str, Any]:
    normalized_inputs = _read_json(ctx.normalized_inputs_file)
    project_id = str(normalized_inputs.get("project_id", ctx.project_id_raw or "unknown"))

    response = empty_result(
        project_id=project_id,
        run_id=ctx.run_id,
        run_attempt=ctx.run_attempt,
        workflow_url=ctx.workflow_url,
        run_mode=run_mode,
    )
    response["timestamp_utc"] = ctx.timestamp_utc or utc_now()
    response["result_artifact"]["name"] = ctx.result_artifact_name
    response["contract_version"] = FACTORY_RUN_RESULT_VERSION

    step_data: dict[str, dict[str, Any]] = {}

    def _with_status(payload: dict[str, Any], step_name: str) -> dict[str, Any]:
        if payload and "status" not in payload:
            payload = dict(payload)
            payload["status"] = "success"
        if payload and "step" not in payload:
            payload = dict(payload)
            payload["step"] = step_name
        if payload and "mode" not in payload:
            payload = dict(payload)
            payload["mode"] = run_mode
        return payload
    for step_name in CANONICAL_STEP_ORDER:
        p = _result_path(ctx, step_name)
        if p.is_file():
            step_data[step_name] = _with_status(_read_json(p), step_name)
        elif step_name == "validate_business_gate" and _result_path(ctx, "business_gate").is_file():
            step_data[step_name] = _with_status(_read_json(_result_path(ctx, "business_gate")), step_name)
        elif step_name == "business_output" and _result_path(ctx, "business_output_result").is_file():
            step_data[step_name] = _with_status(_read_json(_result_path(ctx, "business_output_result")), step_name)
        else:
            step_data[step_name] = {"step": step_name, "status": "skipped", "mode": run_mode}

    steps = [normalize_step(name, step_data[name], run_mode) for name in CANONICAL_STEP_ORDER]
    response["steps"] = steps

    create_repo = step_data.get("create_repo", {})
    deploy = step_data.get("deploy", {})
    quality_gate = step_data.get("quality_gate", {})
    monitor = step_data.get("monitoring_decision", {})
    validate = step_data.get("validate_brief", {})

    response["repo_url"] = str(create_repo.get("repo_url", ""))
    response["deployment_url"] = str(deploy.get("deployment_url", ""))
    response["deployment"] = {
        "status": str(deploy.get("deployment_status", deploy.get("status", "not_started"))),
        "url": str(deploy.get("deployment_url", "")),
    }
    response["idempotency_key"] = str(validate.get("idempotency_key", ""))
    response["quality"] = {
        "status": str(quality_gate.get("status", "not_available")),
        "score": quality_gate.get("quality_score"),
        "decision": str(quality_gate.get("quality_decision", "not_available")),
        "reason": str(quality_gate.get("quality_reason", "")),
        "breakdown": quality_gate.get("quality_breakdown", {}),
    }
    response["execution_signals"] = {
        "kill_candidate": bool(monitor.get("kill_candidate", False)),
        "optimize_candidate": bool(monitor.get("optimize_candidate", False)),
        "scale_candidate": bool(monitor.get("scale_candidate", False)),
    }
    response["kill_candidate"] = response["execution_signals"]["kill_candidate"]
    response["optimize_candidate"] = response["execution_signals"]["optimize_candidate"]
    response["scale_candidate"] = response["execution_signals"]["scale_candidate"]

    errors: list[str] = []
    for step in response["steps"]:
        if step["status"] == "failed":
            err = step.get("error", {})
            msg = str(err.get("message", "")).strip()
            if msg:
                errors.append(f"{step['name']}: {msg}")

    if orchestrator_error:
        errors.insert(0, orchestrator_error)

    response["error_summary"] = "; ".join(errors)
    response["failure_reason"] = errors[0] if errors else ""

    if errors:
        response["status"] = "failed"
        response["error"] = {"code": "EXECUTION_FAILED", "message": response["failure_reason"]}
    else:
        response["status"] = "success"
        response["error"] = {"code": "", "message": ""}

    _write_json(ctx.result_dir / "factory-response.json", response)
    return response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute the factory pipeline through Python orchestration stages")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--build-brief-json", default="")
    parser.add_argument("--dry-run", required=True)
    parser.add_argument("--run-automated-tests-only", default="false")
    parser.add_argument("--test-mode", default="false")
    parser.add_argument("--traffic-signal", default="LOW")
    parser.add_argument("--activation-metric", default="LOW")
    parser.add_argument("--revenue-signal-status", default="NONE")
    parser.add_argument("--result-dir", required=True)
    parser.add_argument("--state-db", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--workflow-url", required=True)
    parser.add_argument("--timestamp-utc", default="")
    parser.add_argument("--template-project-dir", default="templates/saas-template")
    parser.add_argument("--github-repository-owner", required=True)
    parser.add_argument("--github-repository-name", required=True)
    parser.add_argument("--result-artifact-name", required=True)
    return parser.parse_args()


def build_context(args: argparse.Namespace) -> Context:
    repo_root = Path(__file__).resolve().parents[1]
    result_dir = Path(args.result_dir).expanduser().resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    return Context(
        repo_root=repo_root,
        result_dir=result_dir,
        brief_file=result_dir / "build-brief.json",
        normalized_brief_file=result_dir / "normalized-brief.json",
        normalized_inputs_file=result_dir / "normalized-inputs.json",
        tests_only_log_file=result_dir / "tests_only.log",
        state_db=Path(args.state_db).expanduser().resolve(),
        template_project_dir=(repo_root / args.template_project_dir).resolve(),
        project_id_raw=str(args.project_id),
        build_brief_json=str(args.build_brief_json or ""),
        dry_run_raw=str(args.dry_run),
        run_automated_tests_only_raw=str(args.run_automated_tests_only),
        test_mode_raw=str(args.test_mode),
        run_id=str(args.run_id),
        run_attempt=str(args.run_attempt),
        workflow_url=str(args.workflow_url),
        timestamp_utc=str(args.timestamp_utc or utc_now()),
        result_artifact_name=str(args.result_artifact_name),
        traffic_signal=str(args.traffic_signal),
        activation_metric=str(args.activation_metric),
        revenue_signal_status=str(args.revenue_signal_status),
        github_repository_owner=str(args.github_repository_owner),
        github_repository_name=str(args.github_repository_name),
    )


def main() -> None:
    args = parse_args()
    ctx = build_context(args)

    orchestrator_error = ""
    run_mode = "unknown"

    try:
        normalized_inputs = input_stage(ctx)
        run_mode = str(normalized_inputs.get("run_mode", "unknown"))

        if run_mode != "tests_only":
            gate_data, run_mode = gate_stage(ctx, normalized_inputs)
            discovery = discovery_stage(ctx, normalized_inputs)
            repo_stage(ctx, normalized_inputs, gate_data, discovery)
            build_stage(ctx)
            deploy_stage(ctx, normalized_inputs)
            quality_stage(ctx, normalized_inputs)
            report_stage(ctx, normalized_inputs)
    except OrchestratorError as exc:
        orchestrator_error = str(exc)
        print(f"[orchestrator] {orchestrator_error}", file=sys.stderr)
    except Exception as exc:  # pragma: no cover
        orchestrator_error = f"Unhandled orchestrator error: {exc}"
        print(f"[orchestrator] {orchestrator_error}", file=sys.stderr)

    response = finalize_result(ctx, run_mode=run_mode or "unknown", orchestrator_error=orchestrator_error)

    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as handle:
            handle.write("factory_response<<EOF\n")
            handle.write(json.dumps(response, ensure_ascii=True) + "\n")
            handle.write("EOF\n")

    print(json.dumps(response, ensure_ascii=True))
    if response.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
