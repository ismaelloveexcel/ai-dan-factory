#!/usr/bin/env python3
"""github_scout_agent.py – Autonomous GitHub Repository Discovery Agent.

Continuously monitors GitHub for repositories, templates, tools, and
libraries that can enhance the AI-DAN factory's build capabilities.

Modes
------
  discover    – Find trending repos in target domains
  capability  – Search for repos that fill a specific capability gap
  upgrades    – Check template dependencies for newer versions
  report      – Generate a comprehensive scout report (all modes combined)

Environment
-----------
  GITHUB_TOKEN  – Personal access token (required for higher rate limits)

Usage
-----
  python scripts/github_scout_agent.py --mode discover --domains "saas,ai,fintech"
  python scripts/github_scout_agent.py --mode capability --need "game engine nextjs"
  python scripts/github_scout_agent.py --mode upgrades
  python scripts/github_scout_agent.py --mode report --output artifacts/scout_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

DEFAULT_DOMAINS = [
    "saas template nextjs",
    "landing page generator",
    "stripe checkout template",
    "ai automation tool",
    "no-code builder",
    "react dashboard template",
    "email marketing template",
    "lead generation tool",
    "micro-saas boilerplate",
]

CAPABILITY_KEYWORDS = {
    "game": ["game engine javascript", "html5 game framework", "phaser template", "unity webgl"],
    "ecommerce": ["shopify app template", "ecommerce nextjs", "stripe store template"],
    "mobile": ["react native template", "expo boilerplate", "flutter starter"],
    "api": ["api boilerplate fastapi", "express api template", "graphql starter"],
    "ai": ["openai template", "langchain starter", "ai chatbot template"],
    "marketplace": ["marketplace template nextjs", "two-sided marketplace", "peer-to-peer platform"],
    "education": ["course platform template", "lms nextjs", "e-learning starter"],
    "fintech": ["fintech dashboard", "payment processing template", "banking api starter"],
}

TEMPLATE_DEPS_FILE = Path(__file__).resolve().parent.parent / "templates" / "saas-template" / "package.json"

MAX_RESULTS_PER_QUERY = 10
REQUEST_DELAY = 1.5  # seconds between API calls to respect rate limits


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "AI-DAN-Scout/1.0"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def _get(url: str, params: dict | None = None) -> dict:
    """Make a GET request to the GitHub API with rate-limit awareness."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            reset = e.headers.get("X-RateLimit-Reset")
            if reset:
                wait = max(0, int(reset) - int(time.time())) + 1
                print(f"[scout] Rate limited. Waiting {wait}s...", file=sys.stderr)
                time.sleep(min(wait, 60))
                return _get(url)
            print(f"[scout] 403 Forbidden: {e.read().decode()[:200]}", file=sys.stderr)
        elif e.code == 422:
            print(f"[scout] 422 Unprocessable: {e.read().decode()[:200]}", file=sys.stderr)
        else:
            print(f"[scout] HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        return {}
    except urllib.error.URLError as e:
        print(f"[scout] Network error: {e}", file=sys.stderr)
        return {}


# ---------------------------------------------------------------------------
# Core search functions
# ---------------------------------------------------------------------------

def search_repos(query: str, sort: str = "stars", max_results: int = MAX_RESULTS_PER_QUERY) -> list[dict]:
    """Search GitHub repositories and return simplified results."""
    # Add recency filter: repos updated in last 6 months
    six_months_ago = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%d")
    full_query = f"{query} pushed:>{six_months_ago}"

    data = _get(f"{GITHUB_API}/search/repositories", {
        "q": full_query,
        "sort": sort,
        "order": "desc",
        "per_page": str(max_results),
    })

    items = data.get("items", [])
    results = []
    for repo in items:
        results.append({
            "name": repo["full_name"],
            "url": repo["html_url"],
            "description": (repo.get("description") or "")[:200],
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "language": repo.get("language", "Unknown"),
            "updated": repo.get("pushed_at", ""),
            "topics": repo.get("topics", []),
            "license": (repo.get("license") or {}).get("spdx_id", "None"),
            "open_issues": repo.get("open_issues_count", 0),
        })
    return results


def discover_trending(domains: list[str]) -> dict:
    """Discover trending repos across multiple domains."""
    all_results = {}
    for domain in domains:
        print(f"[scout] Searching: {domain}", file=sys.stderr)
        repos = search_repos(domain, sort="stars")
        if repos:
            all_results[domain] = repos
        time.sleep(REQUEST_DELAY)
    return all_results


def find_capabilities(need: str) -> list[dict]:
    """Search for repos matching a specific capability need."""
    # Check if the need maps to known capability keywords
    matched_queries = []
    need_lower = need.lower()
    for category, queries in CAPABILITY_KEYWORDS.items():
        if category in need_lower:
            matched_queries.extend(queries)

    if not matched_queries:
        matched_queries = [need]

    all_repos = []
    seen = set()
    for query in matched_queries[:5]:
        print(f"[scout] Capability search: {query}", file=sys.stderr)
        repos = search_repos(query, sort="stars")
        for r in repos:
            if r["name"] not in seen:
                seen.add(r["name"])
                all_repos.append(r)
        time.sleep(REQUEST_DELAY)

    # Score by relevance
    for repo in all_repos:
        score = 0
        if repo["stars"] > 1000:
            score += 3
        elif repo["stars"] > 100:
            score += 2
        elif repo["stars"] > 10:
            score += 1
        if repo["license"] not in ("None", ""):
            score += 1
        if repo["language"] in ("TypeScript", "JavaScript", "Python"):
            score += 1
        # Bonus for having relevant topics
        need_words = set(need_lower.split())
        topic_overlap = len(need_words & set(t.lower() for t in repo["topics"]))
        score += topic_overlap
        repo["relevance_score"] = score

    all_repos.sort(key=lambda r: r["relevance_score"], reverse=True)
    return all_repos


def check_upgrades() -> dict:
    """Check current template deps against latest GitHub releases."""
    if not TEMPLATE_DEPS_FILE.exists():
        print(f"[scout] Template package.json not found at {TEMPLATE_DEPS_FILE}", file=sys.stderr)
        return {"error": "package.json not found", "upgrades": []}

    with open(TEMPLATE_DEPS_FILE) as f:
        pkg = json.load(f)

    deps = {}
    deps.update(pkg.get("dependencies", {}))
    deps.update(pkg.get("devDependencies", {}))

    upgrades = []
    key_packages = ["next", "react", "tailwindcss", "typescript", "stripe"]

    for pkg_name in key_packages:
        if pkg_name not in deps:
            continue
        current_version = deps[pkg_name].lstrip("^~>=")
        print(f"[scout] Checking {pkg_name}@{current_version}...", file=sys.stderr)

        # Check npm registry for latest
        try:
            req = urllib.request.Request(
                f"https://registry.npmjs.org/{pkg_name}/latest",
                headers={"Accept": "application/json", "User-Agent": "AI-DAN-Scout/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                latest = data.get("version", "unknown")
                if latest != current_version:
                    upgrades.append({
                        "package": pkg_name,
                        "current": current_version,
                        "latest": latest,
                        "registry": "npm",
                    })
        except Exception as e:
            print(f"[scout] Failed to check {pkg_name}: {e}", file=sys.stderr)
        time.sleep(REQUEST_DELAY)

    return {
        "checked": len(key_packages),
        "upgrades_available": len(upgrades),
        "upgrades": upgrades,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(domains: list[str], output_path: str | None = None) -> dict:
    """Generate a comprehensive scout report combining all modes."""
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent": "github-scout-v1",
        "sections": {},
    }

    # 1. Trending discoveries
    print("[scout] === Phase 1: Discovering trending repos ===", file=sys.stderr)
    trending = discover_trending(domains[:5])
    report["sections"]["trending"] = {
        "domains_searched": len(trending),
        "total_repos_found": sum(len(v) for v in trending.values()),
        "results": trending,
    }

    # 2. Capability gaps - search for common build types
    print("[scout] === Phase 2: Scanning capability gaps ===", file=sys.stderr)
    capabilities = {}
    for category in ["game", "ecommerce", "mobile"]:
        repos = find_capabilities(category)
        if repos:
            capabilities[category] = repos[:5]  # Top 5 per category
        time.sleep(REQUEST_DELAY)
    report["sections"]["capabilities"] = capabilities

    # 3. Dependency upgrades
    print("[scout] === Phase 3: Checking for upgrades ===", file=sys.stderr)
    report["sections"]["upgrades"] = check_upgrades()

    # 4. Summary & recommendations
    all_repos = []
    for domain_repos in trending.values():
        all_repos.extend(domain_repos)
    for cap_repos in capabilities.values():
        all_repos.extend(cap_repos)

    # Deduplicate and find top recommendations
    seen = set()
    top_repos = []
    for r in sorted(all_repos, key=lambda x: x.get("stars", 0), reverse=True):
        if r["name"] not in seen:
            seen.add(r["name"])
            top_repos.append(r)
        if len(top_repos) >= 10:
            break

    report["sections"]["recommendations"] = {
        "top_repos": top_repos,
        "action_items": _generate_action_items(report),
    }

    # Output
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"[scout] Report saved to {out}", file=sys.stderr)
    else:
        print(json.dumps(report, indent=2))

    return report


def _generate_action_items(report: dict) -> list[str]:
    """Generate actionable recommendations from the scout report."""
    items = []

    upgrades = report["sections"].get("upgrades", {}).get("upgrades", [])
    if upgrades:
        pkg_list = ", ".join(f"{u['package']}@{u['latest']}" for u in upgrades)
        items.append(f"UPDATE: Upgrade template dependencies: {pkg_list}")

    capabilities = report["sections"].get("capabilities", {})
    for category, repos in capabilities.items():
        if repos:
            top = repos[0]
            items.append(
                f"CAPABILITY: Consider adding {category} support. "
                f"Top repo: {top['name']} ({top['stars']}★)"
            )

    trending = report["sections"].get("trending", {}).get("results", {})
    for domain, repos in trending.items():
        if repos and repos[0]["stars"] > 5000:
            top = repos[0]
            items.append(
                f"TRENDING: {top['name']} ({top['stars']}★) in '{domain}' — "
                f"evaluate for factory integration"
            )

    if not items:
        items.append("NO_ACTION: Factory templates are current. No gaps detected.")

    return items


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AI-DAN GitHub Scout Agent")
    parser.add_argument("--mode", choices=["discover", "capability", "upgrades", "report"],
                        default="report", help="Scout mode")
    parser.add_argument("--domains", type=str, default=None,
                        help="Comma-separated search domains (for discover/report)")
    parser.add_argument("--need", type=str, default=None,
                        help="Capability need description (for capability mode)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path for report")
    args = parser.parse_args()

    if not TOKEN:
        print("[scout] WARNING: GITHUB_TOKEN not set. Rate limits will be very low.", file=sys.stderr)

    domains = args.domains.split(",") if args.domains else DEFAULT_DOMAINS

    if args.mode == "discover":
        results = discover_trending(domains)
        print(json.dumps(results, indent=2))

    elif args.mode == "capability":
        if not args.need:
            parser.error("--need is required for capability mode")
        results = find_capabilities(args.need)
        print(json.dumps(results, indent=2))

    elif args.mode == "upgrades":
        results = check_upgrades()
        print(json.dumps(results, indent=2))

    elif args.mode == "report":
        generate_report(domains, args.output)


if __name__ == "__main__":
    main()
