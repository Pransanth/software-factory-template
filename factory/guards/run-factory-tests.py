#!/usr/bin/env python3
"""Discover and run every factory test -- no hand-maintained module list.

Usage:
    python3 factory/guards/run-factory-tests.py [--require-sandbox]
                                                [--repo-root PATH] [--quiet]

Exit code 0: every discovered test passed, and (with --require-sandbox) the
             sandbox verification really ran.
Exit code 1: a test failed or errored, nothing was discovered at all, or
             --require-sandbox was given and the sandbox verification did not
             actually happen.

## Why this exists (audit finding F-19)

.github/workflows/factory-ci.yml used to name every test module by hand:

    python3 -m unittest factory.guards.test_validate_finding \\
        factory.guards.test_validate_review ... -v

A new test file was therefore only executed in CI if somebody also remembered
to add it to that line -- and forgetting is silent. The list grows, the person
adding a test is usually not thinking about the workflow file, and the failure
mode is the worst kind: CI stays green precisely because the new test never
ran. Worse, the workflow file is control plane, so adding a module to it is a
FACTORY_CHANGE; the friction pushed in exactly the wrong direction.

Discovery removes the list. Anything matching

    factory/guards/test_*.py
    .claude/hooks/test_*.py

runs. Nothing has to be registered anywhere.

Discovering nothing is a hard failure, not a quiet success: "no tests found"
and "all tests passed" must never print the same thing.

## A skipped test is not a passed test (F-19, second half)

.claude/hooks/test_sandbox_protects_reviews.py tries to write into
factory/reviews/ and asserts that the operating-system sandbox refuses. That
assertion is only meaningful when a sandbox is actually active. On a plain CI
runner there is none, so the test skips -- correctly, because it cannot verify
what is not there.

The danger is in the reporting: unittest prints "OK (skipped=1)" and a summary
line that says everything passed. Read quickly, a green CI run then looks like
proof that the sandbox protects factory/reviews/. It is not. It is proof that
the CI runner has no sandbox.

So this runner keeps the two apart explicitly and names them:

  - **CI test** -- deterministic, runs anywhere, and its result is evidence.
  - **Sandbox verification** -- only meaningful inside a real Claude Code
    sandbox. It is reported separately as `performed` or `not_performed`, and
    `not_performed` is never folded into the pass count.

`--require-sandbox` turns `not_performed` into a failure. It is meant for the
local preflight, which runs where a sandbox does exist -- not for CI, where
demanding it would be demanding something the environment cannot provide.
"""
import argparse
import sys
import unittest
from pathlib import Path

# Running the whole test suite in-process imports a lot of modules. Without
# this, CPython would write factory/guards/__pycache__/*.pyc next to the
# sources -- generated files that a later `git add -A` tracks, which moves the
# scope hash and silently invalidates a review that was just recorded. Same
# invariant as validate-finding.py: measuring must not alter what is measured.
sys.dont_write_bytecode = True

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]

# (start directory, top-level import root) for each discovered tree.
# .claude/hooks is its own top level because ".claude" is not an importable
# package name -- the hook tests are standalone scripts, not a package.
TEST_TREES = (
    ("factory/guards", "."),
    (".claude/hooks", ".claude/hooks"),
)

TEST_PATTERN = "test_*.py"

# Tests whose subject is the OS sandbox itself. Their result is only evidence
# where a sandbox exists; everywhere else they skip, and a skip must never be
# read as a pass. Matched on the module name so a new sandbox test is covered
# without touching this file.
SANDBOX_MODULE_MARKER = "sandbox"


class DiscoveryError(RuntimeError):
    """Tests could not be discovered. Never treat this as 'nothing to run'."""


def _module_name_for(relative_start, path):
    """A unique, readable module name that keeps the file's own stem visible.

    The stem has to survive because the sandbox classification below matches
    on the module name -- a renamed-away 'sandbox' would silently turn a
    sandbox verification into an ordinary CI test.
    """
    prefix = relative_start.strip("./").replace("/", "_").replace(".", "")
    return f"{prefix}__{path.stem}"


