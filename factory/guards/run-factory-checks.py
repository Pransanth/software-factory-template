#!/usr/bin/env python3
"""Canonical entry point for all factory checks.

This is the ONE command that decides whether the current repository state
passes the factory's automated checks. Everything else -- the local Stop
hook, GitHub CI -- is expected to call this script rather than
re-implement its own checking logic.

There are three kinds of check, run in order:
  1. Every finding under factory/findings/ must pass
     factory/guards/validate-finding.py. For a finding trying to reach
     READY_FOR_CLOSURE/CLOSED, this includes the full closure binding:
     the referenced review artifact must be this finding's own latest
     round, must pass the review guard, must say "Result: PASS", and its
     scope hash must still match the repository -- see that script's
     docstring.
  2. Every review artifact under factory/reviews/ must pass
     factory/guards/validate-review.py -- structural completeness only
     (are all required fields filled in, is the file name a canonical
     round, is Result a valid value). Whether a review's content is
     actually correct is not something a deterministic script can judge;
     that is the independent reviewer's job
     (.claude/agents/finding-closure-reviewer.md).
  3. The factory's own control plane must match its stamped manifest
     (factory/guards/validate-control-plane.py). This is what stops a
     normal finding from silently changing the guards, scripts, hooks,
     rules or CI workflow that judge it -- CI runs those from the pull
     request's own head, so without this check a branch could weaken the
     guard that was about to check it.

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
CONTROL_PLANE_GUARD = THIS_DIR / "validate-control-plane.py"
BUILD_ORDER_GUARD = THIS_DIR / "validate-build-order.py"
PROJECT_TESTS_MODULE = THIS_DIR / "project_tests.py"
REPO_ROOT = THIS_DIR.parents[1]
DEFAULT_FINDINGS_DIR = THIS_DIR.parent / "findings"
DEFAULT_REVIEWS_DIR = THIS_DIR.parent / "reviews"
DEFAULT_BUILD_ORDERS_DIR = THIS_DIR.parent / "build-orders"

# factory/build-orders/README.md documents the format; it is not a build
# order and must not be validated as an orphan one.
NON_BUILD_ORDER_NAMES = {"README.md"}


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


def run_build_order_checks(build_orders_dir):
    """Run the build-order guard against every build order (audit finding F-10).

    Returns (ok: bool, report_lines: list[str]).

    The finding validator already refuses a finding from IMPLEMENTING onwards
    whose own build order is missing or invalid. This pass is the other
    direction: a build order that belongs to no finding, or that decayed into
    placeholders, is caught here even when no finding currently points at it.
    """
    report = []

    if not BUILD_ORDER_GUARD.is_file():
        report.append(f"[FEHLER] Bauauftrags-Guard nicht gefunden: {BUILD_ORDER_GUARD}")
        return False, report

    if not build_orders_dir.is_dir():
        report.append(
            f"Kein Bauauftrags-Verzeichnis unter {build_orders_dir} -- nichts zu pruefen."
        )
        return True, report

    candidate_files = sorted(
        p for p in build_orders_dir.glob("*.md") if p.name not in NON_BUILD_ORDER_NAMES
    )
    if not candidate_files:
        report.append(f"Keine Bauauftraege unter {build_orders_dir} -- nichts zu pruefen.")
        return True, report

    ok = True
    for candidate_file in candidate_files:
        result = subprocess.run(
            [sys.executable, str(BUILD_ORDER_GUARD), str(candidate_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            report.append(f"[OK]     build-order-guard: {candidate_file.name}")
        else:
            ok = False
            report.append(f"[FEHLER] build-order-guard: {candidate_file.name}")
            for stream in (result.stdout, result.stderr):
                for line in stream.splitlines():
                    if line.strip():
                        report.append(f"           {line}")

    return ok, report


def run_control_plane_checks():
    """Run the control-plane guard. Returns (ok: bool, report_lines: list[str])."""
    report = []

    if not CONTROL_PLANE_GUARD.is_file():
        report.append(f"[FEHLER] Control-Plane-Guard nicht gefunden: {CONTROL_PLANE_GUARD}")
        return False, report

    result = subprocess.run(
        [sys.executable, str(CONTROL_PLANE_GUARD)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        report.append("[OK]     control-plane-guard: Kontrollebene unveraendert")
        return True, report

    report.append("[FEHLER] control-plane-guard: Kontrollebene weicht vom Manifest ab")
    for stream in (result.stdout, result.stderr):
        for line in stream.splitlines():
            if line.strip():
                report.append(f"           {line}")
    return False, report


def run_project_test_configuration_check():
    """Check the product-test CONFIGURATION, not the product tests themselves.

    The distinction matters (audit finding F-21). Running the product suite here
    would break a deliberate design decision: during IMPLEMENTING, a red
    regression test before the fix is a wanted intermediate state, and the local
    Stop hook runs this runner at every end of turn. So the runner asks only the
    structural question -- is it determined which product tests count? -- and
    leaves the actual run to CI, where "this change is finished" is claimed.

    A real project without a test configuration is a blocker here, because that
    state cannot be fixed by any later check: nothing downstream would notice
    that the product was never tested.
    """
    report = []

    if not PROJECT_TESTS_MODULE.is_file():
        report.append(
            f"[FEHLER] project-tests-guard: Modul nicht gefunden: {PROJECT_TESTS_MODULE}"
        )
        return False, report

    sys.path.insert(0, str(PROJECT_TESTS_MODULE.parent))
    try:
        import project_tests
    except ImportError as exc:  # pragma: no cover - defensive
        report.append(f"[FEHLER] project-tests-guard: nicht importierbar ({exc})")
        return False, report

    exit_code, state, lines = project_tests.evaluate(REPO_ROOT)

    if state == project_tests.STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION:
        report.append(f"[FEHLER] project-tests-guard: {state}")
        for line in lines:
            if line.strip() and not line.startswith("PROJECT_TESTS:"):
                report.append(f"           {line}")
        return False, report

    if state == project_tests.STATE_TEMPLATE_WITHOUT_PRODUCT:
        report.append(
            "[OK]     project-tests-guard: TEMPLATE_WITHOUT_PRODUCT "
            "(Vorlage ohne Produktcode -- erwartet)"
        )
        return True, report

    report.append(
        "[OK]     project-tests-guard: CONFIGURED "
        "(Produkttests deklariert; ausgefuehrt werden sie in der CI)"
    )
    return True, report


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
    parser.add_argument(
        "--build-orders-dir",
        type=Path,
        default=DEFAULT_BUILD_ORDERS_DIR,
        help="Verzeichnis mit Bauauftraegen (Standard: factory/build-orders)",
    )
    args = parser.parse_args(argv[1:])

    finding_ok, finding_report = run_finding_checks(args.findings_dir)
    build_order_ok, build_order_report = run_build_order_checks(args.build_orders_dir)
    reviews_ok, reviews_report = run_review_checks(args.reviews_dir)
    control_plane_ok, control_plane_report = run_control_plane_checks()
    project_tests_ok, project_tests_report = run_project_test_configuration_check()

    ok = (
        finding_ok
        and build_order_ok
        and reviews_ok
        and control_plane_ok
        and project_tests_ok
    )
    report = (
        finding_report
        + build_order_report
        + reviews_report
        + control_plane_report
        + project_tests_report
    )

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
