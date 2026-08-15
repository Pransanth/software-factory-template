#!/usr/bin/env python3
"""Deterministic hash of the repository state a closure review is bound to.

Why this exists (audit finding F-03): a review artifact used to record its
diff basis as free text ("Reviewed Commit: abc123") that nothing ever
compared against anything. A PASS therefore stayed valid forever, including
after the reviewed code changed -- and the documented workflow *always*
changes something after the review (it writes Review Artifact and Status
into the finding). So "the reviewer approved this code" and "this is the
code being merged" were two unrelated claims.

This module turns that into one deterministic, machine-checkable value:

    scope hash = sha256 over every tracked file's path and content,
                 EXCEPT factory/findings/ and factory/reviews/

The SubagentStop hook stamps this value into the review artifact at the
moment the reviewer finishes, and validate-finding.py recomputes it at
closure time. They must be equal, or the finding cannot close.

What the two exclusions buy, and why they are safe:
  - factory/findings/: the workflow writes Verification Evidence, CI
    Evidence, Review Artifact and Status into the finding, partly *after*
    the review. Including it would make every review invalidate itself one
    step later, which would force the mechanism to be turned off.
  - factory/reviews/: writing the review artifact itself would otherwise
    change the very hash being stamped into it.
Everything a reviewer actually judges -- product code, tests, guards,
scripts, hooks, agent definitions, CI workflow, build orders -- is inside
the hash. Changing any of it after a PASS invalidates that PASS.

Deliberate, documented limits (do not oversell this):
  - Only *tracked* files count. An untracked file is not part of what a
    push and a merge would carry, so it is not part of what a review binds
    to. `git add` of a new file does change the hash.
  - This is a change detector, not an authenticity proof. It answers "is
    this the same tree the reviewer saw?", not "is this tree good". A
    local user who can rewrite both the artifact and the code can restamp
    it; see factory/reviews/README.md for that honest boundary.
  - Symlinks are hashed by their target *path* (like git stores them), not
    by the content they point at, so the value stays identical between a
    local checkout and a CI checkout.

Usage:
    python3 factory/guards/scope_hash.py [--repo-root PATH]

Exit code 0: prints "scope_hash: sha256:<hex>" and "scope_files: <count>".
Exit code 1: the hash could not be computed (no git repository, git
             failure, or nothing in scope). It never falls back to a
             guessed or empty value -- an unknown scope hash must block a
             closure, not silently pass one.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

SCOPE_HASH_VERSION = "factory-scope-hash-v1"

# Paths whose content is deliberately outside the reviewed scope. Keep this
# list minimal: every entry here is something a review can no longer notice.
EXCLUDED_PREFIXES = (
    "factory/findings/",
    "factory/reviews/",
)

SCOPE_HASH_RE_SOURCE = r"^sha256:[0-9a-f]{64}$"

# factory/guards/scope_hash.py -> parents[0]=guards, [1]=factory, [2]=repo root
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]


class ScopeHashError(RuntimeError):
    """The scope hash could not be determined. Never treat this as 'unchanged'."""


def _tracked_files(repo_root):
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(repo_root),
            capture_output=True,
        )
    except OSError as exc:  # git not installed
        raise ScopeHashError(f"git ist nicht ausfuehrbar: {exc}") from exc

    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ScopeHashError(
            f"'git ls-files' in {repo_root} fehlgeschlagen (kein Git-Repository?): {detail}"
        )

    return sorted(
        entry.decode("utf-8", "surrogateescape")
        for entry in result.stdout.split(b"\0")
        if entry
    )


def _file_fingerprint(path):
    """sha256 of the file's bytes, or of a symlink's target path."""
    if path.is_symlink():
        return "symlink:" + hashlib.sha256(
            str(path.readlink()).encode("utf-8", "surrogateescape")
        ).hexdigest()
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        # Tracked but not readable as a plain file right now (deleted in the
        # working tree, or a submodule directory). Recorded explicitly so the
        # state is still deterministic instead of skipped.
        return "absent"


def in_scope(relative_path):
    return not relative_path.startswith(EXCLUDED_PREFIXES)


def compute_scope_hash(repo_root=None):
    """Return ("sha256:<hex>", file_count) for the repository at repo_root."""
    root = Path(repo_root or DEFAULT_REPO_ROOT).resolve()
    digest = hashlib.sha256()
    digest.update(SCOPE_HASH_VERSION.encode("ascii") + b"\n")

    count = 0
    for relative_path in _tracked_files(root):
        if not in_scope(relative_path):
            continue
        digest.update(relative_path.encode("utf-8", "surrogateescape"))
        digest.update(b"\0")
        digest.update(_file_fingerprint(root / relative_path).encode("ascii"))
        digest.update(b"\n")
        count += 1

    if count == 0:
        raise ScopeHashError(
            f"Kein einziger getrackter Datei-Pfad im Scope unter {root} -- "
            "so ein Hash waere bedeutungslos."
        )

    return "sha256:" + digest.hexdigest(), count


def main(argv):
    parser = argparse.ArgumentParser(description="Compute the factory scope hash.")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv[1:])

    try:
        scope_hash, count = compute_scope_hash(args.repo_root)
    except ScopeHashError as exc:
        print(f"SCOPE_HASH_ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"scope_hash: {scope_hash}")
    print(f"scope_files: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
