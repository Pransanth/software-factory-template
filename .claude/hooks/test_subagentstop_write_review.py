"""Tests for the SubagentStop hook wrapper subagentstop-write-review.py.

Run with:
    python3 .claude/hooks/test_subagentstop_write_review.py

(".claude" starts with a dot, so it cannot be addressed as a normal dotted
unittest module path -- running the file directly works via its own
unittest.main() call, same as test_stop_validate_findings.py.)

Each test builds a throwaway project directory and points the hook at it via
CLAUDE_PROJECT_DIR, then invokes the hook exactly the way Claude Code does:
JSON on stdin (agent_type, agent_id, last_assistant_message), exit code and
factory/reviews/ contents as the result. The real factory/reviews/ and the
real factory/findings/ are never touched or referenced -- these tests use
synthetic finding IDs and never advance any real finding's status.
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
HOOK_SCRIPT = REPO_ROOT / ".claude" / "hooks" / "subagentstop-write-review.py"
REAL_GUARDS_DIR = REPO_ROOT / "factory" / "guards"
REAL_SETTINGS_JSON = REPO_ROOT / ".claude" / "settings.json"

EXPECTED_AGENT_TYPE = "finding-closure-reviewer"

FIELD_ORDER = [
    "Finding",
    "Reviewer",
    "Reviewed Commit",
    "Result",
    "Root Cause Addressed",
    "Regression Evidence Checked",
    "Guard Evidence Checked",
    "Scope Checked",
    "Remaining Risks",
    "Findings And Objections",
]


def build_message(finding="TEST-FINDING-1", result="PASS", omit_fields=(), result_text=None):
    """Build a well-formed (unless tampered with) last_assistant_message,
    mirroring the fenced-block template in
    .claude/agents/finding-closure-reviewer.md."""
    values = {
        "Finding": finding,
        "Reviewer": "finding-closure-reviewer subagent",
        "Reviewed Commit": "uncommitted working tree changes since commit abc123",
        "Result": result_text if result_text is not None else result,
        "Root Cause Addressed": "Yes, see src/foo.py:10.",
        "Regression Evidence Checked": "Read test_foo.py, assertion matches the claim.",
        "Guard Evidence Checked": "Read validate-x.py, matches its own tests.",
        "Scope Checked": "Matches the build order's declared scope.",
        "Remaining Risks": "None identified",
        "Findings And Objections": "None",
    }
    lines = [
        f"{name}: {values[name]}" for name in FIELD_ORDER if name not in omit_fields
    ]
    block = "\n".join(lines)
    return "Here is my independent review:\n\n```\n" + block + "\n```"


class SubagentStopReviewHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="factory-subagentstop-hook-test-")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.project_root = Path(self.tmp_dir)

        guards_dir = self.project_root / "factory" / "guards"
        self.findings_dir = self.project_root / "factory" / "findings"
        self.reviews_dir = self.project_root / "factory" / "reviews"
        guards_dir.mkdir(parents=True)
        self.findings_dir.mkdir(parents=True)
        # Deliberately do NOT pre-create factory/reviews/ -- the hook must
        # create it itself if missing.
        shutil.copy2(REAL_GUARDS_DIR / "validate-review.py", guards_dir / "validate-review.py")
        shutil.copy2(REAL_GUARDS_DIR / "validate-finding.py", guards_dir / "validate-finding.py")

    def run_hook(self, agent_type=EXPECTED_AGENT_TYPE, agent_id="agent-test-0001", message=None):
        hook_input = {
            "session_id": "test-session",
            "hook_event_name": "SubagentStop",
            "cwd": str(self.project_root),
            "agent_type": agent_type,
            "last_assistant_message": message,
        }
        if agent_id is not None:
            hook_input["agent_id"] = agent_id
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project_root)
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            env=env,
        )

    def review_path(self, finding):
        return self.reviews_dir / f"{finding}.md"

    def run_validate_review(self, path):
        return subprocess.run(
            [sys.executable, str(self.project_root / "factory" / "guards" / "validate-review.py"), str(path)],
            capture_output=True,
            text=True,
        )

    def run_validate_finding(self, path):
        return subprocess.run(
            [sys.executable, str(self.project_root / "factory" / "guards" / "validate-finding.py"), str(path)],
            capture_output=True,
            text=True,
        )

    # -- happy paths -----------------------------------------------------

    def test_pass_from_correct_agent_type_writes_valid_review_artifact(self):
        message = build_message(finding="TEST-PASS-1", result="PASS")
        result = self.run_hook(message=message)
        self.assertEqual(result.returncode, 0, result.stderr)

        artifact = self.review_path("TEST-PASS-1")
        self.assertTrue(artifact.is_file())
        content = artifact.read_text(encoding="utf-8")
        self.assertIn("Result: PASS", content)
        self.assertIn("Reviewer Agent Type: finding-closure-reviewer", content)
        self.assertIn("Reviewer Agent ID: agent-test-0001", content)

    def test_fail_result_is_preserved(self):
        message = build_message(finding="TEST-FAIL-1", result="FAIL")
        result = self.run_hook(message=message)
        self.assertEqual(result.returncode, 0, result.stderr)
        content = self.review_path("TEST-FAIL-1").read_text(encoding="utf-8")
        self.assertIn("Result: FAIL", content)
        self.assertNotIn("Result: PASS", content)

    def test_expert_review_required_result_is_preserved(self):
        message = build_message(finding="TEST-EXPERT-1", result="EXPERT_REVIEW_REQUIRED")
        result = self.run_hook(message=message)
        self.assertEqual(result.returncode, 0, result.stderr)
        content = self.review_path("TEST-EXPERT-1").read_text(encoding="utf-8")
        self.assertIn("Result: EXPERT_REVIEW_REQUIRED", content)

    # -- agent type gate ---------------------------------------------------

    def test_wrong_agent_type_writes_no_review(self):
        message = build_message(finding="TEST-WRONG-TYPE-1", result="PASS")
        result = self.run_hook(agent_type="general-purpose", message=message)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.review_path("TEST-WRONG-TYPE-1").exists())
        # No factory/reviews/ directory should even have been created for a
        # non-reviewer agent type.
        self.assertFalse(self.reviews_dir.exists())

    # -- malformed output ---------------------------------------------------

    def test_malformed_output_missing_field_writes_no_artifact(self):
        message = build_message(
            finding="TEST-MALFORMED-1", result="PASS", omit_fields=["Guard Evidence Checked"]
        )
        result = self.run_hook(message=message)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Guard Evidence Checked", result.stderr)
        self.assertFalse(self.review_path("TEST-MALFORMED-1").exists())

    def test_malformed_result_value_never_becomes_pass(self):
        message = build_message(
            finding="TEST-MALFORMED-2", result="PASS", result_text="PASS (mostly, I think)"
        )
        result = self.run_hook(message=message)
        self.assertEqual(result.returncode, 2)
        self.assertIn("ungueltigen Wert", result.stderr)
        self.assertFalse(self.review_path("TEST-MALFORMED-2").exists())

    def test_no_fenced_block_writes_no_artifact(self):
        result = self.run_hook(message="I looked at everything and it seems fine, Result: PASS.")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.reviews_dir.exists())

    def test_unsafe_finding_token_writes_no_artifact(self):
        message = build_message(finding="../../etc/passwd", result="PASS")
        result = self.run_hook(message=message)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Dateiname", result.stderr)

    # -- provenance ---------------------------------------------------------

    def test_missing_agent_id_is_rejected(self):
        message = build_message(finding="TEST-NO-AGENT-ID-1", result="PASS")
        result = self.run_hook(agent_id=None, message=message)
        self.assertEqual(result.returncode, 2)
        self.assertIn("agent_id", result.stderr)
        self.assertFalse(self.review_path("TEST-NO-AGENT-ID-1").exists())

    def test_empty_agent_id_is_rejected(self):
        message = build_message(finding="TEST-EMPTY-AGENT-ID-1", result="PASS")
        result = self.run_hook(agent_id="   ", message=message)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.review_path("TEST-EMPTY-AGENT-ID-1").exists())

    # -- compatibility with the existing, unmodified closure gates ----------

    def test_hook_output_is_accepted_by_validate_review_and_closure_gate(self):
        finding_id = "TEST-E2E-1"
        message = build_message(finding=finding_id, result="PASS")
        hook_result = self.run_hook(message=message)
        self.assertEqual(hook_result.returncode, 0, hook_result.stderr)

        finding_path = self.findings_dir / f"{finding_id}.md"
        finding_path.write_text(
            f"""\
