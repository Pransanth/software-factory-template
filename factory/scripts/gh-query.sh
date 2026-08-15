#!/usr/bin/env bash
# Canonical, narrowly-scoped GitHub/CI query helper for routine factory
# automation. Wraps factory/scripts/gh-api.sh with fixed subcommands so
# routine checks never need an ad hoc `| python3 -c "..."` pipeline and never
# need an intermediate JSON file -- each subcommand is a single, statically
# recognizable command shape with only plain-data arguments (PR number,
# commit SHA, branch name, run id, merge method) that prints "key: value"
# lines on stdout. No token is ever printed.
#
# All answer interpretation lives in factory/guards/gh_evidence.py, not in
# inline snippets here. That module has its own tests
# (factory/guards/test_gh_evidence.py), which is the only way the failure
# modes below can be regression-tested without a network.
#
# Three audit findings shaped the current interface:
#
#   F-07: an API error used to be indistinguishable from an empty normal
#   state ("no check runs yet" for a 401 or a rate limit). Every subcommand
#   now propagates a non-zero exit code and prints `api_error: ...`.
#
#   F-08: the merge decision used to be made by reading an unfiltered list of
#   check-run names as prose. `required-check` gives exactly one verdict and
#   one exit code for one exact SHA and one exact check name, and handles
#   queued/in_progress/cancelled/skipped/neutral/stale, several runs sharing
#   the name (normal here: factory-ci.yml triggers on push AND pull_request),
#   and incomplete pagination.
#
#   F-08: `merge` now REQUIRES the head SHA that was actually verified. It is
#   checked locally first and then passed to GitHub's merge API as `sha`, so
#   a push that landed after the CI/review evidence was collected makes the
#   merge fail server-side instead of silently riding along.
#
# Usage:
#   factory/scripts/gh-query.sh repo
#   factory/scripts/gh-query.sh default-branch
#   factory/scripts/gh-query.sh pr <NUMBER>
#   factory/scripts/gh-query.sh pr-summary <NUMBER>
#   factory/scripts/gh-query.sh pr-create <TITLE> <HEAD_BRANCH> <BASE_BRANCH> <BODY>
#   factory/scripts/gh-query.sh check-runs <SHA>
#   factory/scripts/gh-query.sh check-runs-summary <SHA>
#   factory/scripts/gh-query.sh required-check <SHA> [CHECK_NAME]
#   factory/scripts/gh-query.sh actions-run <BRANCH>
#   factory/scripts/gh-query.sh actions-run-summary <BRANCH>
#   factory/scripts/gh-query.sh actions-jobs <RUN_ID>
#   factory/scripts/gh-query.sh actions-jobs-summary <RUN_ID>
#   factory/scripts/gh-query.sh branch-rules <BRANCH>
#   factory/scripts/gh-query.sh required-checks <BRANCH>
#   factory/scripts/gh-query.sh merge <PR_NUMBER> <MERGE_METHOD> <EXPECTED_HEAD_SHA>
#
# Added by the operational-robustness package:
#   factory/scripts/gh-query.sh pr-for-branch <BRANCH>          (F-16, resume)
#   factory/scripts/gh-query.sh pr-permission-probe <BRANCH>    (F-12)
#   factory/scripts/gh-query.sh ruleset-guarantees <BRANCH> [CHECK_NAME]  (F-13)
#   factory/scripts/gh-query.sh classic-protection <BRANCH> [CHECK_NAME]  (F-13)
#
# Exit codes for `required-check`: 0 success, 1 failed, 2 pending,
# 3 absent, 4 api_error. Only 0 may lead to a merge.
#
# Exit codes for `pr-for-branch`: 0 a pull request exists, 3 none exists,
# 4 api_error. "No pull request yet" is a normal answer with its own code and
# must never be confused with a failed query -- that distinction is the whole
# point of resuming safely after a crashed session.
#
# Exit codes for `pr-permission-probe`: 0 permitted, 1 blocked (including an
# unexpectedly created pull request), 4 api_error. Anything that is not
# GitHub's own validation error is blocked, on purpose: the previous version
# classified by exclusion and reported a 401 or a 404 as "permitted".
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GH_API="$SCRIPT_DIR/gh-api.sh"
GH_EVIDENCE="$SCRIPT_DIR/../guards/gh_evidence.py"

DEFAULT_REQUIRED_CHECK="${FACTORY_REQUIRED_CHECK:-factory-checks}"

API_BODY=""
API_RC=0

usage() {
  echo "usage: gh-query.sh {repo|default-branch|pr|pr-summary|pr-create|pr-for-branch|pr-permission-probe|check-runs|check-runs-summary|required-check|actions-run|actions-run-summary|actions-jobs|actions-jobs-summary|branch-rules|required-checks|ruleset-guarantees|classic-protection|merge} [arg...]" >&2
  exit 2
}

