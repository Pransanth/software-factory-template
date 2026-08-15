#!/usr/bin/env python3
"""Canonical entry point for the project's own test suite.

The factory's own tests (factory/guards/test_*.py, .claude/hooks/test_*.py)
are run directly by CI. This script is the counterpart for the tests of the
PRODUCT code that lives in this repository -- whatever that product is. It
looks for <project-dir>/**/test_*.py (default project dir: app/), loads each
found file as an explicit dotted module name and runs them as one suite.

Why not `unittest discover`: a product package tree without __init__.py
files cannot be reliably recursed into by discovery (behavior varies by
Python version and invocation directory). Resolving each test file to an
explicit module name makes the suite run identically locally and in CI.

Why this is NOT wired into run-factory-checks.py (and therefore not into
the local Stop hook): during IMPLEMENTING, a red regression test *before*
the fix is a normal, wanted intermediate state (that is the whole point of
a Regression Test Plan). A Stop hook that demanded a green product suite at
every end of turn would block exactly that wanted intermediate state. CI
runs on push/PR -- i.e. when a change is claimed to be finished -- and is
therefore the right place for "all product tests must be green".

A repository that has no product code yet (a fresh copy of this template)
simply has no <project-dir>, and this script exits 0 with a clear note.

Usage:
    python3 factory/guards/run-project-tests.py [--project-dir app]

Exit code 0: all project tests passed (including the trivial case of no
             project directory / zero test files found).
Exit code 1: at least one project test failed or errored.
"""
import argparse
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_DIR = "app"


def discover_test_modules(project_dir):
    modules = []
    for path in sorted(project_dir.rglob("test_*.py")):
        rel = path.relative_to(REPO_ROOT).with_suffix("")
        modules.append(".".join(rel.parts))
    return modules


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        default=DEFAULT_PROJECT_DIR,
        help="Verzeichnis mit dem Produktcode, relativ zur Repo-Wurzel (Standard: app)",
    )
    args = parser.parse_args(argv[1:])

    project_dir = (REPO_ROOT / args.project_dir).resolve()
    if not project_dir.is_dir():
        print(
            f"Kein Projektverzeichnis unter {project_dir} -- nichts zu pruefen. "
            "(Frische Kopie der Factory-Vorlage ohne Produktcode: erwartet.)"
        )
        return 0

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    modules = discover_test_modules(project_dir)
    if not modules:
        print(f"Keine Tests unter {project_dir} gefunden -- nichts zu pruefen.")
        return 0

    suite = unittest.TestLoader().loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
