#!/usr/bin/env python3
"""Canonical entry point for the PRODUCT's own test suite.

This is a thin wrapper. All decisions live in factory/guards/project_tests.py,
which is the single place that determines whether product tests count as
performed -- see its module docstring for the three states and why a missing
configuration is a blocker rather than a pass.

What changed, and why (audit finding F-21): this script used to search for
`app/**/test_*.py` and run them with unittest. It therefore assumed the product
was written in Python, and for any other project it found nothing and exited 0.
The factory now knows nothing about the product's test framework; the project
declares its commands in factory/project-tests.conf.

Why this is NOT wired into run-factory-checks.py (and therefore not into the
local Stop hook): during IMPLEMENTING, a red regression test *before* the fix is
a normal, wanted intermediate state -- that is the whole point of a Regression
Test Plan. A Stop hook demanding a green product suite at every end of turn
would block exactly that wanted state. CI runs on push/PR, i.e. when a change is
claimed to be finished, and is therefore the right place for "all product tests
must be green".

Usage:
    python3 factory/guards/run-project-tests.py

Exit code 0: product tests passed, or this is a bare template without product
             code (reported explicitly as TEMPLATE_WITHOUT_PRODUCT).
Exit code 1: at least one configured suite failed.
Exit code 2: blocked -- no usable configuration, an unrunnable command, or
             product code without a test configuration. Never a silent pass.
"""
import sys
from pathlib import Path

# See validate-finding.py for the full reasoning: importing a sibling module
# would otherwise make CPython write factory/guards/__pycache__/*.pyc, which
# becomes tracked content on the next `git add -A` and silently moves the scope
# hash. Measuring must not alter what is measured.
sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_tests import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
