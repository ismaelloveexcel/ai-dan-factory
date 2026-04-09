#!/usr/bin/env python3
"""
Factory execution-plane contract definitions — BuildBrief v1 and FactoryRunResult v1.

This module is the single source of truth for:
  - contract version
  - required and optional BuildBrief v1 fields
  - FactoryRunResult v1 canonical output keys
  - monitoring signal allowed values

Import from here in factory_orchestrator, run_factory_tests, or any
finalization logic instead of duplicating definitions.

This repo is the *execution plane* — it receives BuildBrief payloads and
returns FactoryRunResult payloads.  Business and project-level truth lives in
the AI-DAN control plane (Repo 1).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Contract version
# ---------------------------------------------------------------------------

CONTRACT_VERSION = "v1"

# ---------------------------------------------------------------------------
# BuildBrief v1
# ---------------------------------------------------------------------------

# Required fields — validated by validate_brief.py before any execution
BUILD_BRIEF_V1_REQUIRED_FIELDS: tuple[str, ...] = (
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

# Optional enrichment fields — used for scoring and repo discovery when present
BUILD_BRIEF_V1_OPTIONAL_FIELDS: tuple[str, ...] = (
    "build_complexity",
    "speed_to_revenue",
    "target_user",
    "product_type",
    "preferred_language",
    "idempotency_key",
)

# ---------------------------------------------------------------------------
# FactoryRunResult v1
# ---------------------------------------------------------------------------

# Canonical top-level output keys — every factory-response.json must contain
# all of these.  Downstream consumers (AI-DAN control plane) should read
# exactly these fields.
FACTORY_RUN_RESULT_V1_KEYS: tuple[str, ...] = (
    "contract_version",
    "project_id",
    "run_id",
    "run_attempt",
    "workflow_url",
    "timestamp_utc",
    "repo_url",
    "deployment_url",
    "status",
    "run_mode",
    "idempotency_key",
    "steps",
    "deployment",
    "quality_result",
    "error_summary",
    "failure_reason",
    "kill_candidate",
    "optimize_candidate",
    "scale_candidate",
    "result_artifact",
)

# ---------------------------------------------------------------------------
# Monitoring signal allowed values
# ---------------------------------------------------------------------------

ALLOWED_TRAFFIC_SIGNALS: frozenset[str] = frozenset({"LOW", "MEDIUM", "HIGH"})
ALLOWED_ACTIVATION_METRICS: frozenset[str] = frozenset({"LOW", "MEDIUM", "HIGH"})
ALLOWED_REVENUE_SIGNALS: frozenset[str] = frozenset({"NONE", "WEAK", "STRONG"})
