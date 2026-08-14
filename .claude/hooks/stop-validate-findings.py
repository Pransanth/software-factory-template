#!/usr/bin/env python3
"""Claude Code Stop hook: block ending a task if factory checks fail.

This script is only the Claude-Code-specific glue. It contains NO finding
validation logic of its own -- it delegates entirely to the one canonical
factory entry point, factory/guards/run-factory-checks.py (exit 0 = all
checks passed, exit 1 = at least one failed). This wrapper's only job is to
run that command and translate its result into what Claude Code expects
from a Stop hook:

    exit 0  -> allow Claude to stop
    exit 2  -> block the stop; stderr is fed back to Claude as the reason

See https://code.claude.com/docs/en/hooks.md for the Stop hook contract.

On "stop_hook_active" (loop prevention):
    On the FIRST stop attempt in a turn (stop_hook_active=false), this hook
    always runs the real canonical check and blocks (exit 2) if anything is
    genuinely invalid, with the concrete failure reason on stderr.

    On a REPEATED stop attempt (stop_hook_active=true) -- i.e. this hook
    already blocked at least once for this turn -- it deliberately does NOT
    run the check again and does NOT block a second time: it exits 0
    immediately, regardless of whether the underlying state is now valid or
    still invalid.

    This is a considered change from an earlier version of this hook, which
    re-checked and re-blocked on every single retry and relied on Claude
    Code's own documented block cap (CLAUDE_CODE_STOP_HOOK_BLOCK_CAP,
    nominally 8 consecutive blocks without progress) to eventually let a
    stuck turn end. In practice that cap did not reliably terminate a real
    stuck loop -- a session got stuck unable to end across many repeated
    Stop-hook invocations, with no local recourse except a human manually
    fixing the filesystem state from outside the session. Relying on a
    platform cap that does not reliably fire is not an acceptable substitute
    for local loop safety.

    This hook is, and always was, a LOCAL WORKFLOW CONVENIENCE, not a final
    security or merge gate -- see factory/README.md, "Was kann der
    Stop-Hook ausdruecklich NICHT garantieren?". Blocking once, surfacing a
    concrete reason, and then getting out of the way on retry preserves
    that convenience (a genuinely invalid first attempt is still caught and
    explained) without risking an unbounded local loop a second time.

    This does NOT weaken any actual validation rule: factory/guards/
    validate-finding.py, validate-review.py, and run-factory-checks.py
    itself are completely unchanged and still enforce everything they
    always did. What changed is only whether THIS hook re-blocks a SECOND
    local stop attempt in the same turn -- not what counts as valid. The
    real, unbypassable gate for this repository is GitHub CI
    (.github/workflows/factory-ci.yml) plus a required status check on the
    protected branch, which runs completely independently of any Claude
    Code session and cannot be affected by ending a local turn.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def project_root():
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root)
    # Fallback for manual/local runs: this file lives at <root>/.claude/hooks/.
    return Path(__file__).resolve().parents[2]


def run_factory_checks(root):
    """Run the canonical factory runner. Returns (ok: bool, output: str)."""
    runner = root / "factory" / "guards" / "run-factory-checks.py"
    if not runner.is_file():
        return False, f"Stop-Hook: Factory-Runner nicht gefunden unter {runner}"

    result = subprocess.run(
        [sys.executable, str(runner)],
        capture_output=True,
        text=True,
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
    return result.returncode == 0, output


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        hook_input = {}

    stop_hook_active = bool(hook_input.get("stop_hook_active"))

    if stop_hook_active:
        # A repeated stop attempt in the same turn -- this hook already
        # blocked once. Do not re-check and do not block again; see the
        # module docstring for why. The real, unbypassable gate is GitHub
        # CI, not this local hook.
        print(
            "Factory-Guard: wiederholter Stop-Versuch. Dieser lokale Hook blockiert "
            "kein zweites Mal in derselben Aufgabe. Die verbindliche, unumgehbare "
            "Schranke ist GitHub CI (.github/workflows/factory-ci.yml) mit Required "
            "Status Check auf dem geschuetzten Branch, nicht dieser lokale Hook -- "
            "siehe factory/README.md."
        )
        return 0

    root = project_root()
    ok, output = run_factory_checks(root)

    if ok:
        return 0

    print(
        "Factory-Guard: mindestens ein Factory-Check ist fehlgeschlagen.\n"
        "Die Aufgabe darf nicht beendet werden, bevor alle Checks bestehen.\n\n"
        + output,
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
