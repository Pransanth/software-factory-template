"""Tests for validate-review.py.

Run with:
    python3 -m unittest factory.guards.test_validate_review

Like test_validate_finding.py, this invokes the guard as a subprocess
against temporary fixture files -- never against a real file under
factory/reviews/.

validate-review.py cross-checks that the "Finding" value names a file that
actually exists under <repo-root>/factory/findings/, resolving <repo-root>
from its own location. So each test copies the guard into a throwaway
project tree (tmp/factory/guards/validate-review.py) that has its own
tmp/factory/findings/ with one fixture finding. That keeps these tests
independent of whichever findings a concrete project happens to have --
this file is part of a transferable template and must not assume any
particular finding ID exists.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REAL_SCRIPT = Path(__file__).resolve().parent / "validate-review.py"

EXISTING_FINDING_ID = "EXAMPLE-1"

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
Reviewed Commit: working tree at abc123, uncommitted changes included
Result: PASS
Root Cause Addressed: Ja -- die Reparatur entfernt den frei waehlbaren Parameter.
Regression Evidence Checked: Regressionstest gelesen, Assertion unveraendert.
Guard Evidence Checked: Zentraler Guard gelesen und Negativtest bestaetigt.
Scope Checked: Nur die im Bauauftrag genannten Pfade veraendert.
Remaining Risks: Absichtliche Umgehung ueber dynamische Attribute bleibt technisch moeglich.
Findings And Objections: Keine.
"""

MISSING_FIELDS = """\
# EXAMPLE-1

Finding: EXAMPLE-1
Result: PASS
"""

INVALID_RESULT_VALUE = VALID_REVIEW.replace("Result: PASS", "Result: LOOKS_GOOD_TO_ME")

UNKNOWN_FINDING_REFERENCE = VALID_REVIEW.replace(
    "Finding: EXAMPLE-1", "Finding: P9-DOES-NOT-EXIST"
)

VALID_FAIL_RESULT = VALID_REVIEW.replace("Result: PASS", "Result: FAIL")
VALID_EXPERT_REVIEW_RESULT = VALID_REVIEW.replace("Result: PASS", "Result: EXPERT_REVIEW_REQUIRED")

PLACEHOLDER_FIELD = VALID_REVIEW.replace(
    "Remaining Risks: Absichtliche Umgehung ueber dynamische Attribute bleibt technisch moeglich.",
    "Remaining Risks: TBD",
)

MISSING_REVIEWER_PROVENANCE = VALID_REVIEW.replace(
    "Reviewer Agent Type: finding-closure-reviewer\nReviewer Agent ID: agent-test-0001\n", ""
)

WRONG_REVIEWER_AGENT_TYPE = VALID_REVIEW.replace(
    "Reviewer Agent Type: finding-closure-reviewer",
    "Reviewer Agent Type: main-agent",
)


class ValidateReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-review-guard-test-"))
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        guards_dir = self.tmp_dir / "factory" / "guards"
        findings_dir = self.tmp_dir / "factory" / "findings"
        self.reviews_dir = self.tmp_dir / "factory" / "reviews"
        guards_dir.mkdir(parents=True)
        findings_dir.mkdir(parents=True)
        self.reviews_dir.mkdir(parents=True)

        self.script = guards_dir / "validate-review.py"
        shutil.copy2(REAL_SCRIPT, self.script)
        (findings_dir / f"{EXISTING_FINDING_ID}.md").write_text(
            FIXTURE_FINDING, encoding="utf-8"
        )

    def run_guard(self, content):
        review_path = self.reviews_dir / "review-under-test.md"
        review_path.write_text(content, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(self.script), str(review_path)],
            capture_output=True,
            text=True,
        )

    def test_valid_review_with_result_pass(self):
        result = self.run_guard(VALID_REVIEW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)
        self.assertIn("PASS", result.stdout)

    def test_valid_review_with_result_fail(self):
        result = self.run_guard(VALID_FAIL_RESULT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_valid_review_with_result_expert_review_required(self):
        result = self.run_guard(VALID_EXPERT_REVIEW_RESULT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_missing_fields_are_rejected(self):
        result = self.run_guard(MISSING_FIELDS)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Reviewer", result.stderr)
        self.assertIn("Reviewer Agent Type", result.stderr)
        self.assertIn("Reviewer Agent ID", result.stderr)
        self.assertIn("Reviewed Commit", result.stderr)
        self.assertIn("Root Cause Addressed", result.stderr)
        self.assertIn("Regression Evidence Checked", result.stderr)
        self.assertIn("Guard Evidence Checked", result.stderr)
        self.assertIn("Scope Checked", result.stderr)
        self.assertIn("Remaining Risks", result.stderr)
        self.assertIn("Findings And Objections", result.stderr)

    def test_placeholder_field_value_is_rejected(self):
        result = self.run_guard(PLACEHOLDER_FIELD)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Remaining Risks", result.stderr)

    def test_invalid_result_value_is_rejected(self):
        result = self.run_guard(INVALID_RESULT_VALUE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ungültigen Wert", result.stderr)

    def test_finding_reference_to_nonexistent_finding_is_rejected(self):
        result = self.run_guard(UNKNOWN_FINDING_REFERENCE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("P9-DOES-NOT-EXIST", result.stderr)

    def test_missing_reviewer_provenance_is_rejected(self):
        result = self.run_guard(MISSING_REVIEWER_PROVENANCE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Reviewer Agent Type", result.stderr)
        self.assertIn("Reviewer Agent ID", result.stderr)

    def test_wrong_reviewer_agent_type_is_rejected(self):
        result = self.run_guard(WRONG_REVIEWER_AGENT_TYPE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Reviewer Agent Type", result.stderr)
        self.assertIn("main-agent", result.stderr)


if __name__ == "__main__":
    unittest.main()
