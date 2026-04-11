#!/usr/bin/env python3
"""Apply surgical fixes to aidan-managing-director/main.py"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request

TOKEN = os.environ.get("GH_TOKEN", "")
if not TOKEN:
    print("ERROR: GH_TOKEN not set!", file=sys.stderr)
    sys.exit(1)

OWNER = "ismaelloveexcel"
REPO = "aidan-managing-director"
PATH = "main.py"
BRANCH = "main"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
}

url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{PATH}"
req = urllib.request.Request(url, headers=HEADERS)
with urllib.request.urlopen(req) as r:
    data = json.load(r)
sha = data["sha"]
content = base64.b64decode(data["content"]).decode("utf-8")
print(f"Fetched {len(content)} chars (sha={sha[:8]})")

def rep(label, old, new):
    global content
    if old not in content:
        print(f"  SKIP {label}")
        return
    content = content.replace(old, new, 1)
    print(f"  OK   {label}")

# Fix 1: API field names
rep("submitAnalysis field names",
    "  const payload = {\n    description: desc,\n    problem: document.getElementById('idea-problem').value.trim(),\n    target_user: document.getElementById('idea-user').value.trim(),\n    monetization: document.getElementById('idea-mono').value,\n    competition: document.getElementById('idea-comp').value,\n    time_to_revenue: document.getElementById('idea-ttr').value,\n    differentiation: document.getElementById('idea-diff').value.trim(),\n  };\n\n  apiFetch('/api/analyze', {method:'POST', body: JSON.stringify(payload)})",
    "  const payload = {\n    idea: desc,\n    problem: document.getElementById('idea-problem').value.trim(),\n    target_user: document.getElementById('idea-user').value.trim(),\n    monetization_model: document.getElementById('idea-mono').value,\n    competition_level: document.getElementById('idea-comp').value,\n    time_to_revenue: document.getElementById('idea-ttr').value,\n    differentiation: document.getElementById('idea-diff').value.trim(),\n  };\n\n  apiFetch('/api/analyze/', {method:'POST', body: JSON.stringify(payload)})")

# Fix 2: Response field mapping
rep("renderAnalysisResult decision field",
    "  const decision = (d.decision || d.verdict || 'HOLD').toUpperCase();\n  const scores = d.scores || {};\n  const overall = scores.overall || d.overall_score || 0;",
    "  const decision = (d.final_decision || d.score_decision || d.decision || d.verdict || 'HOLD').toUpperCase();\n  const scores = d.score_breakdown || d.scores || {};\n  const overall = d.total_score || scores.overall || d.overall_score || 0;")

# Fix 3: next_step
rep("next_step field",
    "    APPROVED: (d.next_move || 'Start building the MVP immediately.'),\n    HOLD: (d.next_move || 'Validate the idea with 5 real users before building.'),\n    REJECTED: (d.next_move || 'Move on. Your time is too valuable for this one.'),",
    "    APPROVED: (d.next_step || d.next_move || 'Start building the MVP immediately.'),\n    HOLD: (d.next_step || d.next_move || 'Validate the idea with 5 real users before building.'),\n    REJECTED: (d.next_step || d.next_move || 'Move on. Your time is too valuable for this one.'),")

# Fix 4: offer->brief
rep("offer->brief",
    "  const brief = d.business_brief || d.brief || {};",
    "  const brief = d.offer || d.business_brief || d.brief || {};")

# Fix 5: validation blockers
old5 = "  let warnHtml = '';\n  if (lowScores.length > 0) {\n    warnHtml = '<div class=\"alert alert-warn\">&#9888; Low scores: ' +"
new5 = "  let validHtml = '';\n  const blockers = d.validation_blocking || [];\n  if (blockers.length) {\n    validHtml = '<div class=\"alert alert-error\" style=\"margin-bottom:.5rem\"><strong>&#9888; Blockers:</strong><ul style=\"margin:.3rem 0 0 1rem;padding:0\">' +\n      blockers.map(function(b){return '<li>'+esc(b)+'</li>';}).join('') + '</ul></div>';\n  }\n\n  let warnHtml = '';\n  if (lowScores.length > 0) {\n    warnHtml = '<div class=\"alert alert-warn\">&#9888; Low scores: ' +"
rep("validation blockers display", old5, new5)

# Fix 5b: include validHtml in result card
rep("validHtml in result card",
    "      warnHtml +\n      barsHtml +",
    "      validHtml +\n      warnHtml +\n      barsHtml +")

# Fix 6: factory trigger dry_run
rep("factory trigger dry_run",
    "JSON.stringify({project_name: name})})",
    "JSON.stringify({project_name: name, dry_run: false})})")  

print(f"Final size: {len(content)} chars")

encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
payload = json.dumps({
    "message": "fix: API field names, response mapping, validation display, factory trigger\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>",
    "content": encoded,
    "sha": sha,
    "branch": BRANCH,
}).encode("utf-8")
req2 = urllib.request.Request(url, data=payload, headers=HEADERS, method="PUT")
try:
    with urllib.request.urlopen(req2) as r2:
        result = json.load(r2)
    print(f"SUCCESS: {result['commit']['html_url']}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}: {body[:300]}", file=sys.stderr)
    sys.exit(1)
