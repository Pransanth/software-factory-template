#!/usr/bin/env bash
# Deterministically create a finding worktree pinned to the current tip of
# origin's real default branch.
#
# Why this script exists: EnterWorktree's "fresh" base-ref mode (the
# harness default) resolves "the default branch" via the LOCALLY CACHED
# refs/remotes/origin/HEAD symref. `git fetch origin` does NOT refresh that
# symref -- only an explicit `git remote set-head` does. If it has drifted
# (observed in a real multi-finding run: it pointed at an old, already
# merged feature branch instead of the default branch), a worktree created
# via that implicit resolution silently starts from whatever stale commit
# the symref happens to point at, not from the current default-branch tip.
# This script never consults that symref. It asks the REMOTE itself which
# branch HEAD points at (`git ls-remote --symref origin HEAD`), fetches,
# resolves origin/<default-branch> explicitly, creates the worktree
# directly from that ref, and verifies the worktree's HEAD against the SHA
# it resolved before the caller is told the worktree is usable.
#
# Why the default branch is never hardcoded: this script is part of a
# transferable factory template. The branch may be called main, master,
# trunk or anything else. The documented convention is
# origin/<default-branch>, where <default-branch> is determined
# deterministically from the remote at the moment of use -- never guessed,
# never read from the stale local symref, never assumed to be "main".
#
# Why --no-track: creating a branch whose start point is a remote-tracking
# ref makes git set up upstream tracking by default (branch.autoSetupMerge),
# which writes branch.<name>.remote and branch.<name>.merge into
# .git/config. The factory sandbox deliberately denies writes there, so that
# default fails the whole branch creation with "could not lock config file
# .git/config: Operation not permitted". That sandbox boundary is wanted and
# is not to be loosened -- a finding branch simply does not need upstream
# tracking, so it is created with --no-track and pushed explicitly
# (`git push origin <branch>`) instead.
#
# Usage:
#   factory/scripts/create-finding-worktree.sh resolve
#       Asks the remote for its default branch, fetches origin, and prints
#       two plain lines:
#           DEFAULT_BRANCH <name>
#           BASE_SHA <sha>
#       Run this first and read BASE_SHA -- that is the expected base SHA
#       for the "create" step below.
#
#   factory/scripts/create-finding-worktree.sh create <expected-sha> <path> <branch>
#       Creates a new worktree at <path> on new branch <branch>, directly
#       from origin/<default-branch> (never from the current local branch
#       or any other implicit default) and without upstream tracking (see
#       "Why --no-track" above). Immediately verifies the new worktree's
#       HEAD equals <expected-sha>, before any other command runs in it.
#       On match: prints "WORKTREE_READY <path> <branch> <sha>" and exits
#       0 -- the worktree is safe to enter (e.g. via EnterWorktree with
#       `path: <path>`) and use.
#       On mismatch: removes the worktree immediately, prints
#       "AUTONOMY_BLOCKER: ..." to stderr, and exits 1. The worktree is
#       never left behind for use.
#
# Typical caller sequence -- two separate, simple commands run from the
# repository root (no command substitution, no subshell, no pipeline): run
# `resolve`, read the SHA it printed, then pass that SHA literally to
# `create`.
#   factory/scripts/create-finding-worktree.sh resolve
#   factory/scripts/create-finding-worktree.sh create <sha-from-resolve> .claude/worktrees/<ID> fix/<ID>
set -euo pipefail

# Ask the remote which branch its HEAD points at. This is a live answer
# from origin, NOT the local refs/remotes/origin/HEAD symref (which is
# exactly the thing that goes stale). Exits non-zero if it cannot be
# determined -- the factory never guesses a default branch name.
resolve_default_branch() {
  local symref_line
  symref_line="$(git ls-remote --symref origin HEAD | awk '$1 == "ref:" { print $2 }')"
  if [ -z "$symref_line" ]; then
    echo "AUTONOMY_BLOCKER: could not determine origin's default branch via 'git ls-remote --symref origin HEAD'." >&2
    exit 1
  fi
  printf '%s\n' "${symref_line#refs/heads/}"
}

SUBCOMMAND="${1:-}"

case "$SUBCOMMAND" in
  resolve)
    DEFAULT_BRANCH="$(resolve_default_branch)"
    git fetch origin
    BASE_SHA="$(git rev-parse "origin/$DEFAULT_BRANCH")"
    echo "DEFAULT_BRANCH $DEFAULT_BRANCH"
    echo "BASE_SHA $BASE_SHA"
    ;;
  create)
    if [ "$#" -ne 4 ]; then
      echo "usage: create-finding-worktree.sh create <expected-sha> <path> <branch>" >&2
      exit 2
    fi
    EXPECTED_SHA="$2"
    WT_PATH="$3"
    BRANCH="$4"

    DEFAULT_BRANCH="$(resolve_default_branch)"

    git worktree add --no-track -b "$BRANCH" "$WT_PATH" "origin/$DEFAULT_BRANCH"

    # `git -C` is used here on purpose and is the documented exception to
    # the "no git -C" rule in CLAUDE.md: this is a read-only check of a
    # DIFFERENT worktree from inside a single allowlisted script call, not
    # a routine git command issued by the session itself.
    ACTUAL_SHA="$(git -C "$WT_PATH" rev-parse HEAD)"

    if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
      git worktree remove --force "$WT_PATH"
      echo "AUTONOMY_BLOCKER: worktree HEAD ($ACTUAL_SHA) does not match expected origin/$DEFAULT_BRANCH ($EXPECTED_SHA) -- worktree discarded, not entered, not used." >&2
      exit 1
    fi

    echo "WORKTREE_READY $WT_PATH $BRANCH $ACTUAL_SHA"
    ;;
  *)
    echo "usage: create-finding-worktree.sh {resolve|create <expected-sha> <path> <branch>}" >&2
    exit 2
    ;;
esac
