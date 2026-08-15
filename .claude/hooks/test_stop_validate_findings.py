"""Tests for the Stop hook wrapper stop-validate-findings.py.

Run with:
    python3 .claude/hooks/test_stop_validate_findings.py

(".claude" starts with a dot, so it cannot be addressed as a normal dotted
unittest module path like "factory.guards.test_validate_finding" -- running
the file directly works the same way via its own unittest.main() call.)

Each test builds a throwaway project directory (copies of the real factory
guards plus one finding file) and points the hook at it via
CLAUDE_PROJECT_DIR, then invokes the hook exactly the way Claude Code
does: JSON on stdin, exit code as the result. No real finding and no real
review artifact of this repository is ever touched -- these throwaway
projects have no factory/reviews/ directory at all, which
run-factory-checks.py treats as "nothing to check" for that dimension.

The fixture is a real git repository with a stamped control-plane manifest,
because the canonical runner now also verifies the control plane (see
factory/guards/validate-control-plane.py). That check reads `git ls-files`,
so a bare directory would fail it for the wrong reason.
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

GUARD_FILES = (
    "validate-finding.py",
    "run-factory-checks.py",
    "validate-review.py",
    "validate-build-order.py",
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
Severity: P1

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Not yet analyzed
"""

VALID_ANALYZED_FINDING = """\
# TEST-ANALYZED-INCOMPLETE

Status: ANALYZED
Severity: P1

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

# A P0 must never be worked through the normal lifecycle -- the Stop hook
# has to surface that, because it is the first place a session notices.
P0_IN_IMPLEMENTING = VALID_ANALYZED_FINDING.replace(
    "Status: ANALYZED\nSeverity: P1", "Status: IMPLEMENTING\nSeverity: P0"
)


def _git(cwd, *args):
    env = dict(os.environ)
    env.update(GIT_ENV_OVERRIDES)
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


class StopHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="factory-hook-test-")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        self.project_root = Path(self.tmp_dir).resolve()
        guards_dir = self.project_root / "factory" / "guards"
        self.findings_dir = self.project_root / "factory" / "findings"
        guards_dir.mkdir(parents=True)
        self.findings_dir.mkdir(parents=True)
        for name in GUARD_FILES:
            shutil.copy2(REAL_GUARDS_DIR / name, guards_dir / name)

        _git(self.project_root, "init", "--initial-branch=trunk")
        _git(self.project_root, "add", "-A")
        _git(self.project_root, "commit", "-m", "initial")
        stamp = subprocess.run(
            [
                sys.executable,
                str(guards_dir / "validate-control-plane.py"),
                "--repo-root",
                str(self.project_root),
                "--update",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(stamp.returncode, 0, stamp.stderr)

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

    def test_hook_blocks_stop_on_a_p0_in_the_normal_lifecycle(self):
        self.write_finding(P0_IN_IMPLEMENTING)
        result = self.run_hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("P0", result.stderr)

    def test_hook_blocks_stop_when_the_control_plane_drifted(self):
        """A finding run that changed a guard must not end quietly."""
        self.write_finding(VALID_OPEN_FINDING)
        guard = self.project_root / "factory" / "guards" / "validate-finding.py"
        guard.write_text(
            guard.read_text(encoding="utf-8") + "\n# quietly modified\n", encoding="utf-8"
        )
        result = self.run_hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("control-plane", result.stderr)

    def test_hook_allows_repeat_stop_once_finding_is_actually_fixed(self):
        # First attempt: invalid, gets blocked.
        self.write_finding(INVALID_ANALYZED_FINDING)
        first = self.run_hook(stop_hook_active=False)
        self.assertEqual(first.returncode, 2)

        # Claude "fixes" the finding, then tries to stop again. This still
        # passes under the current hook -- but see the next test: it would
        # pass even if the finding were NOT actually fixed, since a repeat
        # attempt (stop_hook_active=True) is never re-checked or blocked a
        # second time. This test only shows the fixed case still works, not
        # that fixing was what made it pass.
        self.write_finding(VALID_ANALYZED_FINDING)
        second = self.run_hook(stop_hook_active=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotIn("WARNUNG", second.stdout + second.stderr)

    def test_hook_does_not_block_again_on_repeat_stop_even_if_still_invalid(self):
        # This is the key behavior: stop_hook_active=True means "this hook
        # already blocked once for this turn" -- it now exits 0 immediately
        # without even re-running the canonical checks, on purpose,
        # regardless of whether the underlying state is still invalid. Loop
        # prevention is this hook's own job, not a platform block-cap that
        # turned out not to reliably fire. The real, unbypassable gate is
        # GitHub CI, not this local hook -- see the module docstring and
        # factory/README.md.
        self.write_finding(INVALID_ANALYZED_FINDING)

        first = self.run_hook(stop_hook_active=False)
        self.assertEqual(first.returncode, 2)
        self.assertIn("finding.md", first.stderr)

        second = self.run_hook(stop_hook_active=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        # It must not even re-run the canonical runner's report on retry.
        self.assertNotIn("[FEHLER]", second.stdout + second.stderr)
        self.assertIn("wiederholter Stop-Versuch", second.stdout)
        self.assertIn("GitHub CI", second.stdout)

    def test_hook_first_attempt_ignores_stop_hook_active_flag_value(self):
        # stop_hook_active is only ever meaningful as "true" (a genuine
        # repeat). A caller sending stop_hook_active=False still gets the
        # normal, first-attempt check-and-block behavior even on what would
        # otherwise look like a "second" call -- this hook has no memory of
        # prior calls, it only trusts the flag in the current event.
        self.write_finding(INVALID_ANALYZED_FINDING)
        result = self.run_hook(stop_hook_active=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("[FEHLER]", result.stderr)


if __name__ == "__main__":
    unittest.main()
