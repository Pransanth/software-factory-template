#!/usr/bin/env bash
# Minimal GitHub REST API helper used in place of the `gh` CLI. The factory
# deliberately does NOT require gh and never installs anything: this script
# wraps the GitHub credential already stored in this machine's git credential
# helper (`git credential fill` for host=github.com) and uses curl -- no new
# credential, no token in a file, no token ever printed to stdout/stderr by
# this script.
#
# Scope: always targets the repo this working copy's `origin` remote points
# at -- callers cannot redirect it to another repository.
#
# Usage:
#   factory/scripts/gh-api.sh METHOD /path/relative/to/repos/OWNER/REPO [json-body]
#
# Examples:
#   factory/scripts/gh-api.sh GET /pulls
#   factory/scripts/gh-api.sh GET /pulls/1
#   factory/scripts/gh-api.sh GET /commits/<sha>/check-runs
#   factory/scripts/gh-api.sh GET /actions/runs?branch=fix/<finding-id>
#   factory/scripts/gh-api.sh POST /pulls '{"title":"...","head":"fix/<finding-id>","base":"<default-branch>","body":"..."}'
#   factory/scripts/gh-api.sh PUT /pulls/1/merge '{"merge_method":"squash"}'
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: gh-api.sh METHOD /path/relative/to/repos/OWNER/REPO [json-body]" >&2
  exit 2
fi

METHOD="$1"
SUBPATH="$2"
BODY="${3:-}"

REMOTE_URL="$(git config --get remote.origin.url)"
REPO_SLUG="$(printf '%s' "$REMOTE_URL" | sed -E 's#^(https://github\.com/|git@github\.com:)##; s#\.git$##')"
REPO_PATH="$(printf '%s' "$REMOTE_URL" | sed -E 's#^(https://github\.com/|git@github\.com:)##')"

if [ -z "$REPO_SLUG" ]; then
  echo "ERROR: could not derive OWNER/REPO from remote.origin.url ($REMOTE_URL)" >&2
  exit 1
fi

# credential.https://github.com.useHttpPath=true means the repo-specific
# keychain entry is keyed by path too -- a fill request without `path` won't
# match it, so `path` is derived from origin's URL and included here.
TOKEN="$(printf 'protocol=https\nhost=github.com\npath=%s\n\n' "$REPO_PATH" | git credential fill | awk -F= '/^password=/{print $2}')"

if [ -z "$TOKEN" ]; then
  echo "ERROR: no GitHub credential available via git credential-helper for host github.com" >&2
  exit 1
fi

CURL_ARGS=(-sS --max-time 30 -X "$METHOD"
  -H "Authorization: Bearer ${TOKEN}"
  -H "Accept: application/vnd.github+json"
  -H "X-GitHub-Api-Version: 2022-11-28"
  "https://api.github.com/repos/${REPO_SLUG}${SUBPATH}")

if [ -n "$BODY" ]; then
  CURL_ARGS+=(-d "$BODY")
fi

curl "${CURL_ARGS[@]}"
