#!/usr/bin/env python3
"""
Repo Discovery Engine — GitHub repository search, scoring, and template selection.

Before building a product from scratch, the factory searches GitHub for relevant
starter repos/templates.  If a high-quality match exists the factory can reuse it
instead of generating everything internally.

Responsibilities:
  1. Accept a search intent derived from the BuildBrief (product name, problem,
     solution, keywords).
  2. Query the GitHub Search API for candidate repositories.
  3. Score and rank candidates using a deterministic scoring function.
  4. Select the best option: REUSE_EXTERNAL_TEMPLATE, USE_INTERNAL_TEMPLATE, or
     BUILD_MINIMAL_INTERNAL.
  5. Persist the decision and audit trail to a result file.
  6. Fall back gracefully when the API is unavailable or returns no results.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory_utils import log_event, maybe_write_result, utc_timestamp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEP_NAME = "repo_discovery"

# Minimum composite score for the *best* external candidate to beat the internal
# template.  If the best external repo scores below this, the factory keeps using
# its own template.
EXTERNAL_PREFERENCE_THRESHOLD = 70.0

# Maximum number of search results to evaluate per query.
MAX_CANDIDATES = 20

# Selection modes (persisted in the result).
MODE_REUSE_EXTERNAL = "REUSE_EXTERNAL_TEMPLATE"
MODE_USE_INTERNAL = "USE_INTERNAL_TEMPLATE"
MODE_BUILD_MINIMAL = "BUILD_MINIMAL_INTERNAL"

# GitHub Search API base URL.
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

# Days after which a repo is considered stale.
STALE_DAYS = 365

# Keywords that indicate a template-oriented repository.
TEMPLATE_KEYWORDS = frozenset(
    {
        "template",
        "starter",
        "boilerplate",
        "scaffold",
        "skeleton",
        "seed",
        "quickstart",
        "kickstart",
    }
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DiscoveryError(Exception):
    """Non-retryable error during repo discovery."""


# ---------------------------------------------------------------------------
# Search-intent extraction
# ---------------------------------------------------------------------------


def build_search_query(brief: dict[str, Any]) -> str:
    """Derive a GitHub search query from the BuildBrief fields."""
    parts: list[str] = []

    product_name = str(brief.get("product_name", "")).strip()
    solution = str(brief.get("solution", "")).strip()
    problem = str(brief.get("problem", "")).strip()

    # Prefer short, targeted tokens from solution / product_name.
    for raw in (solution, product_name, problem):
        tokens = _extract_keywords(raw)
        if tokens:
            parts.extend(tokens[:4])
        if len(parts) >= 6:
            break

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for tok in parts:
        lower = tok.lower()
        if lower not in seen:
            seen.add(lower)
            unique.append(tok)

    if not unique:
        unique = ["starter", "template"]

    # Append "template OR starter" to bias toward reusable repos.
    query = " ".join(unique[:6]) + " template OR starter"
    return query


_STOP_WORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "and", "but", "or",
        "nor", "not", "no", "so", "if", "of", "at", "by", "for", "with",
        "about", "to", "from", "in", "on", "up", "out", "as", "into", "that",
        "this", "it", "its", "they", "them", "their", "we", "our", "you",
        "your", "he", "she", "him", "her", "who", "which", "what", "when",
        "where", "how", "all", "each", "every", "both", "few", "more", "most",
        "some", "any", "only", "very", "just", "than", "too", "also", "need",
        "way", "users", "simple", "using",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9][\w-]*")


def _extract_keywords(text: str) -> list[str]:
    """Return meaningful tokens from *text*, excluding stop-words."""
    tokens = _TOKEN_RE.findall(text)
    return [t for t in tokens if t.lower() not in _STOP_WORDS and len(t) > 2]


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------


def search_github(
    query: str,
    *,
    token: str,
    max_results: int = MAX_CANDIDATES,
    timeout: int = 15,
) -> tuple[list[dict[str, Any]], str]:
    """Search GitHub repositories.

    Returns ``(results, error)`` where *error* is an empty string on success
    or a description of the failure.  The caller uses *error* to populate
    ``api_error`` / ``fallback_used`` in the result payload.
    """
    params = urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": min(max_results, 100)}
    )
    url = f"{GITHUB_SEARCH_URL}?{params}"

    request = urllib.request.Request(url=url, method="GET")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        return [], str(exc)

    items: list[dict[str, Any]] = data.get("items", [])
    results: list[dict[str, Any]] = []
    for item in items[:max_results]:
        results.append(_normalize_repo(item))
    return results, ""


def _normalize_repo(item: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalize metadata from a GitHub search result item."""
    return {
        "full_name": str(item.get("full_name", "")),
        "description": str(item.get("description") or ""),
        "stars": int(item.get("stargazers_count", 0)),
        "language": str(item.get("language") or ""),
        "updated_at": str(item.get("updated_at", "")),
        "topics": list(item.get("topics") or []),
        "html_url": str(item.get("html_url", "")),
        "is_template": bool(item.get("is_template", False)),
        "archived": bool(item.get("archived", False)),
        "fork": bool(item.get("fork", False)),
        "open_issues_count": int(item.get("open_issues_count", 0)),
        "license": str((item.get("license") or {}).get("spdx_id", "") or ""),
        "size": int(item.get("size", 0)),
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_candidate(
    repo: dict[str, Any],
    *,
    search_query: str,
    preferred_language: str = "",
) -> float:
    """Return a composite score (0–100) for *repo*.

    Dimensions:
      - relevance   (0-30)  keyword overlap with search query
      - popularity  (0-20)  GitHub stars
      - recency     (0-15)  last update freshness
      - template    (0-15)  is_template flag + topic/name signals
      - tech_fit    (0-10)  language match
      - simplicity  (0-10)  low open issues, reasonable size
    """
    if repo.get("archived"):
        return 0.0
    if repo.get("fork"):
        return 0.0

    relevance = _score_relevance(repo, search_query)
    popularity = _score_popularity(repo)
    recency = _score_recency(repo)
    template = _score_template_suitability(repo)
    tech_fit = _score_tech_fit(repo, preferred_language)
    simplicity = _score_simplicity(repo)

    return round(relevance + popularity + recency + template + tech_fit + simplicity, 2)


def _score_relevance(repo: dict[str, Any], query: str) -> float:
    """0-30 based on keyword overlap between query and repo metadata."""
    query_tokens = {t.lower() for t in _TOKEN_RE.findall(query) if len(t) > 2}
    if not query_tokens:
        return 0.0

    name_tokens = {t.lower() for t in _TOKEN_RE.findall(repo.get("full_name", ""))}
    desc_tokens = {t.lower() for t in _TOKEN_RE.findall(repo.get("description", ""))}
    topic_tokens = {t.lower() for t in repo.get("topics", [])}

    all_repo_tokens = name_tokens | desc_tokens | topic_tokens
    overlap = query_tokens & all_repo_tokens
    ratio = len(overlap) / len(query_tokens)
    return round(min(ratio * 30, 30), 2)


def _score_popularity(repo: dict[str, Any]) -> float:
    """0-20 based on stars.  Uses log scale to avoid mega-repos dominating."""
    stars = max(repo.get("stars", 0), 0)
    if stars == 0:
        return 0.0
    # log10(100)=2 → 10, log10(10000)=4 → 20
    return round(min(math.log10(stars + 1) * 5, 20), 2)


def _score_recency(repo: dict[str, Any]) -> float:
    """0-15 based on how recently the repo was updated."""
    updated_str = repo.get("updated_at", "")
    if not updated_str:
        return 0.0
    try:
        updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return 0.0
    now = datetime.now(timezone.utc)
    days_ago = max((now - updated).days, 0)
    if days_ago > STALE_DAYS:
        return 0.0
    return round(15 * (1 - days_ago / STALE_DAYS), 2)


def _score_template_suitability(repo: dict[str, Any]) -> float:
    """0-15 based on whether the repo looks like a template/starter."""
    score = 0.0
    if repo.get("is_template"):
        score += 8.0

    name_lower = repo.get("full_name", "").lower()
    desc_lower = repo.get("description", "").lower()
    topics = {t.lower() for t in repo.get("topics", [])}

    text = f"{name_lower} {desc_lower} {' '.join(topics)}"
    hits = sum(1 for kw in TEMPLATE_KEYWORDS if kw in text)
    score += min(hits * 2.5, 7.0)

    return round(min(score, 15), 2)


def _score_tech_fit(repo: dict[str, Any], preferred_language: str) -> float:
    """0-10 based on language match."""
    if not preferred_language:
        return 5.0  # neutral when no preference
    repo_lang = (repo.get("language") or "").strip().lower()
    if not repo_lang:
        return 0.0
    if repo_lang == preferred_language.lower():
        return 10.0
    return 2.0  # partial credit for having any non-matching language


def _score_simplicity(repo: dict[str, Any]) -> float:
    """0-10 — prefer smaller, lower-issue repos (good for one-person operation)."""
    score = 10.0
    issues = repo.get("open_issues_count", 0)
    if issues > 100:
        score -= 5.0
    elif issues > 30:
        score -= 2.0

    size_kb = repo.get("size", 0)
    if size_kb > 500_000:  # >500 MB
        score -= 5.0
    elif size_kb > 100_000:  # >100 MB
        score -= 2.0

    return max(round(score, 2), 0.0)


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------


def select_template(
    candidates: list[dict[str, Any]],
    *,
    search_query: str,
    preferred_language: str = "",
    has_internal_template: bool = True,
) -> dict[str, Any]:
    """Score candidates and select the best option.

    Returns a dict with:
      - selection_mode
      - selected_repo  (or None)
      - selection_reason
      - scored_candidates  (list of {repo, score})
    """
    scored: list[dict[str, Any]] = []
    for repo in candidates:
        score = score_candidate(
            repo,
            search_query=search_query,
            preferred_language=preferred_language,
        )
        scored.append({"repo": repo, "score": score})

    # Sort descending by score.
    scored.sort(key=lambda x: x["score"], reverse=True)

    best = scored[0] if scored else None

    if best and best["score"] >= EXTERNAL_PREFERENCE_THRESHOLD:
        return {
            "selection_mode": MODE_REUSE_EXTERNAL,
            "selected_repo": best["repo"],
            "selected_score": best["score"],
            "selection_reason": (
                f"External repo '{best['repo']['full_name']}' scored "
                f"{best['score']:.1f} (>= {EXTERNAL_PREFERENCE_THRESHOLD}), "
                f"suitable for reuse."
            ),
            "scored_candidates": scored,
        }

    if has_internal_template:
        reason = f"No external repo met the preference threshold ({EXTERNAL_PREFERENCE_THRESHOLD})"
        if best:
            reason += (
                f" (best: '{best['repo']['full_name']}' scored "
                f"{best['score']:.1f} < {EXTERNAL_PREFERENCE_THRESHOLD})"
            )
        reason += "; using internal template."
        return {
            "selection_mode": MODE_USE_INTERNAL,
            "selected_repo": None,
            "selected_score": 0.0,
            "selection_reason": reason,
            "scored_candidates": scored,
        }

    return {
        "selection_mode": MODE_BUILD_MINIMAL,
        "selected_repo": None,
        "selected_score": 0.0,
        "selection_reason": "No suitable external repo and no internal template available; building minimal internal.",
        "scored_candidates": scored,
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover GitHub repos/templates before building from scratch."
    )
    parser.add_argument(
        "--brief-file", required=True, help="Path to the normalized BuildBrief JSON."
    )
    parser.add_argument(
        "--result-file", default="", help="Path to write step result JSON."
    )
    parser.add_argument(
        "--project-id", required=True, help="Project identifier."
    )
    parser.add_argument(
        "--preferred-language",
        default="",
        help="Preferred programming language (e.g. JavaScript, TypeScript, Python).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip live GitHub API call; simulate empty search results.",
    )
    parser.add_argument(
        "--no-internal-template",
        action="store_true",
        default=False,
        help="Indicate that no internal template is available.",
    )
    args = parser.parse_args()

    project_id = args.project_id.strip()
    mode = "dry_run" if args.dry_run else "production"

    log_event(project_id=project_id, step=STEP_NAME, status="started", mode=mode)

    try:
        brief_path = Path(args.brief_file).expanduser().resolve()
        if not brief_path.is_file():
            raise DiscoveryError(f"Brief file not found: {brief_path}")
        brief: dict[str, Any] = json.loads(brief_path.read_text(encoding="utf-8"))

        search_query = build_search_query(brief)

        candidates: list[dict[str, Any]] = []
        api_error: str = ""

        if args.dry_run:
            candidates = []
        else:
            token = os.environ.get("FACTORY_GITHUB_TOKEN", "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
            try:
                candidates, api_error = search_github(search_query, token=token)
            except Exception as exc:  # noqa: BLE001 — intentional broad catch for resilience
                api_error = str(exc)
                candidates = []
            if api_error:
                log_event(
                    project_id=project_id,
                    step=STEP_NAME,
                    status="warning",
                    mode=mode,
                    error=f"GitHub API search failed: {api_error}",
                )
                candidates = []

        selection = select_template(
            candidates,
            search_query=search_query,
            preferred_language=args.preferred_language,
            has_internal_template=not args.no_internal_template,
        )

        # Build tracking payload.
        repos_considered = [
            {
                "full_name": s["repo"]["full_name"],
                "html_url": s["repo"]["html_url"],
                "score": s["score"],
            }
            for s in selection["scored_candidates"]
        ]

        result_payload: dict[str, Any] = {
            "project_id": project_id,
            "step": STEP_NAME,
            "status": "success",
            "mode": mode,
            "search_query": search_query,
            "repos_considered": repos_considered,
            "repos_considered_count": len(repos_considered),
            "selected_repo": (
                selection["selected_repo"]["full_name"]
                if selection["selected_repo"]
                else None
            ),
            "selected_repo_url": (
                selection["selected_repo"]["html_url"]
                if selection["selected_repo"]
                else None
            ),
            "selected_score": selection["selected_score"],
            "selection_mode": selection["selection_mode"],
            "selection_reason": selection["selection_reason"],
            "timestamp": utc_timestamp(),
        }

        if api_error:
            result_payload["api_error"] = api_error
            result_payload["fallback_used"] = True

        maybe_write_result(args.result_file, result_payload)
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="success",
            mode=mode,
            selection_mode=selection["selection_mode"],
            selection_reason=selection["selection_reason"],
            search_query=search_query,
            repos_considered_count=len(repos_considered),
        )

    except DiscoveryError as exc:
        error_message = str(exc)
        maybe_write_result(
            args.result_file,
            {
                "project_id": project_id,
                "step": STEP_NAME,
                "status": "failed",
                "mode": mode,
                "error": error_message,
                "timestamp": utc_timestamp(),
            },
        )
        log_event(
            project_id=project_id,
            step=STEP_NAME,
            status="failed",
            mode=mode,
            error=error_message,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
