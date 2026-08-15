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
# Two audit findings shaped this script's current behavior:
#
#   F-17: the origin URL was reduced to OWNER/REPO by stripping two exact
#   prefixes and nothing else. Perfectly ordinary remotes --
#   ssh://git@github.com/o/r.git, https://user@github.com/o/r.git, or a
#   trailing slash -- produced garbage like "ssh://git@github.com/o/r", the
#   only check was "is it empty" (it never was), and the result was a
#   malformed API URL whose 404 then looked like a normal answer. The slug is
#   now normalized across all documented remote spellings and validated
#   against OWNER/REPO before any request is made. An unsupported remote is a
#   hard, explained stop.
#
#   F-07: curl ran without any status handling, so a 401, 403, 404, 422, 429
#   or 5xx returned its JSON error body with exit code 0 -- and the callers'
#   `data.get("check_runs", [])` turned that into "no check runs yet", i.e.
#   indistinguishable from "CI has not started". The HTTP status is now
#   captured, an error is reported on stderr as `api_error: HTTP <code>`, and
#   the exit code is non-zero. The body is still printed so the caller can
#   render GitHub's own message.
#
# Usage:
#   factory/scripts/gh-api.sh METHOD /path/relative/to/repos/OWNER/REPO [json-body]
#   factory/scripts/gh-api.sh slug [ORIGIN_URL]   # no network; prints the derived slug
#
# Examples:
#   factory/scripts/gh-api.sh GET /pulls
#   factory/scripts/gh-api.sh GET /commits/<sha>/check-runs
#   factory/scripts/gh-api.sh POST /pulls '{"title":"...","head":"...","base":"..."}'
#   factory/scripts/gh-api.sh PUT /pulls/1/merge '{"merge_method":"squash","sha":"<head>"}'
#
# Exit codes:
#   0  HTTP 2xx
#   1  configuration problem (no origin, unsupported remote, no credential)
#   2  usage error
#   3  HTTP >= 400 -- body on stdout, `api_error: HTTP <code>` on stderr
#   4  curl/network failure
set -euo pipefail

EXIT_CONFIG=1
EXIT_USAGE=2
EXIT_HTTP=3
EXIT_NETWORK=4

# Reduce any supported github.com remote spelling to OWNER/REPO.
# Handles: https://, http://, ssh://, git://, scp-style git@github.com:,
# an optional user@ prefix, an optional .git suffix and a trailing slash.
normalize_slug() {
  printf '%s' "$1" | /usr/bin/sed -E \
    -e 's#^(https?://([^@/]+@)?github\.com/|ssh://([^@/]+@)?github\.com/|git://github\.com/|([^@/]+@)?github\.com:)##' \
    -e 's#/+$##' \
    -e 's#\.git$##'
}

# The credential-helper lookup path: origin's path component as git itself
# stores it (including a .git suffix when the remote has one), without a
# trailing slash.
credential_path() {
  printf '%s' "$1" | /usr/bin/sed -E \
    -e 's#^(https?://([^@/]+@)?github\.com/|ssh://([^@/]+@)?github\.com/|git://github\.com/|([^@/]+@)?github\.com:)##' \
    -e 's#/+$##'
}

resolve_origin_url() {
  local url
  url="$(git config --get remote.origin.url || true)"
  if [ -z "$url" ]; then
    echo "ERROR: kein 'origin'-Remote konfiguriert." >&2
    exit "$EXIT_CONFIG"
  fi
  printf '%s' "$url"
}

validate_slug() {
  # OWNER/REPO, exactly one slash, no scheme, no host, no spaces.
  if ! printf '%s' "$1" | /usr/bin/grep -qE '^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$'; then
    echo "ERROR: aus remote.origin.url ($2) laesst sich kein gueltiges OWNER/REPO ableiten (ergab: '$1')." >&2
    echo "       Unterstuetzt werden github.com-Remotes in den Formen:" >&2
    echo "         https://github.com/OWNER/REPO(.git)" >&2
    echo "         https://USER@github.com/OWNER/REPO(.git)" >&2
    echo "         ssh://git@github.com/OWNER/REPO(.git)" >&2
    echo "         git@github.com:OWNER/REPO(.git)" >&2
    exit "$EXIT_CONFIG"
  fi
}

# --- slug subcommand: no network, used by the preflight and by tests --------

if [ "${1:-}" = "slug" ]; then
  # An explicitly passed URL is used as given -- including an empty one,
  # which must fail validation rather than silently fall back to origin.
  if [ "$#" -ge 2 ]; then
    RAW_URL="$2"
  else
    RAW_URL="$(resolve_origin_url)"
  fi
  SLUG="$(normalize_slug "$RAW_URL")"
  validate_slug "$SLUG" "$RAW_URL"
  echo "slug: $SLUG"
  echo "credential_path: $(credential_path "$RAW_URL")"
  exit 0
fi

if [ "$#" -lt 2 ]; then
  echo "usage: gh-api.sh METHOD /path/relative/to/repos/OWNER/REPO [json-body]" >&2
  echo "       gh-api.sh slug [ORIGIN_URL]" >&2
  exit "$EXIT_USAGE"
fi

METHOD="$1"
SUBPATH="$2"
BODY_IN="${3:-}"

REMOTE_URL="$(resolve_origin_url)"
REPO_SLUG="$(normalize_slug "$REMOTE_URL")"
validate_slug "$REPO_SLUG" "$REMOTE_URL"
REPO_PATH="$(credential_path "$REMOTE_URL")"

# credential.https://github.com.useHttpPath=true means the repo-specific
# keychain entry is keyed by path too -- a fill request without `path` won't
# match it, so `path` is derived from origin's URL and included here.
TOKEN="$(printf 'protocol=https\nhost=github.com\npath=%s\n\n' "$REPO_PATH" | git credential fill | awk -F= '/^password=/{print $2}')"

if [ -z "$TOKEN" ]; then
  echo "ERROR: no GitHub credential available via git credential-helper for host github.com" >&2
  exit "$EXIT_CONFIG"
fi

CURL_ARGS=(-sS --max-time 30 -w '\n%{http_code}' -X "$METHOD"
  -H "Authorization: Bearer ${TOKEN}"
  -H "Accept: application/vnd.github+json"
  -H "X-GitHub-Api-Version: 2022-11-28"
  "https://api.github.com/repos/${REPO_SLUG}${SUBPATH}")

if [ -n "$BODY_IN" ]; then
  CURL_ARGS+=(-d "$BODY_IN")
fi

set +e
RESPONSE="$(curl "${CURL_ARGS[@]}")"
CURL_RC=$?
set -e

if [ "$CURL_RC" -ne 0 ]; then
  echo "api_error: curl/Netzwerkfehler (exit $CURL_RC) bei ${METHOD} ${SUBPATH}." >&2
  exit "$EXIT_NETWORK"
fi

# The status code is the last line appended by -w; everything before it is
# the response body (which may be empty).
HTTP_CODE="${RESPONSE##*$'\n'}"
case "$RESPONSE" in
  *$'\n'*) RESPONSE_BODY="${RESPONSE%$'\n'*}" ;;
  *) RESPONSE_BODY="" ;;
esac

printf '%s\n' "$RESPONSE_BODY"

case "$HTTP_CODE" in
  2*) exit 0 ;;
  *)
    echo "api_error: HTTP ${HTTP_CODE} bei ${METHOD} ${SUBPATH} (Repo ${REPO_SLUG})." >&2
    exit "$EXIT_HTTP"
    ;;
esac
