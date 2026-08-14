"""Tests for validate-finding.py.

Run with:
    python3 -m unittest factory.guards.test_validate_finding

The guard script's filename contains a hyphen ("validate-finding.py"), so it
cannot be imported as a normal Python module. Instead these tests invoke it
the same way any real user (or a future hook/CI job) would: as a
subprocess, checking exit code and printed messages. This also doubles as
an end-to-end check of the CLI itself, not just internal functions.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "validate-finding.py"

VALID_OPEN = """\
# TEST-1

Status: OPEN

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Not yet analyzed
Affected Components: Not yet analyzed
Relevant Architecture: Not yet analyzed
Recommended Repair: Not yet analyzed
Regression Test Plan: Not yet analyzed
Central Guard Plan: Not yet analyzed
Expected Blast Radius: Not yet analyzed
Risk Assessment: Not yet analyzed
"""

UNKNOWN_STATUS = """\
# TEST-2

Status: SOMETHING_MADE_UP

## Befund

Beispielbeschreibung.
"""

ANALYZED_MISSING_FIELDS = """\
# TEST-3

Status: ANALYZED

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Not yet analyzed
Affected Components: TBD
Relevant Architecture: Ein Beispieltext, der tatsaechlich ausgefuellt ist.
Recommended Repair: Ein Beispieltext, der tatsaechlich ausgefuellt ist.
"""

VALID_ANALYZED = """\
# TEST-4

Status: ANALYZED

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Fehlende Pruefung der Organisation beim Erstellen neuer Jobs.
Affected Components: Job-Scheduler, Job-Worker.
Relevant Architecture: Hintergrundjobs laufen ohne zentralen Org-Filter.
Recommended Repair: Zentralen Guard einfuehren, der die Org-ID erzwingt.
Regression Test Plan: Neue Tests fuer Jobs mit falscher/fehlender Org-ID.
Central Guard Plan: Guard-Funktion, die jeder Job-Registrierung vorgeschaltet wird.
Expected Blast Radius: Nur neue Hintergrundjobs, keine bestehenden Endpunkte.
Risk Assessment: Gering, da rein additive Pruefung ohne bestehendes Verhalten zu aendern.
"""

VALID_EXPERT_REVIEW = """\
# TEST-5

Status: EXPERT_REVIEW_REQUIRED

## Befund

Beispielbeschreibung, bei der Claude sich fuer eine Eskalation entscheidet.

## Analyse

Root Cause: Not yet analyzed
Affected Components: Not yet analyzed
Relevant Architecture: Not yet analyzed
Recommended Repair: Not yet analyzed
Regression Test Plan: Not yet analyzed
Central Guard Plan: Not yet analyzed
Expected Blast Radius: Not yet analyzed
Risk Assessment: Moeglicher Zugriff auf Daten einer fremden Organisation, Ausmass unklar.
Expert Review Reason: Die Aenderung beruehrt die Mandantentrennung, das ist zu riskant fuer eine autonome Entscheidung.
What Is Known: Neue Hintergrundjobs koennen ohne Org-Pruefung erstellt werden.
What Remains Uncertain: Ob bereits bestehende Jobs betroffen sind und wie die Datenbank-Isolation aktuell tatsaechlich greift.
What An Expert Would Need To Review: Das Datenbankschema und die bestehende Trennung der Organisationen, bevor ein Guard entworfen wird.
"""

# Same status, but without any real justification for the escalation itself:
# EXPERT_REVIEW_REQUIRED must not be usable as a shortcut around an
# incomplete analysis.
INVALID_EXPERT_REVIEW_MISSING_REASON = """\
# TEST-6

Status: EXPERT_REVIEW_REQUIRED

## Befund

Beispielbeschreibung, bei der Claude sich fuer eine Eskalation entscheidet.

## Analyse

Root Cause: Not yet analyzed
Affected Components: Not yet analyzed
Relevant Architecture: Not yet analyzed
Recommended Repair: Not yet analyzed
Regression Test Plan: Not yet analyzed
Central Guard Plan: Not yet analyzed
Expected Blast Radius: Not yet analyzed
Risk Assessment: Not yet analyzed
Expert Review Reason: TBD
What Is Known: Not yet analyzed
What Remains Uncertain: Not yet analyzed
What An Expert Would Need To Review: Not yet analyzed
"""

# --- Closure gate fixtures (READY_FOR_CLOSURE / CLOSED) ---------------------

FINDING_TEMPLATE_WITH_CLOSURE = """\
# TEST-CLOSURE

Status: {status}

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Fehlende Pruefung der Organisation beim Erstellen neuer Jobs.
Affected Components: Job-Scheduler, Job-Worker.
Relevant Architecture: Hintergrundjobs laufen ohne zentralen Org-Filter.
Recommended Repair: Zentralen Guard einfuehren, der die Org-ID erzwingt.
Regression Test Plan: Neue Tests fuer Jobs mit falscher/fehlender Org-ID.
Central Guard Plan: Guard-Funktion, die jeder Job-Registrierung vorgeschaltet wird.
Expected Blast Radius: Nur neue Hintergrundjobs, keine bestehenden Endpunkte.
Risk Assessment: Gering, da rein additive Pruefung ohne bestehendes Verhalten zu aendern.
{extra_fields}"""

REVIEW_TEMPLATE = """\
# TEST-CLOSURE

