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
    stop_hook_active=true only means "Claude Code is retrying this stop
    attempt after a Stop hook already blocked it at least once" -- it is
    NOT evidence that whatever was invalid has since been fixed. Claude
    could be retrying for an unrelated reason, or nothing may have changed
    at all. So this hook always re-runs the real check, every single time,
    and always reports its true result: a genuinely invalid state is
    blocked (exit 2) on every attempt, not just the first.

    Loop prevention is therefore deliberately NOT this hook's job. Claude
    Code itself already guarantees no infinite loop: per the official docs
    (https://code.claude.com/docs/en/hooks-guide.md, "Limitations and
    troubleshooting"), Claude Code overrides a Stop hook after it blocks
    eight times in a row without progress, ends the turn anyway, and warns
    that the Stop hook blocked too many consecutive times. That cap is
    configurable via the CLAUDE_CODE_STOP_HOOK_BLOCK_CAP environment
    variable. This platform-level cap -- not any logic in this script -- is
    what makes an infinite loop impossible here. It is also the clearest
    concrete illustration of why this hook is a local workflow guard and
    not a final gate: after enough genuinely-still-invalid attempts, Claude
    Code can and will let Claude stop regardless of what this hook returns.
    See factory/README.md, "Was kann der Stop-Hook ausdruecklich NICHT
    garantieren?".
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

    root = project_root()
    ok, output = run_factory_checks(root)

    if ok:
        return 0

    # Always block on a genuinely invalid state -- stop_hook_active is never
    # treated as proof that things are fine, only used for a clarifying note.
    retry_note = (
        "Dies ist ein wiederholter Stop-Versuch; der Zustand wurde erneut\n"
        "tatsaechlich ueberprueft und ist weiterhin ungueltig.\n\n"
        if stop_hook_active
        else ""
    )
    print(
        "Factory-Guard: mindestens ein Factory-Check ist fehlgeschlagen.\n"
        "Die Aufgabe darf nicht beendet werden, bevor alle Checks bestehen.\n\n"
        + retry_note
        + output,
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
