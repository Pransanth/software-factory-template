"""Trust-core regression tests: review integrity, review rounds, severity gate.

Run with:
    python3 -m unittest factory.guards.test_trust_core

These tests pin down the invariants the factory audit found missing
(F-01, F-02, F-03, F-04, F-09). Every one of them was written to FAIL
against the pre-repair guards, which accepted all of the following:

  - a "Review Artifact" pointing at any file outside factory/reviews/
    that happens to contain a "Result: PASS" line (F-01)
  - finding X closing on finding Y's review artifact (F-02)
  - a review artifact staying valid after the reviewed code changed (F-03)
  - a FAIL round being silently overwritten by a later PASS round for the
    exact same code state (F-04)
  - a finding with no severity at all, so "a P0 never runs autonomously"
    was documentation rather than a rule (F-09)

Each test builds a throwaway git repository containing copies of the real
guards, so <repo-root> (which the guards resolve from their own location)
is that temp tree. The real factory/findings/ and factory/reviews/ of this
repository are never read or written.

A real git repository is required because the scope hash is computed over
the repository's tracked files -- see scope_hash.py for why that is the
definition, and what it deliberately does not cover.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REAL_GUARDS_DIR = Path(__file__).resolve().parent

# Guard files copied into every throwaway project.
GUARD_FILES = (
    "validate-finding.py",
    "validate-review.py",
    "validate-build-order.py",
    "run-factory-checks.py",
    "validate-control-plane.py",
    "scope_hash.py",
)

# From IMPLEMENTING onwards a finding needs its own valid build order (audit
# finding F-10). These tests are about review integrity and the severity gate,
# so the fixture supplies a valid build order as the normal case rather than
# every test restating it; factory/guards/test_build_order.py is where the
# build-order rules themselves are pinned down.
BUILD_ORDER_TEMPLATE = """\
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

STATUSES_NEEDING_BUILD_ORDER = (
    "IMPLEMENTING",
    "VERIFYING",
    "READY_FOR_CLOSURE",
    "CLOSED",
)

GIT_ENV_OVERRIDES = {
    "GIT_AUTHOR_NAME": "Factory Test",
    "GIT_AUTHOR_EMAIL": "factory-test@example.invalid",
    "GIT_COMMITTER_NAME": "Factory Test",
    "GIT_COMMITTER_EMAIL": "factory-test@example.invalid",
}

WRONG_SCOPE_HASH = "sha256:" + ("0" * 64)

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

