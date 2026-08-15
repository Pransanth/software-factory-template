"""Tests for the shared factory runner run-factory-checks.py.

Run with:
    python3 -m unittest factory.guards.test_run_factory_checks

Each test builds a throwaway git project (copies of the real guard scripts,
plus factory/findings, factory/reviews and a stamped control-plane
manifest) and runs the copied runner there. No real finding and no real
review artifact of this repository is ever touched or read.

Copying instead of pointing the real runner at temporary directories is
deliberate: the guards resolve <repo-root> from their own location, and
both the scope hash (factory/guards/scope_hash.py) and the control-plane
manifest are defined relative to that root. Running the copies makes that
root the throwaway tree, so these tests do not depend on which findings a
concrete project happens to have -- this file is part of a transferable
template.

The fixture is a real git repository because the scope hash is computed
over tracked files; see scope_hash.py for why that is the definition.
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
    "run-factory-checks.py",
    "validate-finding.py",
    "validate-review.py",
    "validate-control-plane.py",
    "scope_hash.py",
)

GIT_ENV_OVERRIDES = {
    "GIT_AUTHOR_NAME": "Factory Test",
    "GIT_AUTHOR_EMAIL": "factory-test@example.invalid",
    "GIT_COMMITTER_NAME": "Factory Test",
    "GIT_COMMITTER_EMAIL": "factory-test@example.invalid",
}

VALID_OPEN_A = """\
# TEST-A

Status: OPEN

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Not yet analyzed
"""

VALID_OPEN_B = """\
# TEST-B

Status: OPEN

## Befund

Andere Beispielbeschreibung.

## Analyse

Root Cause: TBD
"""

INVALID_ANALYZED = """\
# TEST-BROKEN

Status: ANALYZED
Severity: P1

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Not yet analyzed
"""

FIXTURE_FINDING_ID = "EXAMPLE-1"

FIXTURE_FINDING = """\
# EXAMPLE-1

Status: OPEN

## Befund

Beispielbeschreibung.
"""

REVIEW_TEMPLATE = """\
# {finding}

Finding: {finding}
Reviewer: finding-closure-reviewer subagent
Reviewer Agent Type: finding-closure-reviewer
Reviewer Agent ID: agent-test-0001
Reviewed Commit: abc123
Reviewed Scope Hash: {scope_hash}
Result: {result}
Root Cause Addressed: Ja.
Regression Evidence Checked: Ja.
Guard Evidence Checked: Ja.
Scope Checked: Ja.
Remaining Risks: Keine.
Findings And Objections: Keine.
"""

BROKEN_REVIEW = """\
# EXAMPLE-1

Finding: EXAMPLE-1
Result: PASS
"""

CLOSURE_FINDING = """\
# {finding}

Status: {status}
Severity: P1

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Fehlende Pruefung beim Erstellen neuer Auftraege.
Affected Components: Scheduler, Worker.
Relevant Architecture: Auftraege laufen ohne zentralen Filter.
Recommended Repair: Zentralen Guard einfuehren, der den Filter erzwingt.
Regression Test Plan: Neue Tests fuer Auftraege mit falschem/fehlendem Filter.
Central Guard Plan: Guard-Funktion, die jeder Registrierung vorgeschaltet wird.
Expected Blast Radius: Nur neue Auftraege, keine bestehenden Endpunkte.
Risk Assessment: Gering, da rein additive Pruefung ohne bestehendes Verhalten zu aendern.
Verification Evidence: Alle relevanten Tests gruen.
CI Evidence: GitHub-Actions-Run 123 auf dem Finding-Branch, conclusion success.
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


class RunFactoryChecksTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-runner-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.root = self.tmp_dir / "project"

        guards_dir = self.root / "factory" / "guards"
        self.findings_dir = self.root / "factory" / "findings"
        self.reviews_dir = self.root / "factory" / "reviews"
        guards_dir.mkdir(parents=True)
        self.findings_dir.mkdir(parents=True)
        self.reviews_dir.mkdir(parents=True)
        (self.root / "app").mkdir()
        (self.root / "app" / "code.py").write_text("VALUE = 1\n", encoding="utf-8")

        for name in GUARD_FILES:
            shutil.copy2(REAL_GUARDS_DIR / name, guards_dir / name)
        self.script = guards_dir / "run-factory-checks.py"
        self.control_plane_guard = guards_dir / "validate-control-plane.py"

        # One finding that review fixtures may legitimately reference.
        self.write_finding(f"{FIXTURE_FINDING_ID}.md", FIXTURE_FINDING)

        _git(self.root, "init", "--initial-branch=trunk")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "initial")
        self.stamp_control_plane()

    def stamp_control_plane(self):
        result = subprocess.run(
            [
                sys.executable,
                str(self.control_plane_guard),
                "--repo-root",
                str(self.root),
                "--update",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def scope_hash(self):
        result = subprocess.run(
            [sys.executable, str(self.root / "factory" / "guards" / "scope_hash.py")],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in result.stdout.splitlines():
            if line.startswith("scope_hash:"):
                return line.split(":", 1)[1].strip()
        self.fail("no scope_hash line")

    def write_finding(self, name, content):
        (self.findings_dir / name).write_text(content, encoding="utf-8")

    def write_review(self, name, content):
        (self.reviews_dir / name).write_text(content, encoding="utf-8")

    def write_round(self, finding_id, round_number, result="PASS"):
        self.write_review(
            f"{finding_id}.round-{round_number}.md",
            REVIEW_TEMPLATE.format(
                finding=finding_id, result=result, scope_hash=self.scope_hash()
            ),
        )

    def run_runner(self, *extra_args):
        return subprocess.run(
            [sys.executable, str(self.script), *extra_args],
            capture_output=True,
            text=True,
        )

    # -- findings ----------------------------------------------------------

    def test_all_valid_findings_pass(self):
        self.write_finding("a.md", VALID_OPEN_A)
        self.write_finding("b.md", VALID_OPEN_B)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)
        self.assertIn("[OK]", result.stdout)

    def test_single_invalid_finding_fails(self):
        self.write_finding("broken.md", INVALID_ANALYZED)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn("broken.md", result.stderr)
        self.assertIn("FEHLGESCHLAGEN", result.stderr)

    def test_mixed_findings_report_only_the_broken_one(self):
        self.write_finding("a.md", VALID_OPEN_A)
        self.write_finding("broken.md", INVALID_ANALYZED)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("[OK]     finding-validator: a.md", combined)
        self.assertIn("[FEHLER] finding-validator: broken.md", combined)

    def test_no_findings_at_all_is_not_a_failure(self):
        empty_findings = self.tmp_dir / "empty-findings"
        empty_findings.mkdir()
        result = self.run_runner("--findings-dir", str(empty_findings))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)

    # -- reviews -----------------------------------------------------------

    def test_valid_review_passes(self):
        self.write_round(FIXTURE_FINDING_ID, 1)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"[OK]     review-guard: {FIXTURE_FINDING_ID}.round-1.md", result.stdout)

    def test_broken_review_fails(self):
        self.write_review(f"{FIXTURE_FINDING_ID}.round-1.md", BROKEN_REVIEW)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            f"[FEHLER] review-guard: {FIXTURE_FINDING_ID}.round-1.md", result.stderr
        )
        self.assertIn("FEHLGESCHLAGEN", result.stderr)

    def test_review_with_non_canonical_filename_fails(self):
        """A file named <ID>.md is the pre-repair, overwriting format."""
        self.write_review(
            f"{FIXTURE_FINDING_ID}.md",
            REVIEW_TEMPLATE.format(
                finding=FIXTURE_FINDING_ID, result="PASS", scope_hash=self.scope_hash()
            ),
        )
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)

    def test_readme_in_reviews_dir_is_not_checked(self):
        # README.md documents the format; it is not a review artifact.
        self.write_review("README.md", BROKEN_REVIEW)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("README.md", result.stdout + result.stderr)

    def test_no_reviews_at_all_is_not_a_failure(self):
        empty_reviews = self.tmp_dir / "empty-reviews"
        empty_reviews.mkdir()
        result = self.run_runner("--reviews-dir", str(empty_reviews))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)

    def test_invalid_finding_and_broken_review_are_both_reported(self):
        self.write_finding("broken.md", INVALID_ANALYZED)
        self.write_review(f"{FIXTURE_FINDING_ID}.round-1.md", BROKEN_REVIEW)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("[FEHLER] finding-validator: broken.md", combined)
        self.assertIn(f"[FEHLER] review-guard: {FIXTURE_FINDING_ID}.round-1.md", combined)

    # -- closure, end to end through the one canonical entry point ---------

    def test_ready_for_closure_with_its_own_pass_round_passes_end_to_end(self):
        self.write_round(FIXTURE_FINDING_ID, 1, result="PASS")
        self.write_finding(
            f"{FIXTURE_FINDING_ID}.md",
            CLOSURE_FINDING.format(
                finding=FIXTURE_FINDING_ID,
                status="READY_FOR_CLOSURE",
                review_artifact=f"factory/reviews/{FIXTURE_FINDING_ID}.round-1.md",
            ),
        )
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)

    def test_ready_for_closure_with_failing_review_is_blocked(self):
        self.write_round(FIXTURE_FINDING_ID, 1, result="FAIL")
        self.write_finding(
            f"{FIXTURE_FINDING_ID}.md",
            CLOSURE_FINDING.format(
                finding=FIXTURE_FINDING_ID,
                status="READY_FOR_CLOSURE",
                review_artifact=f"factory/reviews/{FIXTURE_FINDING_ID}.round-1.md",
            ),
        )
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"[FEHLER] finding-validator: {FIXTURE_FINDING_ID}.md", result.stderr)

    # -- control plane ------------------------------------------------------

    def test_runner_reports_the_control_plane_check(self):
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("control-plane-guard", result.stdout)

    def test_runner_fails_when_a_guard_was_modified(self):
        """A finding branch must not be able to weaken the guard checking it."""
        guard_path = self.root / "factory" / "guards" / "validate-finding.py"
        guard_path.write_text(
            guard_path.read_text(encoding="utf-8") + "\n# quietly modified\n",
            encoding="utf-8",
        )
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn("control-plane-guard", result.stderr)
        self.assertIn("validate-finding.py", result.stderr)

    def test_runner_fails_when_the_control_plane_manifest_is_missing(self):
        (self.root / "factory" / "control-plane.sha256").unlink()
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn("control-plane-guard", result.stderr)


if __name__ == "__main__":
    unittest.main()
