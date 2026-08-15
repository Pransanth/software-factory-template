"""Tests for the shared factory runner run-factory-checks.py.

Run with:
    python3 -m unittest factory.guards.test_run_factory_checks

Each test builds a throwaway project tree (tmp/factory/guards with copies
of the three real scripts, plus tmp/factory/findings and
tmp/factory/reviews) and runs the copied runner there. No real finding and
no real review artifact of this repository is ever touched or read.

Copying instead of pointing the real runner at temporary directories is
deliberate: validate-review.py cross-checks that a review's "Finding"
names an existing file under <repo-root>/factory/findings/, resolving
<repo-root> from its own location. Running the copies makes that root the
throwaway tree, so these tests do not depend on which findings a concrete
project happens to have -- this file is part of a transferable template.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REAL_GUARDS_DIR = Path(__file__).resolve().parent

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

VALID_REVIEW = """\
# EXAMPLE-1

Finding: EXAMPLE-1
Reviewer: finding-closure-reviewer subagent
Reviewer Agent Type: finding-closure-reviewer
Reviewer Agent ID: agent-test-0001
Reviewed Commit: abc123
Result: PASS
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


class RunFactoryChecksTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-runner-test-"))
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        guards_dir = self.tmp_dir / "factory" / "guards"
        self.findings_dir = self.tmp_dir / "factory" / "findings"
        self.reviews_dir = self.tmp_dir / "factory" / "reviews"
        guards_dir.mkdir(parents=True)
        self.findings_dir.mkdir(parents=True)
        self.reviews_dir.mkdir(parents=True)

        for name in ("run-factory-checks.py", "validate-finding.py", "validate-review.py"):
            shutil.copy2(REAL_GUARDS_DIR / name, guards_dir / name)
        self.script = guards_dir / "run-factory-checks.py"

        # One finding that review fixtures may legitimately reference.
        self.write_finding(f"{FIXTURE_FINDING_ID}.md", FIXTURE_FINDING)

    def write_finding(self, name, content):
        (self.findings_dir / name).write_text(content, encoding="utf-8")

    def write_review(self, name, content):
        (self.reviews_dir / name).write_text(content, encoding="utf-8")

    def run_runner(self, *extra_args):
        return subprocess.run(
            [sys.executable, str(self.script), *extra_args],
            capture_output=True,
            text=True,
        )

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

    def test_valid_review_passes(self):
        self.write_review(f"{FIXTURE_FINDING_ID}.md", VALID_REVIEW)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"[OK]     review-guard: {FIXTURE_FINDING_ID}.md", result.stdout)

    def test_broken_review_fails(self):
        self.write_review(f"{FIXTURE_FINDING_ID}.md", BROKEN_REVIEW)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"[FEHLER] review-guard: {FIXTURE_FINDING_ID}.md", result.stderr)
        self.assertIn("FEHLGESCHLAGEN", result.stderr)

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
        self.write_review("broken-review.md", BROKEN_REVIEW)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("[FEHLER] finding-validator: broken.md", combined)
        self.assertIn("[FEHLER] review-guard: broken-review.md", combined)

    def test_ready_for_closure_finding_with_matching_pass_review_passes_end_to_end(self):
        review_path = self.reviews_dir / "TEST-CLOSURE.md"
        review_path.write_text(
            VALID_REVIEW.replace("Finding: EXAMPLE-1", f"Finding: {FIXTURE_FINDING_ID}"),
            encoding="utf-8",
        )

        finding = f"""\
# TEST-CLOSURE

Status: READY_FOR_CLOSURE

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
CI Evidence: GitHub-Actions-Run #123 auf dem Default-Branch, gruen.
Review Artifact: {review_path}
"""
        self.write_finding("TEST-CLOSURE.md", finding)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)

    def test_ready_for_closure_finding_with_failing_review_is_blocked(self):
        review_path = self.reviews_dir / "TEST-CLOSURE-FAIL.md"
        review_path.write_text(VALID_REVIEW.replace("Result: PASS", "Result: FAIL"), encoding="utf-8")

        finding = f"""\
# TEST-CLOSURE-FAIL

Status: READY_FOR_CLOSURE

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
CI Evidence: GitHub-Actions-Run #123 auf dem Default-Branch, gruen.
Review Artifact: {review_path}
"""
        self.write_finding("TEST-CLOSURE-FAIL.md", finding)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[FEHLER] finding-validator: TEST-CLOSURE-FAIL.md", result.stderr)


if __name__ == "__main__":
    unittest.main()
