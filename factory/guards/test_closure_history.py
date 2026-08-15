"""Regression tests: a closed finding must not be re-judged against today's tree.

Run with:
    python3 -m unittest factory.guards.test_closure_history

## The defect these tests pin down

The trust-core package bound a review PASS to the scope hash of the code it
actually saw (F-03), and validate-finding.py recomputed that hash from the
WORKING TREE on every run. For a finding on its way to closure that is exactly
right. For a finding that is already CLOSED it is wrong, and it was found here
by doing the next piece of work rather than by reasoning about it:

    $ python3 factory/guards/validate-finding.py factory/findings/FACTORY-TRUST-CORE-1.md
    UNGÜLTIG: factory/findings/FACTORY-TRUST-CORE-1.md
      - Scope-Hash-Abweichung: Review-Artefakt
        'factory/reviews/FACTORY-TRUST-CORE-1.round-1.md' wurde gegen sha256:4a9a17a4…
        erstellt, der aktuelle Stand ist sha256:f09994eb…

FACTORY-TRUST-CORE-1 was closed, reviewed, CI-green and merged. Changing any
tracked file afterwards -- which is what the next finding does by definition --
moved the hash and made that historical closure invalid, so the canonical
runner and therefore CI went red for work that had nothing to do with it.
**The first merged finding turned the whole factory read-only.**

## The repair, and what it deliberately does NOT relax

The binding stays cryptographic and stays exact. What changes is which tree the
comparison may be against:

  - READY_FOR_CLOSURE  -> the CURRENT working tree, unchanged. This is the live
    gate: a finding may only reach the state it merges from if the review
    covers the code being merged.
  - CLOSED             -> the current tree, OR the tree of a commit that
    actually touched this finding or its own review artifact, hashed from
    git's object store by scope_hash.compute_scope_hash_at().

A stale PASS that never corresponded to a state in which this finding was being
closed matches nothing and is still rejected -- that is what the negative tests
below hold in place. Weakening the gate to "CLOSED skips the scope check" would
have been the easy fix and is exactly what these tests forbid.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REAL_GUARDS_DIR = Path(__file__).resolve().parent

GUARD_FILES = (
    "validate-finding.py",
    "validate-review.py",
    "validate-build-order.py",
    "run-factory-checks.py",
    "validate-control-plane.py",
    "scope_hash.py",
    # Audit-Befund F-18: validate-finding.py und validate-build-order.py lesen
    # Findings ausschliesslich ueber diesen einen Parser. Fehlt er in einem
    # Wegwerf-Repository, scheitert jeder Guard-Aufruf mit ModuleNotFoundError.
    "finding_format.py",
    # Audit-Befund F-21: der kanonische Runner prueft ueber dieses Modul, ob
    # bestimmt ist, welche Produkttests als Verification gelten.
    "project_tests.py",
)

GIT_ENV_OVERRIDES = {
    "GIT_AUTHOR_NAME": "Factory Test",
    "GIT_AUTHOR_EMAIL": "factory-test@example.invalid",
    "GIT_COMMITTER_NAME": "Factory Test",
    "GIT_COMMITTER_EMAIL": "factory-test@example.invalid",
}

NEVER_EXISTED_HASH = "sha256:" + ("0" * 64)

ANALYSIS_BLOCK = """\
Root Cause: Fehlende Pruefung der Organisation beim Erstellen neuer Jobs.
Affected Components: Job-Scheduler, Job-Worker.
Relevant Architecture: Hintergrundjobs laufen ohne zentralen Org-Filter.
Recommended Repair: Zentralen Guard einfuehren, der die Org-ID erzwingt.
Regression Test Plan: Neue Tests fuer Jobs mit falscher/fehlender Org-ID.
Central Guard Plan: Guard-Funktion, die jeder Job-Registrierung vorgeschaltet wird.
Expected Blast Radius: Nur neue Hintergrundjobs, keine bestehenden Endpunkte.
Risk Assessment: Gering, da rein additive Pruefung ohne bestehendes Verhalten zu aendern.
"""

BUILD_ORDER = """\
# Bauauftrag: {finding}