# Run gh-api.sh, keeping both its body and its exit code. The body is kept
# even on failure: it carries GitHub's own error message, which the evidence
# module renders as `api_error: ...`.
api_call() {
  API_BODY="$("$GH_API" "$@" 2>/dev/null)"
  API_RC=$?
}

# Feed the captured body to the evidence module and exit with a code that is
# non-zero whenever either layer failed.
render() {
  local rendered_rc
  printf '%s' "$API_BODY" | python3 "$GH_EVIDENCE" "$@"
  rendered_rc=$?
  if [ "$API_RC" -ne 0 ] && [ "$rendered_rc" -eq 0 ]; then
    echo "api_error: gh-api.sh endete mit Exit $API_RC."
    return 4
  fi
  return "$rendered_rc"
}

# Like render(), but WITHOUT the "gh-api.sh failed, so this is an api_error"
# override. Used only by the modes that are given gh-api.sh's exit code
# explicitly and interpret it themselves -- the PR permission probe, where an
# HTTP error is the expected and informative answer, and classic branch
# protection, where a 404 means "no classic protection", a legitimate state.
render_raw() {
  printf '%s' "$API_BODY" | python3 "$GH_EVIDENCE" "$@"
}

# OWNER of the repository origin points at, for endpoints that need
# `head=OWNER:BRANCH`. Derived through gh-api.sh's own normalisation and
# validation (F-17) rather than by re-parsing the remote URL here.
repo_owner() {
  local slug_line slug
  slug_line="$("$GH_API" slug 2>/dev/null | /usr/bin/grep '^slug:' || true)"
  slug="${slug_line#slug: }"
  if [ -z "$slug" ] || [ "$slug" = "$slug_line" ]; then
    echo "api_error: OWNER liess sich nicht aus origin ableiten." >&2
    return 4
  fi
  printf '%s' "${slug%%/*}"
}

require_arg() {
  [ -n "$1" ] || { echo "$2" >&2; exit 2; }
}

[ "$#" -ge 1 ] || usage

SUBCOMMAND="$1"
ARG="${2:-}"

