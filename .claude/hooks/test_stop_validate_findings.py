"""Tests for the Stop hook wrapper stop-validate-findings.py.

Run with:
    python3 .claude/hooks/test_stop_validate_findings.py

(".claude" starts with a dot, so it cannot be addressed as a normal dotted
unittest module path like "factory.guards.test_validate_finding" -- running
the file directly works the same way via its own unittest.main() call.)

Each test builds a throwaway project directory (a copy of the real
factory/guards/validate-finding.py and run-factory-checks.py, plus one
finding file) and points the hook at it via CLAUDE_PROJECT_DIR, then
invokes the hook exactly the way Claude Code does: JSON on stdin, exit code
as the result. The real factory/findings/P1-DEMO-1.md is never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO_ROOT / ".claude" / "hooks" / "stop-validate-findings.py"
REAL_GUARDS_DIR = REPO_ROOT / "factory" / "guards"

VALID_OPEN_FINDING = """\
# TEST-OPEN

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

INVALID_ANALYZED_FINDING = """\
# TEST-ANALYZED-INCOMPLETE

Status: ANALYZED

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Not yet analyzed
"""

VALID_ANALYZED_FINDING = """\
# TEST-ANALYZED-INCOMPLETE

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


class StopHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="factory-hook-test-")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        self.project_root = Path(self.tmp_dir)
        guards_dir = self.project_root / "factory" / "guards"
        self.findings_dir = self.project_root / "factory" / "findings"
        guards_dir.mkdir(parents=True)
        self.findings_dir.mkdir(parents=True)
        shutil.copy2(REAL_GUARDS_DIR / "validate-finding.py", guards_dir / "validate-finding.py")
        shutil.copy2(
            REAL_GUARDS_DIR / "run-factory-checks.py", guards_dir / "run-factory-checks.py"
        )
        # Always the same single finding file, its content changes per test
        # to simulate "the finding gets fixed between two stop attempts".
        self.finding_path = self.findings_dir / "finding.md"

    def write_finding(self, content):
        self.finding_path.write_text(content, encoding="utf-8")

    def run_hook(self, stop_hook_active=False):
        hook_input = {
            "session_id": "test-session",
            "hook_event_name": "Stop",
            "cwd": str(self.project_root),
            "stop_hook_active": stop_hook_active,
        }
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project_root)
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            env=env,
        )

    def test_hook_allows_stop_when_all_findings_valid(self):
        self.write_finding(VALID_OPEN_FINDING)
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hook_blocks_stop_when_a_finding_is_invalid(self):
        self.write_finding(INVALID_ANALYZED_FINDING)
        result = self.run_hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("finding.md", result.stderr)
        self.assertIn("Pflichtfeld", result.stderr)
        # The hook must not re-implement the check itself: the failure text
        # comes straight from the canonical runner's own report format.
        self.assertIn("[FEHLER]", result.stderr)

    def test_hook_allows_repeat_stop_once_finding_is_actually_fixed(self):
        # First attempt: invalid, gets blocked.
        self.write_finding(INVALID_ANALYZED_FINDING)
        first = self.run_hook(stop_hook_active=False)
        self.assertEqual(first.returncode, 2)

        # Claude "fixes" the finding, then tries to stop again.
        self.write_finding(VALID_ANALYZED_FINDING)
        second = self.run_hook(stop_hook_active=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotIn("WARNUNG", second.stdout + second.stderr)

    def test_hook_blocks_again_when_still_invalid_on_repeat_stop(self):
        # stop_hook_active=True must NOT be treated as proof the finding is
        # now valid: the hook always re-checks the real state and blocks
        # again if it is still broken. Loop prevention is Claude Code's own
        # documented block cap, not something this hook fakes by silently
        # allowing an invalid state through.
        self.write_finding(INVALID_ANALYZED_FINDING)
        result = self.run_hook(stop_hook_active=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("finding.md", result.stderr)
        self.assertIn("wiederholter Stop-Versuch", result.stderr)


if __name__ == "__main__":
    unittest.main()
