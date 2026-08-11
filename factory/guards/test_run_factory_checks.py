"""Tests for the canonical factory check runner run-factory-checks.py.

Run with:
    python3 -m unittest factory.guards.test_run_factory_checks

These tests point the real runner at temporary findings directories via
--findings-dir, so the real factory/findings/P1-DEMO-1.md is never touched.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "run-factory-checks.py"

VALID_OPEN_A = """\
# TEST-A

Status: OPEN

## Befund

Beispielbeschreibung A.

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

VALID_OPEN_B = VALID_OPEN_A.replace("TEST-A", "TEST-B").replace(
    "Beispielbeschreibung A.", "Beispielbeschreibung B."
)

INVALID_ANALYZED = """\
# TEST-BROKEN

Status: ANALYZED

## Befund

Beispielbeschreibung, unvollstaendig analysiert.

## Analyse

Root Cause: Not yet analyzed
"""


class RunFactoryChecksTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="factory-runner-test-")
        self.findings_dir = Path(self.tmp_dir)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def write_finding(self, name, content):
        (self.findings_dir / name).write_text(content, encoding="utf-8")

    def run_runner(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--findings-dir", str(self.findings_dir)],
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
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)


if __name__ == "__main__":
    unittest.main()
