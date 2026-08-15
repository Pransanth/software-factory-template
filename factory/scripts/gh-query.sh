#!/usr/bin/env bash
# Canonical, narrowly-scoped read-only GitHub/CI query helper for routine
# factory automation. Wraps factory/scripts/gh-api.sh with fixed
# subcommands so routine checks (PR status, check-runs, Actions runs/jobs,
# ruleset/required-status-check status, repo metadata, merge) never need an
# ad hoc `| python3 -c "..."` pipeline, and never need an intermediate JSON
# file that would then have to be read back with a separate, unauthorized
# tool call -- each subcommand is a single, statically recognizable command
# shape with only plain-data arguments (PR number, commit SHA, branch name,
# run id, merge method) that prints its result directly to stdout. No
# token is ever printed; the credential-helper's benign "failed to store"
# keychain-write noise (see gh-api.sh) is suppressed here so callers get
# clean output on stdout.
#
# Two flavors of read subcommand:
#   - The plain ones (repo, pr, check-runs, actions-run, actions-jobs,
#     branch-rules) print the full raw JSON response, for callers that
#     need more than the routine fields below.
#   - The "-summary" ones (and default-branch, required-checks, merge)
#     extract only the routine fields a caller actually needs for
#     PR/CI/merge verification and print them as plain "key: value" lines
#     on stdout -- no JSON parsing on the caller's side, no temp file.
#
# Usage:
#   factory/scripts/gh-query.sh repo
#   factory/scripts/gh-query.sh default-branch
#   factory/scripts/gh-query.sh pr <NUMBER>
#   factory/scripts/gh-query.sh pr-summary <NUMBER>
#   factory/scripts/gh-query.sh check-runs <SHA>
#   factory/scripts/gh-query.sh check-runs-summary <SHA>
#   factory/scripts/gh-query.sh actions-run <BRANCH>
#   factory/scripts/gh-query.sh actions-run-summary <BRANCH>
#   factory/scripts/gh-query.sh actions-jobs <RUN_ID>
#   factory/scripts/gh-query.sh actions-jobs-summary <RUN_ID>
#   factory/scripts/gh-query.sh branch-rules <BRANCH>
#   factory/scripts/gh-query.sh required-checks <BRANCH>
#   factory/scripts/gh-query.sh merge <PR_NUMBER> <MERGE_METHOD>
#   factory/scripts/gh-query.sh pr-create <TITLE> <HEAD_BRANCH> <BASE_BRANCH> <BODY>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GH_API="$SCRIPT_DIR/gh-api.sh"

if [ "$#" -lt 1 ]; then
  echo "usage: gh-query.sh {repo|default-branch|pr|pr-summary|pr-create|check-runs|check-runs-summary|actions-run|actions-run-summary|actions-jobs|actions-jobs-summary|branch-rules|required-checks|merge} [arg...]" >&2
  exit 2
fi

SUBCOMMAND="$1"
ARG="${2:-}"

case "$SUBCOMMAND" in
  repo)
    "$GH_API" GET "" 2>/dev/null
    ;;
  default-branch)
    "$GH_API" GET "" 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
print("default_branch:", data.get("default_branch"))
'
    ;;
  pr)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh pr <NUMBER>" >&2; exit 2; }
    "$GH_API" GET "/pulls/$ARG" 2>/dev/null
    ;;
  pr-summary)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh pr-summary <NUMBER>" >&2; exit 2; }
    "$GH_API" GET "/pulls/$ARG" 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
head = data.get("head", {})
base = data.get("base", {})
print("number:", data.get("number"))
print("state:", data.get("state"))
print("merged:", data.get("merged"))
print("mergeable:", data.get("mergeable"))
print("mergeable_state:", data.get("mergeable_state"))
print("head_ref:", head.get("ref"))
print("head_sha:", head.get("sha"))
print("base_ref:", base.get("ref"))
print("base_sha:", base.get("sha"))
'
    ;;
  check-runs)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh check-runs <SHA>" >&2; exit 2; }
    "$GH_API" GET "/commits/$ARG/check-runs" 2>/dev/null
    ;;
  check-runs-summary)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh check-runs-summary <SHA>" >&2; exit 2; }
    "$GH_API" GET "/commits/$ARG/check-runs" 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