Finding: TEST-CLOSURE
Reviewer: test-reviewer
Reviewed Commit: abc123
Result: {result}
Root Cause Addressed: Ja, siehe Analyse.
Regression Evidence Checked: Regressionstest gegengeprueft.
Guard Evidence Checked: Guard-Ausgabe gegengeprueft.
Scope Checked: Ja, im genehmigten Bauauftrags-Scope.
Remaining Risks: Keine.
Findings And Objections: Keine.
"""


class ValidateFindingTests(unittest.TestCase):
    def run_guard(self, content):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(content)
            temp_path = handle.name
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), temp_path],
                capture_output=True,
                text=True,
            )
        finally:
            Path(temp_path).unlink()
        return result

    def test_valid_open_finding(self):
        result = self.run_guard(VALID_OPEN)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_unknown_status_is_rejected(self):
        result = self.run_guard(UNKNOWN_STATUS)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unbekannter Status", result.stderr)

    def test_analyzed_with_missing_fields_is_rejected(self):
        result = self.run_guard(ANALYZED_MISSING_FIELDS)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Regression Test Plan", result.stderr)
        self.assertIn("Central Guard Plan", result.stderr)
        self.assertIn("Expected Blast Radius", result.stderr)
        self.assertIn("Risk Assessment", result.stderr)
        # A placeholder value ("TBD") must also be flagged, not just missing fields.
        self.assertIn("Affected Components", result.stderr)

    def test_valid_analyzed_finding(self):
        result = self.run_guard(VALID_ANALYZED)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_valid_expert_review_required_finding(self):
        result = self.run_guard(VALID_EXPERT_REVIEW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_expert_review_required_without_reason_is_rejected(self):
        result = self.run_guard(INVALID_EXPERT_REVIEW_MISSING_REASON)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Expert Review Reason", result.stderr)
        self.assertIn("What Is Known", result.stderr)
        self.assertIn("What Remains Uncertain", result.stderr)
        self.assertIn("What An Expert Would Need To Review", result.stderr)
        self.assertIn("Risk Assessment", result.stderr)


def _write_temp_file(content, suffix=".md"):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as handle:
        handle.write(content)
        return handle.name


class ValidateFindingClosureGateTests(unittest.TestCase):
    """Closure gate: READY_FOR_CLOSURE and CLOSED additionally require
    Verification Evidence, CI Evidence and a Review Artifact whose
    Result is PASS. Review artifact fixtures use an ABSOLUTE path in the
    "Review Artifact:" field so these tests never touch the real
    factory/reviews/ directory -- validate-finding.py resolves a
    relative path against the real repo root, but leaves an absolute
    path untouched."""

    def setUp(self):
        self._temp_files = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for path in self._temp_files:
            Path(path).unlink(missing_ok=True)

    def write_review(self, result):
        path = _write_temp_file(REVIEW_TEMPLATE.format(result=result))
        self._temp_files.append(path)
        return path

    def write_finding(self, status, extra_fields=""):
        path = _write_temp_file(
            FINDING_TEMPLATE_WITH_CLOSURE.format(status=status, extra_fields=extra_fields)
        )
        self._temp_files.append(path)
        return path

    def run_guard_on(self, path):
        return subprocess.run(
            [sys.executable, str(SCRIPT), path], capture_output=True, text=True
        )

    def full_evidence_fields(self, review_path):
        return (
            "Verification Evidence: Regressionstest gruen, relevante App-Tests gruen.\n"
            "CI Evidence: GitHub Actions Run #123 auf main, gruen.\n"
            f"Review Artifact: {review_path}\n"
        )

    def test_verifying_is_valid_with_verification_evidence_present(self):
        extra = "Verification Evidence: Regressionstest app.jobs.test_org_scope_regression gruen.\n"
        finding_path = self.write_finding("VERIFYING", extra)
        result = self.run_guard_on(finding_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_ready_for_closure_without_closure_fields_is_rejected(self):
        finding_path = self.write_finding("READY_FOR_CLOSURE", "")
        result = self.run_guard_on(finding_path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Verification Evidence", result.stderr)
        self.assertIn("CI Evidence", result.stderr)
        self.assertIn("Review Artifact", result.stderr)

    def test_ready_for_closure_with_review_fail_is_rejected(self):
        review_path = self.write_review("FAIL")
        finding_path = self.write_finding("READY_FOR_CLOSURE", self.full_evidence_fields(review_path))
        result = self.run_guard_on(finding_path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Result 'FAIL'", result.stderr)

    def test_ready_for_closure_is_blocked_when_review_result_is_expert_review_required(self):
        review_path = self.write_review("EXPERT_REVIEW_REQUIRED")
        finding_path = self.write_finding("READY_FOR_CLOSURE", self.full_evidence_fields(review_path))
        result = self.run_guard_on(finding_path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("EXPERT_REVIEW_REQUIRED", result.stderr)

    def test_ready_for_closure_with_review_pass_and_full_evidence_is_accepted(self):
        review_path = self.write_review("PASS")
        finding_path = self.write_finding("READY_FOR_CLOSURE", self.full_evidence_fields(review_path))
        result = self.run_guard_on(finding_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_closed_without_full_evidence_is_rejected(self):
        finding_path = self.write_finding("CLOSED", "")
        result = self.run_guard_on(finding_path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Review Artifact", result.stderr)

    def test_closed_with_full_evidence_and_review_pass_is_accepted(self):
        review_path = self.write_review("PASS")
        finding_path = self.write_finding("CLOSED", self.full_evidence_fields(review_path))
        result = self.run_guard_on(finding_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_review_artifact_pointing_at_missing_file_is_rejected(self):
        extra = (
            "Verification Evidence: Alle Tests gruen.\n"
            "CI Evidence: GitHub Actions Run #123, gruen.\n"
            "Review Artifact: /nonexistent/path/to/review-does-not-exist.md\n"
        )
        finding_path = self.write_finding("READY_FOR_CLOSURE", extra)
        result = self.run_guard_on(finding_path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("existiert", result.stderr)


if __name__ == "__main__":
    unittest.main()