# {finding_id}

Status: READY_FOR_CLOSURE

## Analyse

Root Cause: Test root cause.
Affected Components: Test components.
Relevant Architecture: Test architecture.
Recommended Repair: Test repair.
Regression Test Plan: Test plan.
Central Guard Plan: Test guard plan.
Expected Blast Radius: Test blast radius.
Risk Assessment: Test risk assessment.
Verification Evidence: Test verification evidence.
CI Evidence: Test CI evidence (run 123).
Review Artifact: factory/reviews/{finding_id}.md
""",
            encoding="utf-8",
        )

        review_path = self.review_path(finding_id)
        review_check = self.run_validate_review(review_path)
        self.assertEqual(review_check.returncode, 0, review_check.stderr)
        self.assertIn("GÜLTIG", review_check.stdout)

        # validate-finding.py resolves a relative "Review Artifact" path
        # against its own REPO_ROOT (parents[2] of the copied script, i.e.
        # this temp project root), matching how it is invoked in real usage.
        finding_check = self.run_validate_finding(finding_path)
        self.assertEqual(finding_check.returncode, 0, finding_check.stderr)

    # -- static configuration -------------------------------------------

    def test_settings_json_registers_hook_and_deny_rules(self):
        """This checks that .claude/settings.json is wired up as intended --
        it is a config-presence check, not a test of Claude Code's actual
        runtime permission enforcement (which is out of reach for a script
        run outside the Claude Code harness itself)."""
        settings = json.loads(REAL_SETTINGS_JSON.read_text(encoding="utf-8"))

        deny_rules = settings.get("permissions", {}).get("deny", [])
        self.assertIn("Edit(/factory/reviews/**)", deny_rules)
        self.assertIn("Write(/factory/reviews/**)", deny_rules)

        subagent_stop_hooks = settings.get("hooks", {}).get("SubagentStop", [])
        matchers = [entry.get("matcher") for entry in subagent_stop_hooks]
        self.assertIn(EXPECTED_AGENT_TYPE, matchers)

        matching_entry = next(
            entry for entry in subagent_stop_hooks if entry.get("matcher") == EXPECTED_AGENT_TYPE
        )
        commands = [h.get("command", "") for h in matching_entry.get("hooks", [])]
        self.assertTrue(
            any("subagentstop-write-review.py" in command for command in commands)
        )

    def test_settings_json_enables_os_sandbox_denying_reviews_write(self):
        """Same caveat as the test above: this is a config-presence check for
        the sandbox.filesystem.denyWrite entry, not a test of the actual OS
        enforcement (see .claude/hooks/test_sandbox_protects_reviews.py for
        the closest thing to a live enforcement check)."""
        settings = json.loads(REAL_SETTINGS_JSON.read_text(encoding="utf-8"))

        sandbox = settings.get("sandbox", {})
        self.assertIs(sandbox.get("enabled"), True)
        self.assertIs(sandbox.get("allowUnsandboxedCommands"), False)
        self.assertIn("./factory/reviews", sandbox.get("filesystem", {}).get("denyWrite", []))


if __name__ == "__main__":
    unittest.main()
