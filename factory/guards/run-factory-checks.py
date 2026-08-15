#!/usr/bin/env python3
"""Canonical entry point for all factory checks.

This is the ONE command that decides whether the current repository state
passes the factory's automated checks. Everything else -- the local Stop
hook, GitHub CI -- is expected to call this script rather than
re-implement its own checking logic.

There are two kinds of check, run in order:
  1. Every finding under factory/findings/ must pass
     factory/guards/validate-finding.py. For a finding trying to reach
     READY_FOR_CLOSURE/CLOSED, this already includes checking that its
     referenced review artifact exists and says "Result: PASS" -- see that
     script's docstring.
  2. Every review artifact under factory/reviews/ must pass
     factory/guards/validate-review.py -- structural completeness only
     (are all required fields filled in, is Result a valid value). Whether
     a review's content is actually correct is not something a
     deterministic script can judge; that is the independent reviewer's
     job (.claude/agents/finding-closure-reviewer.md).

Project-specific guards (e.g. an AST guard that enforces a particular
runtime security boundary of the application this factory is used on) are
deliberately NOT part of this template: they belong to the project, not to
the factory. The intended extension point is a new run_*_checks() function
here plus its own validate-*.py guard, so that every caller keeps invoking
exactly one command and no caller ever duplicates checking logic.

No LLM calls, no network access, no external services -- everything here is
plain, deterministic Python standard library.

Usage:
    python3 factory/guards/run-factory-checks.py [--findings-dir PATH] [--reviews-dir PATH]

Exit code 0: every check passed (including the trivial case of nothing to
             check).
Exit code 1: at least one check failed. A summary of which check and which
             file failed is printed to stderr.
"""
import argparse
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
VALIDATOR = THIS_DIR / "validate-finding.py"
REVIEW_GUARD = THIS_DIR / "validate-review.py"
DEFAULT_FINDINGS_DIR = THIS_DIR.parent / "findings"
DEFAULT_REVIEWS_DIR = THIS_DIR.parent / "reviews"


def run_finding_checks(findings_dir):
    """Run the finding validator against every finding in findings_dir.

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


def run_review_checks(reviews_dir):
    """Run the review-artifact guard against every review file in reviews_dir
    (README.md is excluded -- it documents the format, it is not a review
    artifact itself).

    Returns (ok: bool, report_lines: list[str]).
    """
    report = []

    if not REVIEW_GUARD.is_file():
        report.append(f"[FEHLER] Review-Guard nicht gefunden: {REVIEW_GUARD}")
        return False, report

    if not reviews_dir.is_dir():
        report.append(f"Kein Reviews-Verzeichnis unter {reviews_dir} -- nichts zu pruefen.")
        return True, report

    candidate_files = sorted(p for p in reviews_dir.glob("*.md") if p.name != "README.md")
    if not candidate_files:
        report.append(f"Keine Review-Artefakte unter {reviews_dir} -- nichts zu pruefen.")
        return True, report

    ok = True
    for candidate_file in candidate_files:
        result = subprocess.run(
            [sys.executable, str(REVIEW_GUARD), str(candidate_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            report.append(f"[OK]     review-guard: {candidate_file.name}")
        else:
            ok = False
            report.append(f"[FEHLER] review-guard: {candidate_file.name}")
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
    parser.add_argument(
        "--reviews-dir",
        type=Path,
        default=DEFAULT_REVIEWS_DIR,
        help="Verzeichnis mit Review-Artefakten (Standard: factory/reviews)",
    )
    args = parser.parse_args(argv[1:])

    finding_ok, finding_report = run_finding_checks(args.findings_dir)
    reviews_ok, reviews_report = run_review_checks(args.reviews_dir)

    ok = finding_ok and reviews_ok
    report = finding_report + reviews_report

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
