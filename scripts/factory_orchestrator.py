#!/usr/bin/env python3
"""
Factory Orchestrator — execution plane entry point for AI-DAN factory builds.

This repo is the *execution plane*.  It receives BuildBrief v1 payloads, runs
deterministic pipeline stages, and returns FactoryRunResult v1 payloads.
Business and project-level truth lives in the AI-DAN control plane (Repo 1).

Three execution stages:
  input_stage  → validate brief, run business/economics gates, repo discovery
  build_stage  → create repo, inject brief, generate business output
  deploy_stage → trigger deployment, health-check, quality gate, monitor, distribute

Each stage calls leaf scripts as subprocesses so stage logic stays auditable
in isolation and individual scripts remain independently testable.

Contract definitions live in factory_run_contract.py.

Usage (CLI):
    python scripts/factory_orchestrator.py \\
        --brief-file path/to/build_brief.json \\
        --project-id my-project-001 \\
        --state-db data/lifecycle.sqlite \\
        --result-dir /tmp/factory-run \\
        [--dry-run] \\
        [--run-id RUN_ID] \\
        [--run-attempt RUN_ATTEMPT] \\
        [--workflow-url URL] \\
        [--traffic-signal LOW|MEDIUM|HIGH] \\
        [--activation-metric LOW|MEDIUM|HIGH] \\
        [--revenue-signal-status NONE|WEAK|STRONG] \\
        [--result-file path/to/factory_result.json]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory_run_contract import (
    BUILD_BRIEF_V1_OPTIONAL_FIELDS,
    BUILD_BRIEF_V1_REQUIRED_FIELDS,
    CONTRACT_VERSION,
    FACTORY_RUN_RESULT_V1_KEYS,
)
from factory_utils import log_event, maybe_write_result

# Re-export contract constants so existing importers of this module keep working
__all__ = [
    "BUILD_BRIEF_V1_OPTIONAL_FIELDS",
    "BUILD_BRIEF_V1_REQUIRED_FIELDS",
    "CONTRACT_VERSION",
    "FACTORY_RUN_RESULT_V1_KEYS",
    "OrchestratorError",
    "input_stage",
    "build_stage",
    "deploy_stage",
    "run_pipeline",
]

STEP_NAME = "factory_orchestrator"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_script(args: list[str], step: str) -> subprocess.CompletedProcess[str]:
    """Run a leaf script, print output, and return the completed process."""
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.rstrip(), flush=True)
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr, flush=True)
    if result.returncode != 0:
        raise OrchestratorError(
            f"Stage step '{step}' failed with exit code {result.returncode}"
        )
    return result


def _read_json_safe(path: Path) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


class OrchestratorError(Exception):
    """Raised when a pipeline stage fails unrecoverably."""


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------


def input_stage(
    *,
    brief_file: Path,
    project_id: str,
    state_db: str,
    run_id: str,
    run_attempt: str,
    workflow_url: str,
    timestamp_utc: str,
    result_dir: Path,
    dry_run: bool,
    mode: str,
) -> dict[str, Any]:
    """
    input_stage — validate brief, run lifecycle init, business gate, and gates.

    Returns a dict with:
      normalized_brief_file  (Path) : path to the normalised brief JSON
      idempotency_key        (str)  : stable key from the brief
      business_decision      (str)  : APPROVE | HOLD | REJECT
      business_score         (float): numeric gate score
      stage_results          (dict) : per-step result payloads
    """
    stage_results: dict[str, Any] = {}
    dry_flag = ["--dry-run"] if dry_run else []
    py = sys.executable

    # 1) Validate brief
    normalized_brief = result_dir / "normalized_brief.json"
    validate_result = result_dir / "validate_brief.json"
    _run_script(
        [
            py, "scripts/validate_brief.py",
            "--brief-file", str(brief_file),
            "--expected-project-id", project_id,
            "--normalized-output", str(normalized_brief),
            "--result-file", str(validate_result),
        ] + dry_flag,
        step="validate_brief",
    )
    stage_results["validate_brief"] = _read_json_safe(validate_result)
    idempotency_key = str(stage_results["validate_brief"].get("idempotency_key", ""))

    # 2) Initialize lifecycle state
    lifecycle_result = result_dir / "lifecycle_idea.json"
    _run_script(
        [
            py, "scripts/lifecycle_orchestrator.py",
            "--state-db", state_db,
            "--project-id", project_id,
            "--run-id", run_id,
            "--run-attempt", run_attempt,
            "--to-state", "idea",
            "--reason", "Initialized lifecycle state via orchestrator",
            "--workflow-url", workflow_url,
            "--timestamp-utc", timestamp_utc,
            "--metadata-json", json.dumps({"workflow_url": workflow_url}),
        ],
        step="lifecycle_idea",
    )
    lifecycle_data = lifecycle_result.read_text(encoding="utf-8") if lifecycle_result.is_file() else "{}"
    try:
        stage_results["lifecycle_idea"] = json.loads(lifecycle_data)
    except json.JSONDecodeError:
        stage_results["lifecycle_idea"] = {}

    # 3) Unified business gate
    brief_source = normalized_brief if normalized_brief.is_file() and normalized_brief.stat().st_size > 0 else brief_file
    gate_result = result_dir / "business_gate.json"
    _run_script(
        [
            py, "scripts/validate_business_gate.py",
            "--brief-file", str(brief_source),
            "--result-file", str(gate_result),
            "--state-db", state_db,
            "--workflow-run-id", run_id,
            "--workflow-run-attempt", run_attempt,
            "--workflow-url", workflow_url,
            "--timestamp-utc", timestamp_utc,
            "--run-mode", mode,
        ],
        step="business_gate",
    )
    gate_data = _read_json_safe(gate_result)
    stage_results["business_gate"] = gate_data
    business_decision = str(gate_data.get("decision", ""))
    business_score = float(gate_data.get("score", 0))

    if business_decision != "APPROVE":
        raise OrchestratorError(
            f"Business gate decision={business_decision}, score={business_score}. "
            "Build/deploy blocked."
        )

    # 4) Build economics
    economics_result = result_dir / "build_economics.json"
    _run_script(
        [
            py, "scripts/build_economics.py",
            "--brief-file", str(brief_source),
            "--result-file", str(economics_result),
            "--project-id", project_id,
        ] + dry_flag,
        step="build_economics",
    )
    economics_data = _read_json_safe(economics_result)
    stage_results["build_economics"] = economics_data
    if not dry_run and economics_data.get("economics_decision") == "HOLD":
        raise OrchestratorError("Build economics decision is HOLD; pausing pipeline.")

    # 5) Build control and rate limiting
    control_result = result_dir / "build_control.json"
    _run_script(
        [
            py, "scripts/build_control.py",
            "--brief-file", str(brief_source),
            "--state-db", state_db,
            "--business-score", str(business_score),
            "--result-file", str(control_result),
            "--project-id", project_id,
        ] + dry_flag,
        step="build_control",
    )
    stage_results["build_control"] = _read_json_safe(control_result)

    # 6) Repo discovery and template selection
    discovery_result = result_dir / "repo_discovery.json"
    _run_script(
        [
            py, "scripts/repo_discovery_engine.py",
            "--brief-file", str(brief_source),
            "--project-id", project_id,
            "--result-file", str(discovery_result),
        ] + dry_flag,
        step="repo_discovery",
    )
    stage_results["repo_discovery"] = _read_json_safe(discovery_result)

    return {
        "normalized_brief_file": normalized_brief,
        "idempotency_key": idempotency_key,
        "business_decision": business_decision,
        "business_score": business_score,
        "stage_results": stage_results,
    }


def build_stage(
    *,
    project_id: str,
    normalized_brief_file: Path,
    idempotency_key: str,
    state_db: str,
    run_id: str,
    run_attempt: str,
    workflow_url: str,
    timestamp_utc: str,
    result_dir: Path,
    dry_run: bool,
    discovery_result: dict[str, Any],
    template_owner: str,
    template_repo: str,
    repo_org: str,
) -> dict[str, Any]:
    """
    build_stage — create project repo, inject brief, and generate business output.

    Returns a dict with:
      repo_url       (str) : URL of the created/found project repository
      stage_results  (dict): per-step result payloads
    """
    stage_results: dict[str, Any] = {}
    dry_flag = ["--dry-run"] if dry_run else []
    py = sys.executable

    # Determine effective template source from discovery result
    tmpl_owner = template_owner
    tmpl_repo = template_repo
    selection_mode = str(discovery_result.get("selection_mode", ""))
    if selection_mode == "REUSE_EXTERNAL_TEMPLATE":
        selected = str(discovery_result.get("selected_repo", ""))
        if selected and "/" in selected:
            tmpl_owner, tmpl_repo = selected.split("/", 1)

    # 1) Advance lifecycle to building
    lifecycle_building = result_dir / "lifecycle_building.json"
    _run_script(
        [
            py, "scripts/lifecycle_orchestrator.py",
            "--state-db", state_db,
            "--project-id", project_id,
            "--run-id", run_id,
            "--run-attempt", run_attempt,
            "--to-state", "building",
            "--reason", "Approved idea entered build stage",
            "--workflow-url", workflow_url,
            "--timestamp-utc", timestamp_utc,
            "--metadata-json", "{}",
        ],
        step="lifecycle_building",
    )
    lifecycle_building_data = lifecycle_building.read_text(encoding="utf-8") if lifecycle_building.is_file() else "{}"
    try:
        stage_results["lifecycle_building"] = json.loads(lifecycle_building_data)
    except json.JSONDecodeError:
        stage_results["lifecycle_building"] = {}

    # 2) Create project repository
    create_result = result_dir / "create_repo.json"
    _run_script(
        [
            py, "scripts/create_project.py",
            "--project-id", project_id,
            "--org", repo_org,
            "--template-owner", tmpl_owner,
            "--template-repo", tmpl_repo,
            "--idempotency-key", idempotency_key,
            "--result-file", str(create_result),
        ] + dry_flag,
        step="create_repo",
    )
    create_data = _read_json_safe(create_result)
    stage_results["create_repo"] = create_data
    repo_url = str(create_data.get("repo_url", ""))

    # 3) Inject BuildBrief into generated repository
    inject_result = result_dir / "inject_brief.json"
    template_project_dir = str(Path("templates") / "saas-template")
    if dry_run:
        # dry-run: inject into local template dir to simulate the operation
        _run_script(
            [
                py, "scripts/inject_brief.py",
                "--project-id", project_id,
                "--project-dir", template_project_dir,
                "--brief-file", str(normalized_brief_file),
                "--idempotency-key", idempotency_key,
                "--result-file", str(inject_result),
                "--dry-run",
            ],
            step="inject_brief",
        )
    else:
        # production: clone generated repo, inject brief, commit and push
        github_token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("FACTORY_GITHUB_TOKEN", "")).strip()
        if repo_url and github_token:
            with tempfile.TemporaryDirectory(prefix=f"factory-inject-{project_id}-") as _inject_tmp:
                generated_repo_dir = Path(_inject_tmp)
                clone_url = repo_url.replace("https://", f"https://x-access-token:{github_token}@")
                _run_script(
                    ["git", "clone", "--depth=1", clone_url, str(generated_repo_dir)],
                    step="git_clone",
                )
                _run_script(
                    [
                        py, "scripts/inject_brief.py",
                        "--project-id", project_id,
                        "--project-dir", str(generated_repo_dir),
                        "--brief-file", str(normalized_brief_file),
                        "--idempotency-key", idempotency_key,
                        "--result-file", str(inject_result),
                    ],
                    step="inject_brief",
                )
                _run_script(
                    ["git", "-C", str(generated_repo_dir), "config",
                     "user.email", "factory-bot@users.noreply.github.com"],
                    step="git_config_email",
                )
                _run_script(
                    ["git", "-C", str(generated_repo_dir), "config", "user.name", "Factory Bot"],
                    step="git_config_name",
                )
                _run_script(
                    ["git", "-C", str(generated_repo_dir), "add",
                     "PRODUCT_BRIEF.md", "product.config.json"],
                    step="git_add",
                )
                # only commit and push if there are staged changes
                diff_check = subprocess.run(
                    ["git", "-C", str(generated_repo_dir), "diff", "--cached", "--quiet"],
                    capture_output=True,
                )
                if diff_check.returncode != 0:
                    _run_script(
                        ["git", "-C", str(generated_repo_dir), "commit",
                         "-m", f"chore: inject product brief for {project_id}"],
                        step="git_commit",
                    )
                    _run_script(
                        ["git", "-C", str(generated_repo_dir), "push"],
                        step="git_push",
                    )
        else:
            # fallback: no repo_url or no token — inject into template dir
            print(
                f"::warning::No repo_url or GITHUB_TOKEN for inject; "
                "falling back to template dir.",
                file=sys.stderr,
                flush=True,
            )
            _run_script(
                [
                    py, "scripts/inject_brief.py",
                    "--project-id", project_id,
                    "--project-dir", template_project_dir,
                    "--brief-file", str(normalized_brief_file),
                    "--idempotency-key", idempotency_key,
                    "--result-file", str(inject_result),
                ],
                step="inject_brief",
            )
    stage_results["inject_brief"] = _read_json_safe(inject_result)

    # 4) Generate business output
    business_output_file = result_dir / "business_output.json"
    business_output_result = result_dir / "business_output_result.json"
    _run_script(
        [
            py, "scripts/business_output_engine.py",
            "--brief-file", str(normalized_brief_file),
            "--output-file", str(business_output_file),
            "--result-file", str(business_output_result),
        ],
        step="business_output",
    )
    stage_results["business_output"] = _read_json_safe(business_output_result)

    return {
        "repo_url": repo_url,
        "business_output_file": business_output_file,
        "stage_results": stage_results,
    }


def deploy_stage(
    *,
    project_id: str,
    normalized_brief_file: Path,
    idempotency_key: str,
    state_db: str,
    run_id: str,
    run_attempt: str,
    workflow_url: str,
    timestamp_utc: str,
    result_dir: Path,
    dry_run: bool,
    business_output_file: Path,
    traffic_signal: str,
    activation_metric: str,
    revenue_signal_status: str,
) -> dict[str, Any]:
    """
    deploy_stage — deploy, health-check, quality gate, monitor, and distribute.

    Returns a dict with:
      deployment_url    (str) : deployment URL
      deployment_status (str) : triggered | skipped | failed
      kill_candidate    (bool): monitoring kill flag
      optimize_candidate(bool): monitoring optimize flag
      scale_candidate   (bool): monitoring scale flag
      stage_results     (dict): per-step result payloads
    """
    stage_results: dict[str, Any] = {}
    dry_flag = ["--dry-run"] if dry_run else []
    py = sys.executable

    # 1) Trigger deployment
    deploy_result = result_dir / "deploy.json"
    _run_script(
        [
            py, "scripts/deploy.py",
            "--project-id", project_id,
            "--idempotency-key", idempotency_key,
            "--result-file", str(deploy_result),
        ] + dry_flag,
        step="deploy",
    )
    deploy_data = _read_json_safe(deploy_result)
    stage_results["deploy"] = deploy_data
    deployment_url = str(deploy_data.get("deployment_url", ""))
    deployment_status = str(deploy_data.get("deployment_status", deploy_data.get("status", "unknown")))

    # 2) Deployment health check
    health_result = result_dir / "deploy_health.json"
    _run_script(
        [
            py, "scripts/deploy_health_check.py",
            "--project-id", project_id,
            "--deployment-url", deployment_url,
            "--result-file", str(health_result),
        ] + dry_flag,
        step="deploy_health",
    )
    health_data = _read_json_safe(health_result)
    stage_results["deploy_health"] = health_data
    health_status = str(health_data.get("health_status", "unknown"))

    # 3) Product quality gate
    quality_result = result_dir / "quality_gate.json"
    bo_flag = ["--business-output-file", str(business_output_file)] if business_output_file.is_file() else []
    _run_script(
        [
            py, "scripts/quality_gate.py",
            "--brief-file", str(normalized_brief_file),
        ] + bo_flag + [
            "--health-status", health_status,
            "--result-file", str(quality_result),
            "--project-id", project_id,
        ] + dry_flag,
        step="quality_gate",
    )
    stage_results["quality_gate"] = _read_json_safe(quality_result)

    # 4) Advance lifecycle to deployed
    lifecycle_deployed = result_dir / "lifecycle_deployed.json"
    _run_script(
        [
            py, "scripts/lifecycle_orchestrator.py",
            "--state-db", state_db,
            "--project-id", project_id,
            "--run-id", run_id,
            "--run-attempt", run_attempt,
            "--to-state", "deployed",
            "--reason", "Build completed and deployment triggered",
            "--workflow-url", workflow_url,
            "--timestamp-utc", timestamp_utc,
            "--metadata-json", json.dumps({"workflow_url": workflow_url}),
        ],
        step="lifecycle_deployed",
    )
    lifecycle_deployed_data = lifecycle_deployed.read_text(encoding="utf-8") if lifecycle_deployed.is_file() else "{}"
    try:
        stage_results["lifecycle_deployed"] = json.loads(lifecycle_deployed_data)
    except json.JSONDecodeError:
        stage_results["lifecycle_deployed"] = {}

    # 5) Advance lifecycle to monitored
    lifecycle_monitored = result_dir / "lifecycle_monitored.json"
    _run_script(
        [
            py, "scripts/lifecycle_orchestrator.py",
            "--state-db", state_db,
            "--project-id", project_id,
            "--run-id", run_id,
            "--run-attempt", run_attempt,
            "--to-state", "monitored",
            "--reason", "Deployment entered monitoring stage",
            "--workflow-url", workflow_url,
            "--timestamp-utc", timestamp_utc,
            "--metadata-json", json.dumps({"workflow_url": workflow_url}),
        ],
        step="lifecycle_monitored",
    )
    lifecycle_monitored_data = lifecycle_monitored.read_text(encoding="utf-8") if lifecycle_monitored.is_file() else "{}"
    try:
        stage_results["lifecycle_monitored"] = json.loads(lifecycle_monitored_data)
    except json.JSONDecodeError:
        stage_results["lifecycle_monitored"] = {}

    # 6) Monitor and decide
    monitor_result = result_dir / "monitoring_decision.json"
    _run_script(
        [
            py, "scripts/monitor_and_decide.py",
            "--state-db", state_db,
            "--run-id", run_id,
            "--run-attempt", run_attempt,
            "--project-id", project_id,
            "--traffic-signal", traffic_signal,
            "--activation-metric", activation_metric,
            "--revenue-signal-status", revenue_signal_status,
            "--timestamp-utc", timestamp_utc,
            "--result-file", str(monitor_result),
        ],
        step="monitor_and_decide",
    )
    monitor_data = _read_json_safe(monitor_result)
    stage_results["monitoring_decision"] = monitor_data
    kill_candidate = bool(monitor_data.get("kill_candidate", False))
    optimize_candidate = bool(monitor_data.get("optimize_candidate", False))
    scale_candidate = bool(monitor_data.get("scale_candidate", False))

    # 7) Distribution (optional — skip if no business output)
    distribution_result = result_dir / "distribution.json"
    if business_output_file.is_file():
        _run_script(
            [
                py, "scripts/distribution_engine.py",
                "--brief-file", str(normalized_brief_file),
                "--business-output-file", str(business_output_file),
                "--deployment-url", deployment_url,
                "--result-file", str(distribution_result),
                "--project-id", project_id,
            ] + dry_flag,
            step="distribution",
        )
        stage_results["distribution"] = _read_json_safe(distribution_result)

    return {
        "deployment_url": deployment_url,
        "deployment_status": deployment_status,
        "health_status": health_status,
        "kill_candidate": kill_candidate,
        "optimize_candidate": optimize_candidate,
        "scale_candidate": scale_candidate,
        "stage_results": stage_results,
    }


# ---------------------------------------------------------------------------
# Top-level pipeline runner
# ---------------------------------------------------------------------------


def run_pipeline(
    *,
    brief_file: Path,
    project_id: str,
    state_db: str,
    run_id: str,
    run_attempt: str,
    workflow_url: str,
    result_dir: Path,
    dry_run: bool,
    traffic_signal: str = "LOW",
    activation_metric: str = "LOW",
    revenue_signal_status: str = "NONE",
    template_owner: str = "",
    template_repo: str = "",
    repo_org: str = "",
    result_file: str = "",
) -> dict[str, Any]:
    """
    Orchestrate input_stage → build_stage → deploy_stage.

    Returns a FactoryRunResult v1 dict.  Writes it to *result_file* when provided.
    Always writes portfolio_summary.json and raises SystemExit(1) on failure.
    """
    result_dir.mkdir(parents=True, exist_ok=True)
    timestamp_utc = _utc_now()
    mode = "dry_run" if dry_run else "production"
    py = sys.executable

    log_event(
        project_id=project_id,
        step=STEP_NAME,
        status="started",
        mode=mode,
        run_id=run_id,
        run_attempt=run_attempt,
    )

    all_steps: list[dict[str, Any]] = []
    repo_url = ""
    deployment_url = ""
    deployment_status = "not_started"
    idempotency_key = ""
    kill_candidate = False
    optimize_candidate = False
    scale_candidate = False
    errors: list[str] = []
    failure_reason = ""
    overall_status = "success"

    try:
        # -------- input_stage ------------------------------------------------
        input_out = input_stage(
            brief_file=brief_file,
            project_id=project_id,
            state_db=state_db,
            run_id=run_id,
            run_attempt=run_attempt,
            workflow_url=workflow_url,
            timestamp_utc=timestamp_utc,
            result_dir=result_dir,
            dry_run=dry_run,
            mode=mode,
        )
        idempotency_key = input_out["idempotency_key"]
        for step_name, step_data in input_out["stage_results"].items():
            all_steps.append(step_data)
            if isinstance(step_data, dict) and step_data.get("status") == "failed":
                err = str(step_data.get("error", "")).strip()
                if err:
                    errors.append(f"{step_name}: {err}")

        # -------- build_stage ------------------------------------------------
        discovery_result = input_out["stage_results"].get("repo_discovery", {})
        build_out = build_stage(
            project_id=project_id,
            normalized_brief_file=input_out["normalized_brief_file"],
            idempotency_key=idempotency_key,
            state_db=state_db,
            run_id=run_id,
            run_attempt=run_attempt,
            workflow_url=workflow_url,
            timestamp_utc=timestamp_utc,
            result_dir=result_dir,
            dry_run=dry_run,
            discovery_result=discovery_result,
            template_owner=template_owner,
            template_repo=template_repo,
            repo_org=repo_org,
        )
        repo_url = build_out["repo_url"]
        for step_name, step_data in build_out["stage_results"].items():
            all_steps.append(step_data)
            if isinstance(step_data, dict) and step_data.get("status") == "failed":
                err = str(step_data.get("error", "")).strip()
                if err:
                    errors.append(f"{step_name}: {err}")

        # -------- deploy_stage -----------------------------------------------
        deploy_out = deploy_stage(
            project_id=project_id,
            normalized_brief_file=input_out["normalized_brief_file"],
            idempotency_key=idempotency_key,
            state_db=state_db,
            run_id=run_id,
            run_attempt=run_attempt,
            workflow_url=workflow_url,
            timestamp_utc=timestamp_utc,
            result_dir=result_dir,
            dry_run=dry_run,
            business_output_file=build_out["business_output_file"],
            traffic_signal=traffic_signal,
            activation_metric=activation_metric,
            revenue_signal_status=revenue_signal_status,
        )
        deployment_url = deploy_out["deployment_url"]
        deployment_status = deploy_out["deployment_status"]
        kill_candidate = deploy_out["kill_candidate"]
        optimize_candidate = deploy_out["optimize_candidate"]
        scale_candidate = deploy_out["scale_candidate"]
        for step_name, step_data in deploy_out["stage_results"].items():
            all_steps.append(step_data)
            if isinstance(step_data, dict) and step_data.get("status") == "failed":
                err = str(step_data.get("error", "")).strip()
                if err:
                    errors.append(f"{step_name}: {err}")

    except OrchestratorError as exc:
        overall_status = "failed"
        failure_reason = str(exc)
        errors.append(failure_reason)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            error=failure_reason,
        )

    # Portfolio summary — always run
    try:
        portfolio_result = result_dir / "portfolio_summary.json"
        subprocess.run(
            [py, "scripts/portfolio_summary.py",
             "--state-db", state_db,
             "--result-file", str(portfolio_result)],
            text=True,
            capture_output=True,
        )
    except Exception:  # noqa: BLE001
        pass

    error_summary = "; ".join(errors) if errors else ""
    if overall_status == "failed" and not failure_reason:
        failure_reason = error_summary or "Pipeline failed before detailed reason was captured."

    # Extract quality_result as a top-level field for easier consumption by Repo 1
    quality_result: dict[str, Any] = {}
    for step_data in all_steps:
        if isinstance(step_data, dict) and step_data.get("step") == "quality_gate":
            quality_result = step_data
            break
    if not quality_result:
        # Try reading directly from result_dir
        quality_result = _read_json_safe(result_dir / "quality_gate.json")

    result: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "project_id": project_id,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "workflow_url": workflow_url,
        "timestamp_utc": timestamp_utc,
        "repo_url": repo_url,
        "deployment_url": deployment_url,
        "status": overall_status,
        "run_mode": mode,
        "idempotency_key": idempotency_key,
        "steps": all_steps,
        "deployment": {
            "status": deployment_status,
            "url": deployment_url,
        },
        "quality_result": quality_result,
        "error_summary": error_summary,
        "failure_reason": failure_reason,
        "kill_candidate": kill_candidate,
        "optimize_candidate": optimize_candidate,
        "scale_candidate": scale_candidate,
        "result_artifact": {
            "name": f"factory-result-{run_id}-{run_attempt}",
            "path": "factory-response.json",
        },
    }

    # Always write factory-response.json to result_dir so the workflow can
    # upload it even when result_file is not explicitly provided.
    response_path = result_dir / "factory-response.json"
    response_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    if result_file and Path(result_file).resolve() != response_path.resolve():
        maybe_write_result(result_file, result)

    log_event(
        project_id=project_id,
        step=STEP_NAME,
        status=overall_status,
        mode=mode,
        run_id=run_id,
        run_attempt=run_attempt,
        error=error_summary,
    )

    print(json.dumps(result, ensure_ascii=True), flush=True)
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI-DAN Factory Orchestrator — run the full execution pipeline"
    )
    parser.add_argument("--brief-file", required=True, help="Path to BuildBrief v1 JSON file")
    parser.add_argument("--project-id", required=True, help="Project slug (e.g. my-project-001)")
    parser.add_argument(
        "--state-db",
        default="data/lifecycle.sqlite",
        help="Path to SQLite lifecycle state database",
    )
    parser.add_argument(
        "--result-dir",
        default="",
        help="Directory for per-run result JSON files (auto-created temp dir if omitted)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Execute without real side effects")
    parser.add_argument("--run-id", default="", help="Workflow run ID")
    parser.add_argument("--run-attempt", default="1", help="Workflow run attempt number")
    parser.add_argument("--workflow-url", default="", help="URL of the triggering workflow run")
    parser.add_argument(
        "--traffic-signal",
        default="LOW",
        choices=["LOW", "MEDIUM", "HIGH"],
        help="Monitoring traffic signal",
    )
    parser.add_argument(
        "--activation-metric",
        default="LOW",
        choices=["LOW", "MEDIUM", "HIGH"],
        help="Monitoring activation metric",
    )
    parser.add_argument(
        "--revenue-signal-status",
        default="NONE",
        choices=["NONE", "WEAK", "STRONG"],
        help="Monitoring revenue signal",
    )
    parser.add_argument("--template-owner", default="", help="GitHub org/user owning the template repo")
    parser.add_argument("--template-repo", default="", help="Template repository name")
    parser.add_argument("--repo-org", default="", help="GitHub org to create the project repo in")
    parser.add_argument("--result-file", default="", help="Path to write FactoryRunResult v1 JSON")
    args = parser.parse_args()

    brief_file = Path(args.brief_file).expanduser().resolve()
    if not brief_file.is_file():
        log_event(
            project_id=args.project_id or "unknown",
            step=STEP_NAME,
            status="failed",
            mode="startup",
            error=f"BuildBrief file not found: {brief_file}",
        )
        raise SystemExit(1)

    if args.result_dir:
        result_dir = Path(args.result_dir).expanduser().resolve()
    else:
        result_dir = Path(tempfile.mkdtemp(prefix=f"factory-orchestrator-{args.project_id}-"))

    result = run_pipeline(
        brief_file=brief_file,
        project_id=args.project_id,
        state_db=args.state_db,
        run_id=args.run_id or "local",
        run_attempt=args.run_attempt,
        workflow_url=args.workflow_url,
        result_dir=result_dir,
        dry_run=args.dry_run,
        traffic_signal=args.traffic_signal,
        activation_metric=args.activation_metric,
        revenue_signal_status=args.revenue_signal_status,
        template_owner=args.template_owner,
        template_repo=args.template_repo,
        repo_org=args.repo_org,
        result_file=args.result_file,
    )

    if result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