CLOSURE_BLOCK = """\
Verification Evidence: Regressionstest app.test_org_scope gruen, Guard gruen.
CI Evidence: GitHub Actions Run 123456789 auf dem Finding-Branch, conclusion success.
Review Artifact: {review_artifact}
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


def _git(cwd, *args):
    env = dict(os.environ)
    env.update(GIT_ENV_OVERRIDES)
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


class TrustCoreTestCase(unittest.TestCase):
    """Shared fixture: a throwaway git project with the real guards in it."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-trust-core-test-")).resolve()
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
            shutil.copy2(REAL_GUARDS_DIR / name, self.guards_dir / name)

        # A tracked product file: changing it is what makes the scope hash move.
        (self.root / "app" / "code.py").write_text("VALUE = 1\n", encoding="utf-8")

        _git(self.root, "init", "--initial-branch=trunk")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "initial")

        # The canonical runner also checks the control plane, so the fixture
        # needs a stamped manifest. Product changes below never touch it.
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

    # -- helpers ---------------------------------------------------------

    def scope_hash(self):
        """The scope hash of the temp project, as the guards compute it."""
        result = subprocess.run(
            [sys.executable, str(self.guards_dir / "scope_hash.py")],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in result.stdout.splitlines():
            if line.startswith("scope_hash:"):
                return line.split(":", 1)[1].strip()
        self.fail(f"scope_hash.py printed no scope_hash line: {result.stdout!r}")

    def change_product_code(self, value):
        """A relevant code change: tracked content that the scope hash covers."""
        (self.root / "app" / "code.py").write_text(f"VALUE = {value}\n", encoding="utf-8")

    def write_finding(
        self,
        finding_id,
        status="READY_FOR_CLOSURE",
        severity="P1",
        review_artifact=None,
        extra="",
    ):
        body = [f"# {finding_id}", "", f"Status: {status}"]
        if severity is not None:
            body.append(f"Severity: {severity}")
        body += ["", "## Befund", "", "Beispielbefund.", "", "## Analyse", "", ANALYSIS_BLOCK.rstrip()]
        if review_artifact is not None:
            body.append(CLOSURE_BLOCK.format(review_artifact=review_artifact).rstrip())
        if extra:
            body.append(extra.rstrip())
        path = self.findings_dir / f"{finding_id}.md"
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        if status in STATUSES_NEEDING_BUILD_ORDER:
            self.write_build_order(finding_id)
        return path

    def write_build_order(self, finding_id):
        path = self.build_orders_dir / f"{finding_id}.md"
        path.write_text(BUILD_ORDER_TEMPLATE.format(finding=finding_id), encoding="utf-8")
        return path

    def write_round(self, finding_id, round_number, result="PASS", scope_hash=None, commit="abc123"):
        path = self.reviews_dir / f"{finding_id}.round-{round_number}.md"
        path.write_text(
            REVIEW_TEMPLATE.format(
                finding=finding_id,
                result=result,
                commit=commit,
                scope_hash=self.scope_hash() if scope_hash is None else scope_hash,
            ),
            encoding="utf-8",
        )
        return path

    def validate_finding(self, path):
        return subprocess.run(
            [sys.executable, str(self.guards_dir / "validate-finding.py"), str(path)],
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


class ReviewArtifactPathTests(TrustCoreTestCase):
    """F-01: the closure gate must accept only the canonical review artifact."""

    def test_canonical_review_artifact_is_accepted(self):
        self.write_round("F-1", 1, result="PASS")
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertAccepted(self.validate_finding(finding))

    def test_arbitrary_file_containing_result_pass_is_rejected(self):
        """The exact bypass reproduced in the audit: a self-written build
        order with a 'Result: PASS' line used as the review artifact."""
        fake = self.build_orders_dir / "F-1.md"
        fake.write_text("# Bauauftrag: F-1\n\nResult: PASS\n", encoding="utf-8")
        finding = self.write_finding("F-1", review_artifact="factory/build-orders/F-1.md")
        self.assertRejected(self.validate_finding(finding), "Review Artifact")

    def test_absolute_path_outside_reviews_is_rejected(self):
        outside = self.tmp_dir / "outside-review.md"
        outside.write_text("Result: PASS\n", encoding="utf-8")
        finding = self.write_finding("F-1", review_artifact=str(outside))
        self.assertRejected(self.validate_finding(finding), "Review Artifact")

    def test_parent_traversal_is_rejected(self):
        outside = self.tmp_dir / "outside-review.md"
        outside.write_text("Result: PASS\n", encoding="utf-8")
        finding = self.write_finding(
            "F-1", review_artifact="factory/reviews/../../../outside-review.md"
        )
        self.assertRejected(self.validate_finding(finding), "Review Artifact")

    def test_symlink_escape_out_of_reviews_dir_is_rejected(self):
        outside = self.tmp_dir / "outside-review.md"
        outside.write_text(
            REVIEW_TEMPLATE.format(
                finding="F-1", result="PASS", commit="abc123", scope_hash=self.scope_hash()
            ),
            encoding="utf-8",
        )
        link = self.reviews_dir / "F-1.round-1.md"
        link.symlink_to(outside)
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertRejected(self.validate_finding(finding))

    def test_review_artifact_that_fails_the_review_guard_blocks_closure(self):
        """Not just 'contains Result: PASS' -- the artifact must pass
        validate-review.py itself (F-01, requirement 7)."""
        path = self.reviews_dir / "F-1.round-1.md"
        path.write_text(
            "# F-1\n\nFinding: F-1\nResult: PASS\n", encoding="utf-8"
        )  # structurally incomplete: no provenance, no scope hash
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertRejected(self.validate_finding(finding))


class ReviewIdentityTests(TrustCoreTestCase):
    """F-02: a PASS for finding A must never close finding B."""

    def test_finding_cannot_close_on_another_findings_review(self):
        self.write_finding("F-1", status="OPEN")
        self.write_round("F-1", 1, result="PASS")
        finding_b = self.write_finding("F-2", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertRejected(self.validate_finding(finding_b), "Review Artifact")

    def test_review_whose_finding_field_mismatches_its_filename_is_rejected(self):
        path = self.reviews_dir / "F-2.round-1.md"
        path.write_text(
            REVIEW_TEMPLATE.format(
                finding="F-1", result="PASS", commit="abc123", scope_hash=self.scope_hash()
            ),
            encoding="utf-8",
        )
        self.write_finding("F-1", status="OPEN")
        finding = self.write_finding("F-2", review_artifact="factory/reviews/F-2.round-1.md")
        self.assertRejected(self.validate_finding(finding))

    def test_review_guard_rejects_mismatch_on_its_own(self):
        path = self.reviews_dir / "F-2.round-1.md"
        path.write_text(
            REVIEW_TEMPLATE.format(
                finding="F-1", result="PASS", commit="abc123", scope_hash=self.scope_hash()
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(self.guards_dir / "validate-review.py"), str(path)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1, result.stdout)


class ScopeBindingTests(TrustCoreTestCase):
    """F-03: a PASS must not survive a relevant code change."""

    def test_pass_is_invalid_after_the_reviewed_code_changed(self):
        self.write_round("F-1", 1, result="PASS")
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertAccepted(self.validate_finding(finding))

        self.change_product_code(2)
        self.assertRejected(self.validate_finding(finding), "Scope")

    def test_finding_metadata_written_after_the_review_does_not_invalidate_it(self):
        """The workflow itself writes Review Artifact and Status into the
        finding after the review, and creates the review artifact. Neither
        may invalidate the review it belongs to."""
        self.write_round("F-1", 1, result="PASS")
        finding = self.write_finding(
            "F-1", status="READY_FOR_CLOSURE", review_artifact="factory/reviews/F-1.round-1.md"
        )
        self.assertAccepted(self.validate_finding(finding))

        finding = self.write_finding(
            "F-1", status="CLOSED", review_artifact="factory/reviews/F-1.round-1.md"
        )
        self.assertAccepted(self.validate_finding(finding))

    def test_wrong_scope_hash_is_rejected(self):
        self.write_round("F-1", 1, result="PASS", scope_hash=WRONG_SCOPE_HASH)
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertRejected(self.validate_finding(finding), "Scope")


class ReviewRoundTests(TrustCoreTestCase):
    """F-04: rounds are append-only, and FAIL -> PASS needs a real change."""

    def test_fail_then_pass_against_the_same_code_state_is_rejected(self):
        unchanged = self.scope_hash()
        self.write_round("F-1", 1, result="FAIL", scope_hash=unchanged)
        self.write_round("F-1", 2, result="PASS", scope_hash=unchanged)
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-2.md")
        self.assertRejected(self.validate_finding(finding))

    def test_fail_then_change_then_pass_is_accepted(self):
        self.write_round("F-1", 1, result="FAIL")
        self.change_product_code(2)
        self.write_round("F-1", 2, result="PASS")
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-2.md")
        self.assertAccepted(self.validate_finding(finding))

    def test_an_older_pass_round_cannot_be_used_when_a_newer_round_exists(self):
        self.write_round("F-1", 1, result="PASS")
        self.change_product_code(2)
        self.write_round("F-1", 2, result="FAIL")
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertRejected(self.validate_finding(finding))

    def test_latest_round_must_be_pass(self):
        self.write_round("F-1", 1, result="FAIL")
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertRejected(self.validate_finding(finding))

    def test_expert_review_required_round_does_not_close(self):
        self.write_round("F-1", 1, result="EXPERT_REVIEW_REQUIRED")
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertRejected(self.validate_finding(finding))

    def test_non_round_review_filename_is_rejected_by_the_review_guard(self):
        path = self.reviews_dir / "F-1.md"
        path.write_text(
            REVIEW_TEMPLATE.format(
                finding="F-1", result="PASS", commit="abc123", scope_hash=self.scope_hash()
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(self.guards_dir / "validate-review.py"), str(path)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1, result.stdout)


class SeverityGateTests(TrustCoreTestCase):
    """F-09: P0 must not run through the normal autonomous lifecycle."""

    def test_severity_is_required_from_analyzed_onwards(self):
        finding = self.write_finding("F-1", status="ANALYZED", severity=None)
        self.assertRejected(self.validate_finding(finding), "Severity")

    def test_unknown_severity_is_rejected(self):
        finding = self.write_finding("F-1", status="ANALYZED", severity="CRITICAL")
        self.assertRejected(self.validate_finding(finding), "Severity")

    def test_open_finding_without_severity_is_still_valid(self):
        finding = self.write_finding("F-1", status="OPEN", severity=None)
        self.assertAccepted(self.validate_finding(finding))

    def test_p0_may_be_analyzed(self):
        finding = self.write_finding("F-1", status="ANALYZED", severity="P0")
        self.assertAccepted(self.validate_finding(finding))

    def test_p0_may_be_escalated_to_expert_review(self):
        finding = self.write_finding(
            "F-1",
            status="EXPERT_REVIEW_REQUIRED",
            severity="P0",
            extra=(
                "Expert Review Reason: Laufende Ausnutzung, autonome Entscheidung nicht verantwortbar.\n"
                "What Is Known: Der Angriffspfad ist reproduziert.\n"
                "What Remains Uncertain: Umfang des bereits erfolgten Zugriffs.\n"
                "What An Expert Would Need To Review: Zugriffsprotokolle und Sofortmassnahmen.\n"
            ),
        )
        self.assertAccepted(self.validate_finding(finding))

    def test_p0_cannot_reach_implementing(self):
        finding = self.write_finding("F-1", status="IMPLEMENTING", severity="P0")
        self.assertRejected(self.validate_finding(finding), "P0")

    def test_p0_cannot_reach_verifying(self):
        finding = self.write_finding("F-1", status="VERIFYING", severity="P0")
        self.assertRejected(self.validate_finding(finding), "P0")

    def test_p0_cannot_reach_closed_even_with_a_valid_review(self):
        self.write_round("F-1", 1, result="PASS")
        finding = self.write_finding(
            "F-1", status="CLOSED", severity="P0", review_artifact="factory/reviews/F-1.round-1.md"
        )
        self.assertRejected(self.validate_finding(finding), "P0")

    def test_p1_closes_normally(self):
        self.write_round("F-1", 1, result="PASS")
        finding = self.write_finding(
            "F-1", status="CLOSED", severity="P1", review_artifact="factory/reviews/F-1.round-1.md"
        )
        self.assertAccepted(self.validate_finding(finding))


class CanonicalRunnerTests(TrustCoreTestCase):
    """The same invariants must hold through the one canonical entry point."""

    def test_runner_rejects_the_arbitrary_file_bypass(self):
        fake = self.build_orders_dir / "F-1.md"
        fake.write_text("Result: PASS\n", encoding="utf-8")
        self.write_finding("F-1", status="CLOSED", review_artifact="factory/build-orders/F-1.md")
        result = self.run_factory_checks()
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_runner_accepts_a_fully_bound_closure(self):
        self.write_round("F-1", 1, result="PASS")
        self.write_finding(
            "F-1", status="CLOSED", review_artifact="factory/reviews/F-1.round-1.md"
        )
        result = self.run_factory_checks()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ScopeHashPurityTests(TrustCoreTestCase):
    """Measuring the scope must never change the scope (audit F-03).

    The scope hash covers the repository's TRACKED files. Importing the
    scope-hash module makes CPython write __pycache__/*.pyc next to the source
    by default, so a later `git add -A` turns that generated bytecode into
    tracked content -- and the hash changes with no content change at all,
    silently invalidating a review that had just been recorded.

    This was invisible on the machine it was developed on, whose system python
    redirects bytecode to a central cache via sys.pycache_prefix, and only
    surfaced on CI. These tests therefore normalise the interpreter to
    CPython's documented default (sys.pycache_prefix = None) through a
    sitecustomize helper placed OUTSIDE the fixture repository. That is not a
    platform special case -- it removes one, by making a vendor-specific
    redirection irrelevant to the result.
    """

    def setUp(self):
        super().setUp()
        helper = self.tmp_dir / "sitecustomize-helper"
        helper.mkdir()
        (helper / "sitecustomize.py").write_text(
            "import sys\nsys.pycache_prefix = None\n", encoding="utf-8"
        )
        self.pure_env = dict(os.environ)
        self.pure_env["PYTHONPATH"] = str(helper)
        # An inherited PYTHONDONTWRITEBYTECODE would make every test in this
        # class pass without proving anything.
        self.pure_env.pop("PYTHONDONTWRITEBYTECODE", None)

        # Settle the fixture before measuring anything. The base fixture
        # stamps factory/control-plane.sha256 AFTER its initial commit, so that
        # file starts out untracked; a real repository has it committed. Left
        # unsettled, the first `git add -A` in a test would pull it into the
        # hash and look exactly like the bytecode defect these tests exist to
        # catch. Staging here keeps the tests measuring one thing only.
        _git(self.root, "add", "-A")

    # -- helpers ---------------------------------------------------------

    def run_pure(self, *args):
        """Run a factory script the way CI does: bytecode written next to the
        source unless the script itself refuses to write it."""
        return subprocess.run(
            [sys.executable, *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            env=self.pure_env,
        )

    def pure_scope_hash(self):
        result = self.run_pure(str(self.guards_dir / "scope_hash.py"))
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in result.stdout.splitlines():
            if line.startswith("scope_hash:"):
                return line.split(":", 1)[1].strip()
        self.fail(f"no scope_hash line: {result.stdout!r}")

    def bytecode_in_repo(self):
        return sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*.pyc"))

    def tracked_files(self):
        result = subprocess.run(
            ["git", "ls-files"], cwd=str(self.root), capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.split()

    def measure_via_finding_validator(self):
        """The real measurement path: validate-finding.py imports scope_hash."""
        finding = self.write_finding("F-PURITY", status="ANALYZED")
        result = self.run_pure(str(self.guards_dir / "validate-finding.py"), str(finding))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # -- the invariant ----------------------------------------------------

    def test_running_the_scope_hash_cli_writes_no_bytecode(self):
        self.pure_scope_hash()
        self.assertEqual(self.bytecode_in_repo(), [])

    def test_the_finding_validator_writes_no_bytecode(self):
        """validate-finding.py imports scope_hash -- the exact path that
        produced factory/guards/__pycache__/scope_hash.cpython-311.pyc in CI."""
        self.measure_via_finding_validator()
        self.assertEqual(self.bytecode_in_repo(), [])

    def test_git_add_after_measuring_tracks_no_bytecode(self):
        self.measure_via_finding_validator()
        self.pure_scope_hash()
        _git(self.root, "add", "-A")
        tracked_bytecode = [
            path for path in self.tracked_files()
            if path.endswith((".pyc", ".pyo")) or "__pycache__" in path
        ]
        self.assertEqual(tracked_bytecode, [])

    def test_scope_hash_is_unchanged_by_measuring_it(self):
        """The whole point: measure, stage everything, measure again."""
        before = self.pure_scope_hash()
        self.measure_via_finding_validator()
        _git(self.root, "add", "-A")
        after = self.pure_scope_hash()
        self.assertEqual(before, after)

    def test_the_review_binding_survives_a_measurement(self):
        """End to end: a PASS must still close after the scope was measured
        and everything staged -- that is what broke in CI."""
        # The build order is inside the scope hash (a reviewer judges it), so
        # it has to exist and be tracked BEFORE the round is stamped. That is
        # the mechanism working, not a workaround: staging new reviewed
        # content after a review does invalidate it.
        self.write_build_order("F-1")
        _git(self.root, "add", "-A")

        self.write_round("F-1", 1, result="PASS")
        finding = self.write_finding("F-1", review_artifact="factory/reviews/F-1.round-1.md")
        self.assertAccepted(self.validate_finding(finding))

        self.measure_via_finding_validator()
        _git(self.root, "add", "-A")
        self.assertAccepted(self.validate_finding(finding))

    # -- the fix must not have weakened the hash --------------------------

    def test_a_real_code_change_still_changes_the_hash(self):
        before = self.pure_scope_hash()
        self.change_product_code(2)
        self.assertNotEqual(before, self.pure_scope_hash())

    def test_a_deliberately_tracked_pyc_is_still_part_of_the_hash(self):
        """No path is excluded from the hash by this fix. Bytecode that a
        project really does track stays inside the measured scope -- a
        sourceless .pyc can execute code, so hiding it would be exactly the
        blind spot this audit closed. The fix prevents such files from being
        created and tracked; it does not make them invisible."""
        before = self.pure_scope_hash()
        pycache = self.guards_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "deliberate.cpython-311.pyc").write_text("x", encoding="utf-8")
        _git(self.root, "add", "-A", "-f")
        self.assertNotEqual(before, self.pure_scope_hash())

    def test_only_findings_and_reviews_are_outside_the_hash(self):
        """No tracked source is silently hidden: the number of hashed files
        must equal the tracked files minus exactly the two documented
        prefixes."""
        _git(self.root, "add", "-A")
        expected = [
            path for path in self.tracked_files()
            if not path.startswith(("factory/findings/", "factory/reviews/"))
        ]
        result = self.run_pure(str(self.guards_dir / "scope_hash.py"))
        self.assertEqual(result.returncode, 0, result.stderr)
        counted = None
        for line in result.stdout.splitlines():
            if line.startswith("scope_files:"):
                counted = int(line.split(":", 1)[1])
        self.assertIsNotNone(counted)
        self.assertEqual(counted, len(expected))
        self.assertIn("factory/guards/validate-finding.py", expected)
        self.assertIn("app/code.py", expected)


if __name__ == "__main__":
    unittest.main()