runs = data.get("check_runs", [])
if not runs:
    print("no check runs yet")
for run in runs:
    print(run.get("name"), "status=" + str(run.get("status")), "conclusion=" + str(run.get("conclusion")))
'
    ;;
  actions-run)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh actions-run <BRANCH>" >&2; exit 2; }
    "$GH_API" GET "/actions/runs?branch=$ARG" 2>/dev/null
    ;;
  actions-run-summary)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh actions-run-summary <BRANCH>" >&2; exit 2; }
    "$GH_API" GET "/actions/runs?branch=$ARG" 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
runs = data.get("workflow_runs", [])
if not runs:
    print("no runs yet")
for run in runs[:5]:
    print(
        "id=" + str(run.get("id")),
        "name=" + str(run.get("name")),
        "status=" + str(run.get("status")),
        "conclusion=" + str(run.get("conclusion")),
        "head_sha=" + str(run.get("head_sha")),
    )
'
    ;;
  actions-jobs)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh actions-jobs <RUN_ID>" >&2; exit 2; }
    "$GH_API" GET "/actions/runs/$ARG/jobs" 2>/dev/null
    ;;
  actions-jobs-summary)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh actions-jobs-summary <RUN_ID>" >&2; exit 2; }
    "$GH_API" GET "/actions/runs/$ARG/jobs" 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
for job in data.get("jobs", []):
    print(job.get("name"), "status=" + str(job.get("status")), "conclusion=" + str(job.get("conclusion")))
    for step in job.get("steps", []) or []:
        print("  -", step.get("name"), "status=" + str(step.get("status")), "conclusion=" + str(step.get("conclusion")))
'
    ;;
  branch-rules)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh branch-rules <BRANCH>" >&2; exit 2; }
    "$GH_API" GET "/rules/branches/$ARG" 2>/dev/null
    ;;
  required-checks)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh required-checks <BRANCH>" >&2; exit 2; }
    "$GH_API" GET "/rules/branches/$ARG" 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
contexts = []
for rule in data:
    if rule.get("type") == "required_status_checks":
        for check in rule.get("parameters", {}).get("required_status_checks", []):
            contexts.append(check.get("context"))
if not contexts:
    print("no required status checks configured")
for context in contexts:
    print("required_status_check:", context)
'
    ;;
  merge)
    PR_NUMBER="$ARG"
    MERGE_METHOD="${3:-squash}"
    [ -n "$PR_NUMBER" ] || { echo "usage: gh-query.sh merge <PR_NUMBER> <MERGE_METHOD>" >&2; exit 2; }
    "$GH_API" PUT "/pulls/$PR_NUMBER/merge" "{\"merge_method\":\"$MERGE_METHOD\"}" 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
print("merged:", data.get("merged"))
print("sha:", data.get("sha"))
print("message:", data.get("message"))
'
    ;;
  pr-create)
    PR_TITLE="${2:-}"
    PR_HEAD="${3:-}"
    PR_BASE="${4:-}"
    PR_BODY="${5:-}"
    if [ -z "$PR_TITLE" ] || [ -z "$PR_HEAD" ] || [ -z "$PR_BASE" ]; then
      echo "usage: gh-query.sh pr-create <TITLE> <HEAD_BRANCH> <BASE_BRANCH> <BODY>" >&2
      exit 2
    fi
    PR_PAYLOAD="$(python3 -c '
import json, sys
title, head, base, body = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ""
print(json.dumps({"title": title, "head": head, "base": base, "body": body}))
' "$PR_TITLE" "$PR_HEAD" "$PR_BASE" "$PR_BODY")"
    "$GH_API" POST /pulls "$PR_PAYLOAD" 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
print("number:", data.get("number"))
print("html_url:", data.get("html_url"))
print("state:", data.get("state"))
head = data.get("head") or {}
print("head_sha:", head.get("sha"))
'
    ;;
  *)
    echo "ERROR: unknown subcommand '$SUBCOMMAND'" >&2
    exit 2
    ;;
esac