## Primäre Sicherheitsgrenze

Die Org-ID wird nicht mehr als Parameter durchgereicht, sondern aus dem
Auftragskontext abgeleitet, sodass der unsichere Zustand unerreichbar wird.

## Verbindliche Reihenfolge

1. Regressionstest schreiben und ROT beobachten.
2. Laufzeitgrenze umsetzen, bis derselbe Test GRUEN ist.
3. Zentralen Guard ergaenzen und kanonischen Runner laufen lassen.

## Acceptance Criteria

Ein Job ohne abgeleitete Org-ID ist nicht mehr registrierbar, und der zentrale
Guard erkennt jeden erneuten Versuch, sie als Parameter zu uebergeben.

## Scope

Erlaubt und abschliessend: app/jobs/**, app/tests/test_jobs.py. Alles andere
ist out of scope, insbesondere die geschuetzten Factory-Pfade.

## Red Regression Evidence

```
FAIL: test_job_without_org_is_rejected
AssertionError: 0 != 1 : guard accepted what it must reject.
```

## Green Runtime Fix Evidence

```
$ python3 -m unittest app.tests.test_jobs
Ran 4 tests in 0.112s
OK
```
"""

REVIEW_TEMPLATE = """\
# {finding}

Finding: {finding}
Reviewer: finding-closure-reviewer subagent
Reviewer Agent Type: finding-closure-reviewer
Reviewer Agent ID: agent-test-0001
Reviewed Commit: {commit}
Reviewed Scope Hash: {scope_hash}
Result: {result}
Root Cause Addressed: Ja, die Reparatur entfernt den frei waehlbaren Parameter.
Regression Evidence Checked: Regressionstest gelesen, Assertion unveraendert.
Guard Evidence Checked: Zentraler Guard gelesen und Negativtest bestaetigt.
Scope Checked: Nur die im Bauauftrag genannten Pfade veraendert.
Remaining Risks: Keine identifiziert.
Findings And Objections: Keine.
"""

CLOSURE_BLOCK = """\
Verification Evidence: Regressionstest app.test_org_scope gruen, Guard gruen.
CI Evidence: GitHub Actions Run 123456789 auf dem Finding-Branch, conclusion success.
Review Artifact: {review_artifact}
"""


def _git(cwd, *args):
    env = dict(os.environ)
    env.update(GIT_ENV_OVERRIDES)
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


class ClosureHistoryTestCase(unittest.TestCase):
    """A throwaway git project with real history, not just a single commit."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-closure-history-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.root = self.tmp_dir / "project"

        self.guards_dir = self.root / "factory" / "guards"
        self.findings_dir = self.root / "factory" / "findings"
        self.reviews_dir = self.root / "factory" / "reviews"
        self.build_orders_dir = self.root / "factory" / "build-orders"
        for directory in (
            self.guards_dir,
            self.findings_dir,
            self.reviews_dir,
            self.build_orders_dir,
            self.root / "app",
        ):
            directory.mkdir(parents=True)

        for name in GUARD_FILES:
            source = REAL_GUARDS_DIR / name
            if source.is_file():
                shutil.copy2(source, self.guards_dir / name)

        (self.root / "app" / "code.py").write_text("VALUE = 1\n", encoding="utf-8")
        # Product code present -> audit finding F-21 requires a test
        # configuration, otherwise the canonical runner correctly blocks.
        (self.root / "factory" / "project-tests.conf").write_text(
            "mode: real-project\n\n[suite: unit]\ncommand: true\n", encoding="utf-8"
        )

        _git(self.root, "init", "--initial-branch=trunk")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "initial")

        stamp = subprocess.run(
            [
                sys.executable,
                str(self.guards_dir / "validate-control-plane.py"),
                "--repo-root",
                str(self.root),
                "--update",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(stamp.returncode, 0, stamp.stderr)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "stamp control plane")

    # -- helpers ---------------------------------------------------------

    def scope_hash(self, commit=None):
        args = [sys.executable, str(self.guards_dir / "scope_hash.py")]
        if commit:
            args += ["--commit", commit]
        result = subprocess.run(args, cwd=str(self.root), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in result.stdout.splitlines():
            if line.startswith("scope_hash:"):
                return line.split(":", 1)[1].strip()
        self.fail(f"scope_hash.py printed no scope_hash line: {result.stdout!r}")

    def change_product_code(self, value):
        (self.root / "app" / "code.py").write_text(f"VALUE = {value}\n", encoding="utf-8")

    def write_finding(self, finding_id, status, review_artifact=None):
        body = [
            f"# {finding_id}",
            "",
            f"Status: {status}",
            "Severity: P1",
            "",
            "## Befund",
            "",
            "Beispielbefund.",
            "",
            "## Analyse",
            "",
            ANALYSIS_BLOCK.rstrip(),
        ]
        if review_artifact is not None:
            body.append(CLOSURE_BLOCK.format(review_artifact=review_artifact).rstrip())
        path = self.findings_dir / f"{finding_id}.md"
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        return path

    def write_build_order(self, finding_id):
        path = self.build_orders_dir / f"{finding_id}.md"
        path.write_text(BUILD_ORDER.format(finding=finding_id), encoding="utf-8")
        return path

    def commit_build_order(self, finding_id):
        """Write AND commit the build order.

        It has to be committed before any review round is stamped: build
        orders are inside the scope hash (a reviewer judges them), so an
        untracked one that becomes tracked later would move the hash after the
        stamp -- which is the mechanism working, not a bug, but it would make
        these fixtures test the wrong thing.
        """
        self.write_build_order(finding_id)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", f"build order for {finding_id}")

    def write_round(self, finding_id, number, result="PASS", scope_hash=None):
        path = self.reviews_dir / f"{finding_id}.round-{number}.md"
        path.write_text(
            REVIEW_TEMPLATE.format(
                finding=finding_id,
                result=result,
                commit="abc123",
                scope_hash=self.scope_hash() if scope_hash is None else scope_hash,
            ),
            encoding="utf-8",
        )
        return path

    def close_finding(self, finding_id="F-1", scope_hash=None):
        """Write and COMMIT a complete, legitimate closure."""
        self.commit_build_order(finding_id)

        self.write_round(finding_id, 1, scope_hash=scope_hash)
        self.write_finding(
            finding_id,
            "CLOSED",
            review_artifact=f"factory/reviews/{finding_id}.round-1.md",
        )
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", f"close {finding_id}")

    def validate_finding(self, finding_id="F-1"):
        return subprocess.run(
            [
                sys.executable,
                str(self.guards_dir / "validate-finding.py"),
                str(self.findings_dir / f"{finding_id}.md"),
            ],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )

    def run_factory_checks(self):
        return subprocess.run(
            [sys.executable, str(self.guards_dir / "run-factory-checks.py")],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )

    def assertRejected(self, result, *expected_fragments):
        self.assertEqual(
            result.returncode,
            1,
            f"guard accepted what it must reject.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        combined = result.stdout + result.stderr
        for fragment in expected_fragments:
            self.assertIn(fragment, combined)

    def assertAccepted(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class HistoricalScopeHashTests(ClosureHistoryTestCase):
    """compute_scope_hash_at() must reproduce the working-tree hash exactly."""

    def test_commit_hash_equals_working_tree_hash_for_a_clean_tree(self):
        self.assertEqual(self.scope_hash(), self.scope_hash("HEAD"))

    def test_a_finding_only_commit_does_not_move_the_hash(self):
        """The exclusions exist for this: writing the finding and the review
        after the review must not invalidate it."""
        self.commit_build_order("F-1")
        before = self.scope_hash("HEAD")

        self.write_round("F-1", 1)
        self.write_finding(
            "F-1", "CLOSED", review_artifact="factory/reviews/F-1.round-1.md"
        )
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "close F-1")

        self.assertEqual(self.scope_hash("HEAD"), before)

    def test_a_product_change_does_move_the_commit_hash(self):
        """Guard against over-repair: the historical hash must still be a real
        change detector, not a constant."""
        before = self.scope_hash("HEAD")
        self.change_product_code(2)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "product change")
        self.assertNotEqual(self.scope_hash("HEAD"), before)


class ClosedFindingSurvivesLaterWorkTests(ClosureHistoryTestCase):
    """The blocker itself: closure is history, not a claim about today."""

    def test_a_closed_finding_stays_valid_after_later_unrelated_work(self):
        self.close_finding()
        self.assertAccepted(self.validate_finding())

        self.change_product_code(2)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "unrelated later work")

        self.assertAccepted(self.validate_finding())

    def test_the_canonical_runner_survives_a_change_after_a_closure(self):
        """This is the layer CI actually runs -- and the one that went red."""
        self.close_finding()
        self.change_product_code(3)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "unrelated later work")
        self.assertAccepted(self.run_factory_checks())

    def test_an_uncommitted_later_change_also_leaves_a_closure_valid(self):
        """A dirty working tree during the next finding must not invalidate
        an already merged closure either."""
        self.close_finding()
        self.change_product_code(4)
        self.assertAccepted(self.validate_finding())


class ClosureBindingIsNotRelaxedTests(ClosureHistoryTestCase):
    """What must still be rejected. These are the reason the fix is not
    'CLOSED skips the scope-hash check'."""

    def test_ready_for_closure_still_requires_the_current_scope_hash(self):
        self.commit_build_order("F-1")
        self.write_round("F-1", 1)
        self.write_finding(
            "F-1", "READY_FOR_CLOSURE", review_artifact="factory/reviews/F-1.round-1.md"
        )
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "ready for closure")
        self.assertAccepted(self.validate_finding())

        self.change_product_code(2)
        self.assertRejected(self.validate_finding(), "Scope-Hash-Abweichung")

    def test_closed_with_a_scope_hash_that_never_existed_is_rejected(self):
        self.close_finding(scope_hash=NEVER_EXISTED_HASH)
        self.assertRejected(self.validate_finding(), "Scope-Hash-Abweichung")

    def test_closed_with_a_hash_from_a_state_this_finding_never_closed_at_is_rejected(self):
        """A PASS for an old tree, in which this finding was never being
        closed, must not close it now."""
        stale_hash = self.scope_hash()

        self.change_product_code(2)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "code moved on before the finding existed")

        self.close_finding(scope_hash=stale_hash)
        self.assertRejected(self.validate_finding(), "Scope-Hash-Abweichung")

    def test_a_fail_round_for_the_same_state_still_blocks_a_later_pass(self):
        """F-04 must survive the history lookup unchanged."""
        self.commit_build_order("F-1")
        self.write_round("F-1", 1, result="FAIL")
        self.write_round("F-1", 2, result="PASS")
        self.write_finding(
            "F-1", "CLOSED", review_artifact="factory/reviews/F-1.round-2.md"
        )
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "close after fail")
        self.assertRejected(self.validate_finding(), "Result 'FAIL'")

    def test_a_closed_finding_still_needs_its_own_review(self):
        """F-02 must survive the history lookup unchanged."""
        self.commit_build_order("F-1")
        self.write_round("F-2", 1)
        self.write_finding(
            "F-1", "CLOSED", review_artifact="factory/reviews/F-2.round-1.md"
        )
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "close on a foreign review")
        self.assertRejected(self.validate_finding(), "kanonische")


if __name__ == "__main__":
    unittest.main(verbosity=2)
