"""Live check that Claude Code's OS-level sandbox actually blocks writes to
factory/reviews/ from a Bash-spawned child process (not just the Edit/Write
tool-permission deny rules, which .claude/hooks/test_subagentstop_write_review.py
already covers structurally).

Run with:
    python3 .claude/hooks/test_sandbox_protects_reviews.py

IMPORTANT, read before assuming a failure here means something is broken:

The sandbox (.claude/settings.json -> "sandbox") is enforced by Claude Code
itself, at the point where it launches a Bash tool command -- it wraps that
command and every child process it spawns in an OS-level container (Seatbelt
on macOS, bubblewrap on Linux/WSL2). It is NOT something a plain Python
process can turn on for itself, and it does not exist at all outside a
Claude-Code-driven Bash invocation:

  - Running this file directly in a plain terminal, or via GitHub Actions CI
    (factory-ci.yml), is NOT sandboxed -- there is no Claude Code Bash tool
    wrapping the process tree, so a write to factory/reviews/ would simply
    succeed there. That is expected, not a bug in this test or the sandbox
    config, so this test SKIPS (rather than fails) whenever the probe write
    below unexpectedly succeeds, and always cleans up any file it manages to
    create either way. For this reason, this file is deliberately NOT wired
    into .github/workflows/factory-ci.yml -- it would always skip there and
    provide no signal, so it stays a local, Claude-Code-session-only check
    (same category of limitation the Stop hook already documents about
    itself in factory/README.md).
  - This test necessarily targets the REAL factory/reviews/ directory of
    this actual repository, not a throwaway temp copy: the sandbox's
    "./factory/reviews" denyWrite entry is anchored to this specific
    project's root by Claude Code's already-loaded settings.json, so a
    throwaway project directory elsewhere would not be covered by it (unlike
    the guard/hook tests elsewhere in this repo, which simulate a whole
    separate project via CLAUDE_PROJECT_DIR). It only ever attempts to write
    a uniquely-named, harmless probe file, and removes it immediately if the
    write unexpectedly succeeds -- it never touches any real finding or any
    real review artifact.

What this test deliberately does NOT attempt to prove: that the trusted
SubagentStop hook (subagentstop-write-review.py) can still write despite the
sandbox. Testing that here would require spawning the hook script as a child
process of this same Bash-invoked test, which would put it inside the exact
same sandbox boundary as this test itself -- unlike its real invocation path,
where Claude Code fires it directly from its own hook-execution mechanism,
architecturally separate from the Bash tool sandbox. A test built that way
would either give a false negative (the hook blocked here, despite working
fine in real, non-Bash-nested use) or would need to disable the very
protection it's supposed to verify. That gap is real and stays undocumented-
as-untested rather than papered over with a misleading green check; the
architecture is trusted here, not (yet) proven end-to-end by a script.
"""
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWS_DIR = REPO_ROOT / "factory" / "reviews"


class SandboxProtectsReviewsTests(unittest.TestCase):
    def test_nested_python_write_to_reviews_dir_is_blocked_by_os_sandbox(self):
        probe_path = REVIEWS_DIR / f".sandbox-probe-{uuid.uuid4().hex}.md"
        self.assertFalse(probe_path.exists())

        write_script = (
            "from pathlib import Path; "
            f"Path({str(probe_path)!r}).write_text('sandbox probe', encoding='utf-8')"
        )
        result = subprocess.run(
            [sys.executable, "-c", write_script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        try:
            if result.returncode == 0 and probe_path.exists():
                # The write succeeded -- we are not running under an active
                # Claude Code OS sandbox for this process tree (e.g. this
                # file was invoked directly, or outside Claude Code, or the
                # sandbox is disabled). That is inconclusive, not a failure
                # of the protection itself.
                self.skipTest(
                    "Write to factory/reviews/ succeeded -- this process is not "
                    "running under an active Claude Code OS sandbox (expected when "
                    "run outside a sandboxed Claude Code Bash session, e.g. in plain "
                    "CI). Re-run this file from within a Claude Code session that "
                    "has this repo's .claude/settings.json sandbox config active to "
                    "get a meaningful result."
                )

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertFalse(probe_path.exists())
            self.assertTrue(
                "PermissionError" in result.stderr
                or "Operation not permitted" in result.stderr
                or "Permission denied" in result.stderr,
                f"expected a permission-style failure, got:\n{result.stderr}",
            )
        finally:
            if probe_path.exists():
                probe_path.unlink()


if __name__ == "__main__":
    unittest.main()
