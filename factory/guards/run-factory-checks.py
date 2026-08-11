#!/usr/bin/env python3
"""Canonical entry point for all factory checks.

This is the ONE command that decides whether the current repository state
passes the factory's automated checks. Everything else -- the local Stop
hook today, CI later -- is expected to call this script rather than
re-implement its own checking logic.

Right now there is exactly one kind of check: every finding under
factory/findings/ must pass factory/guards/validate-finding.py. More check
kinds can be added later; they would all be run from here, in one place.

No LLM calls, no network access, no external services -- everything here is
plain, deterministic Python standard library.

Usage:
    python3 factory/guards/run-factory-checks.py [--findings-dir PATH]

Exit code 0: every check passed (including the trivial case of zero
             findings -- nothing to check is not a failure).
Exit code 1: at least one check failed. A summary of which check and which
             file failed is printed to stderr.
"""
import argparse
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
VALIDATOR = THIS_DIR / "validate-finding.py"
DEFAULT_FINDINGS_DIR = THIS_DIR.parent / "findings"


def run_checks(findings_dir):
    """Run every factory check against findings_dir.

    Returns (ok: bool, report_lines: list[str]).
    """
    report = []

    if not VALIDATOR.is_file():
        report.append(f"[FEHLER] Validator nicht gefunden: {VALIDATOR}")
        return False, report

    if not findings_dir.is_dir():
        report.append(f"Kein Findings-Verzeichnis unter {findings_dir} -- nichts zu pruefen.")
        return True, report

    finding_files = sorted(findings_dir.glob("*.md"))
    if not finding_files:
        report.append(f"Keine Findings unter {findings_dir} -- nichts zu pruefen.")
        return True, report

    ok = True
    for finding_file in finding_files:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), str(finding_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            report.append(f"[OK]     finding-validator: {finding_file.name}")
        else:
            ok = False
            report.append(f"[FEHLER] finding-validator: {finding_file.name}")
            for stream in (result.stdout, result.stderr):
                for line in stream.splitlines():
                    if line.strip():
                        report.append(f"           {line}")

    return ok, report


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--findings-dir",
        type=Path,
        default=DEFAULT_FINDINGS_DIR,
        help="Verzeichnis mit Finding-Dateien (Standard: factory/findings)",
    )
    args = parser.parse_args(argv[1:])

    ok, report = run_checks(args.findings_dir)

    stream = sys.stdout if ok else sys.stderr
    for line in report:
        print(line, file=stream)

    if ok:
        print("Factory-Checks: ALLE BESTANDEN", file=sys.stdout)
        return 0

    print("Factory-Checks: FEHLGESCHLAGEN", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
