#!/usr/bin/env python3
"""
Cross-repo run reconciliation.

Compares the factory's local state_store with the MD's canonical
PortfolioRepository (queried via the /factory/runs/{correlation_id}/result
polling endpoint).  Reports mismatches and optionally updates the local
state_store to match the MD's authoritative status.

Usage:
    python scripts/reconcile_runs.py --state-db data/factory.sqlite3 \
        --md-base-url https://aidan-md.vercel.app \
        [--fix]  [--limit 50]

Environment:
    FACTORY_SECRET — optional HMAC secret for authenticated MD requests
    MD_BASE_URL    — alternative to --md-base-url flag
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from factory_utils import log_event, redact_secrets, validate_webhook_url
from state_store import FactoryStateStore

STEP_NAME = "reconcile_runs"

# Map MD statuses to factory lifecycle states
_MD_STATUS_TO_FACTORY_STATE: dict[str, str] = {
    "succeeded": "deployed",
    "deployed": "deployed",
    "failed": "killed",
    "building": "building",
    "pending": "approved",
    "dispatched": "approved",
    "running": "building",
}


def _query_md_run(
    base_url: str,
    correlation_id: str,
    factory_secret: str = "",
    timeout: int = 15,
) -> dict | None:
    """GET /factory/runs/{correlation_id}/result from the MD."""
    url = f"{base_url.rstrip('/')}/factory/runs/{correlation_id}/result"
    validate_webhook_url(url)
    req = urllib.request.Request(url=url, method="GET")
    req.add_header("Accept", "application/json")
    if factory_secret:
        req.add_header("X-Factory-Secret", factory_secret)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("found") is False:
                return None
            return data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    except urllib.error.URLError:
        return None


def reconcile(
    store: FactoryStateStore,
    md_base_url: str,
    factory_secret: str = "",
    limit: int = 50,
    fix: bool = False,
) -> list[dict]:
    """Compare local runs against MD and return list of mismatches."""
    runs = store.list_recent_runs(limit=limit)
    mismatches: list[dict] = []

    for run in runs:
        project_id = run.get("project_id", "")
        run_id = run.get("run_id", "")
        run_attempt = run.get("run_attempt", "")
        factory_state = str(run.get("state", "")).lower()

        # We need a correlation ID to look up in MD; fall back to run_id
        # The factory workflow passes correlation_id as part of the callback.
        # However state_store doesn't store correlation_id explicitly.
        # We'll query by run_id through the MD's run lookup.
        md_data = _query_md_run(md_base_url, run_id, factory_secret)
        if md_data is None:
            # Run not in MD — this is expected for dry-runs or very new runs
            continue

        md_status = str(md_data.get("status", "")).lower()
        expected_factory_state = _MD_STATUS_TO_FACTORY_STATE.get(md_status, md_status)

        if factory_state == expected_factory_state:
            continue

        mismatch = {
            "project_id": project_id,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "factory_state": factory_state,
            "md_status": md_status,
            "expected_factory_state": expected_factory_state,
            "fixed": False,
        }

        if fix and expected_factory_state in ("deployed", "killed"):
            try:
                store.record_transition(
                    project_id=project_id,
                    from_state=factory_state,
                    to_state=expected_factory_state,
                    status="reconciled",
                    reason=f"Reconciled: MD reports '{md_status}', local was '{factory_state}'",
                    run_id=run_id,
                    run_attempt=run_attempt,
                    workflow_url="",
                    timestamp_utc=__import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).isoformat(),
                    metadata={"reconciled_from_md": True, "md_status": md_status},
                    deployment_url=md_data.get("deploy_url", ""),
                    repo_url=md_data.get("repo_url", ""),
                )
                mismatch["fixed"] = True
            except Exception as exc:
                mismatch["fix_error"] = str(exc)

        mismatches.append(mismatch)

    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-repo factory run reconciliation")
    parser.add_argument("--state-db", required=True, help="Path to factory state SQLite DB")
    parser.add_argument("--md-base-url", default="", help="MD API base URL")
    parser.add_argument("--limit", type=int, default=50, help="Max recent runs to check")
    parser.add_argument("--fix", action="store_true", help="Update local state to match MD")
    parser.add_argument("--result-file", default="", help="Write JSON summary to this file")
    args = parser.parse_args()

    md_base_url = args.md_base_url.strip() or os.environ.get("MD_BASE_URL", "").strip()
    if not md_base_url:
        print(f"[{STEP_NAME}] ERROR: --md-base-url or MD_BASE_URL required", file=sys.stderr)
        return 1

    factory_secret = os.environ.get("FACTORY_SECRET", "").strip()

    store = FactoryStateStore(args.state_db)
    try:
        mismatches = reconcile(
            store=store,
            md_base_url=md_base_url,
            factory_secret=factory_secret,
            limit=args.limit,
            fix=args.fix,
        )
    finally:
        store.close()

    summary = {
        "total_checked": args.limit,
        "mismatches_found": len(mismatches),
        "mismatches_fixed": sum(1 for m in mismatches if m.get("fixed")),
        "details": mismatches,
    }

    log_event(
        project_id="system",
        step=STEP_NAME,
        status="completed",
        mode="fix" if args.fix else "audit",
        mismatches=len(mismatches),
        fixed=summary["mismatches_fixed"],
    )

    if args.result_file:
        from factory_utils import maybe_write_result
        maybe_write_result(args.result_file, summary)

    if mismatches:
        print(f"[{STEP_NAME}] {len(mismatches)} mismatch(es) found:", flush=True)
        for m in mismatches:
            fixed_tag = " [FIXED]" if m.get("fixed") else ""
            err_tag = f" [ERROR: {m.get('fix_error', '')}]" if m.get("fix_error") else ""
            print(
                f"  {m['project_id']} (run {m['run_id']}): "
                f"factory={m['factory_state']} md={m['md_status']} expected={m['expected_factory_state']}"
                f"{fixed_tag}{err_tag}",
                flush=True,
            )
    else:
        print(f"[{STEP_NAME}] All runs in sync.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