def discover(repo_root):
    """Return (suite, [module names]) for every factory test tree.

    Test files are loaded by PATH, not through package discovery. That is
    deliberate: unittest's discovery requires the start directory to be an
    importable package, which factory/guards is not on Python 3.9 (namespace
    packages only became discoverable later) and .claude/hooks can never be,
    because ".claude" is not a valid identifier. Loading by path works
    identically on every supported interpreter and keeps CI and local runs
    executing the same set of files.
    """
    import importlib.util

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    modules = []

    for relative_start, relative_top in TEST_TREES:
        start_dir = repo_root / relative_start
        if not start_dir.is_dir():
            continue

        # Standalone test scripts (the hooks) resolve their subject relative
        # to their own directory, so that directory has to be importable.
        for candidate in (repo_root / relative_top, start_dir):
            candidate_str = str(candidate.resolve())
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)

        for path in sorted(start_dir.glob(TEST_PATTERN)):
            module_name = _module_name_for(relative_start, path)
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise DiscoveryError(f"Testmodul nicht ladbar: {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as exc:  # noqa: BLE001 - a broken test file must be loud
                raise DiscoveryError(
                    f"Testmodul {path} liess sich nicht importieren: {exc!r}"
                ) from exc
            suite.addTests(loader.loadTestsFromModule(module))
            modules.append(f"{relative_start}/{path.name}")

    if not modules:
        raise DiscoveryError(
            "Kein einziges Testmodul gefunden ("
            + ", ".join(f"{start}/{TEST_PATTERN}" for start, _ in TEST_TREES)
            + "). 'nichts gefunden' und 'alles bestanden' duerfen nie dasselbe "
            "Ergebnis liefern."
        )

    return suite, modules


def _test_module_name(test):
    """The module a test (or a discovery failure) came from."""
    return type(test).__module__ or ""


def sandbox_test_ids(suite):
    """Ids of the tests whose subject is the OS sandbox itself.

    Collected BEFORE the run: unittest.TestSuite drops its tests as it
    executes them (TestSuite._removeTestAtIndex), so inspecting the suite
    afterwards silently yields nothing -- which would report every run as
    "no sandbox test present" and quietly lose exactly the distinction this
    runner exists to make.
    """
    return {
        str(test)
        for test in _iter_tests(suite)
        if SANDBOX_MODULE_MARKER in _test_module_name(test).lower()
    }


def classify_sandbox(result, sandbox_ids):
    """Return (state, detail) for the sandbox verification.

    state is one of 'performed', 'not_performed', 'absent'.
    """
    if not sandbox_ids:
        return "absent", "kein Sandbox-Verifikationstest vorhanden"

    skipped = {str(test): reason for test, reason in result.skipped}
    failed_ids = {str(test) for test, _ in result.failures + result.errors}

    ran = sorted(test_id for test_id in sandbox_ids if test_id not in skipped)
    if not ran:
        reasons = sorted({skipped[test_id] for test_id in sandbox_ids if test_id in skipped})
        return "not_performed", "; ".join(reasons) or "uebersprungen"

    if any(test_id in failed_ids for test_id in ran):
        return "not_performed", "Sandbox-Verifikation ist fehlgeschlagen"

    return "performed", f"{len(ran)} Test(s) real ausgefuehrt"


def _iter_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_tests(item)
        else:
            yield item


def main(argv):
    parser = argparse.ArgumentParser(description="Run every discovered factory test.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument(
        "--require-sandbox",
        action="store_true",
        help=(
            "Fehlschlag, wenn die Sandbox-Verifikation nicht wirklich lief. "
            "Fuer den lokalen Preflight gedacht, NICHT fuer CI: dort gibt es "
            "keine Claude-Sandbox, und sie einzufordern hiesse, etwas zu "
            "verlangen, das die Umgebung nicht liefern kann."
        ),
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv[1:])

    repo_root = args.repo_root.resolve()

    try:
        suite, modules = discover(repo_root)
    except DiscoveryError as exc:
        print(f"FACTORY_TESTS_ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Entdeckte Testmodule ({len(modules)}):")
    for name in modules:
        print(f"  - {name}")
    print()

    sandbox_ids = sandbox_test_ids(suite)

    runner = unittest.TextTestRunner(verbosity=1 if args.quiet else 2, stream=sys.stdout)
    result = runner.run(suite)

    sandbox_state, sandbox_detail = classify_sandbox(result, sandbox_ids)

    print()
    print(f"ci_tests_run: {result.testsRun}")
    print(f"ci_test_failures: {len(result.failures)}")
    print(f"ci_test_errors: {len(result.errors)}")
    print(f"ci_tests_skipped: {len(result.skipped)}")
    for test, reason in result.skipped:
        print(f"  skipped: {test} -- {reason}")
    print(f"SANDBOX_VERIFICATION: {sandbox_state} ({sandbox_detail})")
    print(
        "hinweis: ein uebersprungener Sandbox-Test belegt NICHT, dass die "
        "Sandbox schuetzt -- er belegt, dass hier keine aktiv ist."
    )

    ok = result.wasSuccessful()

    if args.require_sandbox and sandbox_state != "performed":
        print(
            "FACTORY_TESTS: FEHLGESCHLAGEN -- --require-sandbox verlangt eine "
            f"tatsaechlich durchgefuehrte Sandbox-Verifikation, Zustand ist "
            f"'{sandbox_state}'.",
            file=sys.stderr,
        )
        ok = False

    if not ok:
        print("FACTORY_TESTS: FEHLGESCHLAGEN", file=sys.stderr)
        return 1

    print("FACTORY_TESTS: ALLE BESTANDEN")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