case "$SUBCOMMAND" in
  repo)
    api_call GET ""
    printf '%s\n' "$API_BODY"
    exit "$API_RC"
    ;;
  pr)
    require_arg "$ARG" "usage: gh-query.sh pr <NUMBER>"
    api_call GET "/pulls/$ARG"
    printf '%s\n' "$API_BODY"
    exit "$API_RC"
    ;;
  check-runs)
    require_arg "$ARG" "usage: gh-query.sh check-runs <SHA>"
    api_call GET "/commits/$ARG/check-runs?per_page=100"
    printf '%s\n' "$API_BODY"
    exit "$API_RC"
    ;;
  actions-run)
    require_arg "$ARG" "usage: gh-query.sh actions-run <BRANCH>"
    api_call GET "/actions/runs?branch=$ARG&per_page=100"
    printf '%s\n' "$API_BODY"
    exit "$API_RC"
    ;;
  actions-jobs)
    require_arg "$ARG" "usage: gh-query.sh actions-jobs <RUN_ID>"
    api_call GET "/actions/runs/$ARG/jobs?per_page=100"
    printf '%s\n' "$API_BODY"
    exit "$API_RC"
    ;;
  branch-rules)
    require_arg "$ARG" "usage: gh-query.sh branch-rules <BRANCH>"
    api_call GET "/rules/branches/$ARG"
    printf '%s\n' "$API_BODY"
    exit "$API_RC"
    ;;

  default-branch)
    api_call GET ""
    render repo-default-branch
    exit $?
    ;;
  pr-summary)
    require_arg "$ARG" "usage: gh-query.sh pr-summary <NUMBER>"
    api_call GET "/pulls/$ARG"
    render pr-summary
    exit $?
    ;;
  check-runs-summary)
    require_arg "$ARG" "usage: gh-query.sh check-runs-summary <SHA>"
    api_call GET "/commits/$ARG/check-runs?per_page=100"
    render check-runs-summary
    exit $?
    ;;
  required-check)
    require_arg "$ARG" "usage: gh-query.sh required-check <SHA> [CHECK_NAME]"
    CHECK_NAME="${3:-$DEFAULT_REQUIRED_CHECK}"
    api_call GET "/commits/$ARG/check-runs?per_page=100"
    render required-check "$CHECK_NAME"
    exit $?
    ;;
  actions-run-summary)
    require_arg "$ARG" "usage: gh-query.sh actions-run-summary <BRANCH>"
    api_call GET "/actions/runs?branch=$ARG&per_page=100"
    render actions-run-summary
    exit $?
    ;;
  actions-jobs-summary)
    require_arg "$ARG" "usage: gh-query.sh actions-jobs-summary <RUN_ID>"
    api_call GET "/actions/runs/$ARG/jobs?per_page=100"
    render actions-jobs-summary
    exit $?
    ;;
  required-checks)
    require_arg "$ARG" "usage: gh-query.sh required-checks <BRANCH>"
    api_call GET "/rules/branches/$ARG"
    render required-checks
    exit $?
    ;;

  # --- resume / onboarding helpers (audit findings F-12, F-13, F-16) --------

  pr-for-branch)
    require_arg "$ARG" "usage: gh-query.sh pr-for-branch <BRANCH>"
    OWNER="$(repo_owner)" || exit 4
    api_call GET "/pulls?head=${OWNER}:${ARG}&state=all&per_page=100"
    render pr-for-branch "$ARG"
    exit $?
    ;;
  ruleset-guarantees)
    require_arg "$ARG" "usage: gh-query.sh ruleset-guarantees <BRANCH> [CHECK_NAME]"
    CHECK_NAME="${3:-$DEFAULT_REQUIRED_CHECK}"
    api_call GET "/rules/branches/$ARG"
    render ruleset-guarantees "$CHECK_NAME"
    exit $?
    ;;
  classic-protection)
    require_arg "$ARG" "usage: gh-query.sh classic-protection <BRANCH> [CHECK_NAME]"
    CHECK_NAME="${3:-$DEFAULT_REQUIRED_CHECK}"
    api_call GET "/branches/$ARG/protection"
    render_raw classic-protection "$API_RC" "$CHECK_NAME"
    exit $?
    ;;
  pr-permission-probe)
    # Probes POST /pulls with head == base. Such a request can never create a
    # pull request, and GitHub checks the token's permission before it
    # validates the payload -- so a validation error proves the permission is
    # there. Nothing is created; see gh_evidence.pr_permission_probe for why
    # only that one answer counts as "permitted".
    require_arg "$ARG" "usage: gh-query.sh pr-permission-probe <BRANCH>"
    PROBE_PAYLOAD="$(python3 "$GH_EVIDENCE" --json-object \
      title "factory-preflight permission probe (cannot create a PR: head == base)" \
      head "$ARG" base "$ARG")"
    api_call POST /pulls "$PROBE_PAYLOAD"
    render_raw pr-permission-probe "$API_RC"
    exit $?
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
    PR_PAYLOAD="$(python3 "$GH_EVIDENCE" --json-object title "$PR_TITLE" head "$PR_HEAD" base "$PR_BASE" body "$PR_BODY")"
    api_call POST /pulls "$PR_PAYLOAD"
    render pr-create-result
    exit $?
    ;;

  merge)
    PR_NUMBER="${2:-}"
    MERGE_METHOD="${3:-}"
    EXPECTED_HEAD_SHA="${4:-}"
    if [ -z "$PR_NUMBER" ] || [ -z "$MERGE_METHOD" ] || [ -z "$EXPECTED_HEAD_SHA" ]; then
      echo "usage: gh-query.sh merge <PR_NUMBER> <MERGE_METHOD> <EXPECTED_HEAD_SHA>" >&2
      echo "       Der erwartete Head-SHA ist Pflicht: gemergt wird ausschliesslich der" >&2
      echo "       Stand, fuer den CI-Evidence und Review tatsaechlich vorliegen." >&2
      exit 2
    fi

    # 1. Local precheck: is the PR still open, unmerged, and on the SHA that
    #    was actually verified?
    api_call GET "/pulls/$PR_NUMBER"
    render merge-precheck "$EXPECTED_HEAD_SHA"
    PRECHECK_RC=$?
    if [ "$PRECHECK_RC" -ne 0 ]; then
      echo "merge: nicht ausgefuehrt (Precheck-Exit $PRECHECK_RC)."
      exit "$PRECHECK_RC"
    fi

    # 2. Server-side binding: GitHub refuses the merge itself if the head
    #    moved between the precheck and now.
    MERGE_PAYLOAD="$(python3 "$GH_EVIDENCE" --json-object merge_method "$MERGE_METHOD" sha "$EXPECTED_HEAD_SHA")"
    api_call PUT "/pulls/$PR_NUMBER/merge" "$MERGE_PAYLOAD"
    render merge-result
    exit $?
    ;;

  *)
    echo "ERROR: unknown subcommand '$SUBCOMMAND'" >&2
    usage
    ;;
esac
