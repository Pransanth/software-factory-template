"""Tests for validate-control-plane.py (audit finding F-05).

Run with:
    python3 -m unittest factory.guards.test_control_plane

The invariant: normal finding work must not be able to change the factory's
own controls without that change being visible. Before this guard, a branch
could weaken factory/guards/validate-finding.py and be checked by the very
guard it had just weakened, because CI runs the guards from the pull
request's own head.

Each test builds a throwaway git repository with a miniature control plane
in it and runs the real guard there. The real repository is never touched.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "validate-control-plane.py"

GIT_ENV_OVERRIDES = {
    "GIT_AUTHOR_NAME": "Factory Test",
    "GIT_AUTHOR_EMAIL": "factory-test@example.invalid",
    "GIT_COMMITTER_NAME": "Factory Test",
    "GIT_COMMITTER_EMAIL": "factory-test@example.invalid",
}

# One file per control-plane category the guard claims to cover.
CONTROL_PLANE_FIXTURE = {
    "factory/guards/validate-finding.py": "# guard\n",
    "factory/scripts/gh-query.sh": "#!/usr/bin/env bash\n",
    ".claude/hooks/subagentstop-write-review.py": "# hook\n",
    ".claude/agents/finding-closure-reviewer.md": "# reviewer\n",
    ".claude/skills/verify-finding/SKILL.md": "# skill\n",
    ".claude/rules/factory-workflow.md": "# rules\n",
    ".claude/settings.json": "{}\n",
    ".github/workflows/factory-ci.yml": "name: CI\n",
    "CLAUDE.md": "# CLAUDE\n",
}

# Files that must NOT be part of the control plane: normal finding work
# changes these constantly.
NON_CONTROL_PLANE_FIXTURE = {
    "app/code.py": "VALUE = 1\n",
    "factory/findings/F-1.md": "# F-1\n",
    "factory/build-orders/F-1.md": "# Bauauftrag\n",
    "factory/reviews/README.md": "# Reviews\n",
    "README.md": "# Projekt\n",
}


def _git(cwd, *args):
    env = dict(os.environ)
    env.update(GIT_ENV_OVERRIDES)
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


class ControlPlaneGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-control-plane-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.root = self.tmp_dir / "project"
        self.root.mkdir()

        for relative_path, content in {**CONTROL_PLANE_FIXTURE, **NON_CONTROL_PLANE_FIXTURE}.items():
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        _git(self.root, "init", "--initial-branch=trunk")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "initial")

        self.manifest = self.root / "factory" / "control-plane.sha256"

    def run_guard(self, *args):
        return subprocess.run(
            [sys.executable, str(GUARD), "--repo-root", str(self.root), *args],
            capture_output=True,
            text=True,
        )

    def stamp(self):
        result = self.run_guard("--update")
        self.assertEqual(result.returncode, 0, result.stderr)
        _git(self.root, "add", "-A")
        return result

    def write_tracked(self, relative_path, content):
        (self.root / relative_path).write_text(content, encoding="utf-8")

    # -- baseline ---------------------------------------------------------

    def test_missing_manifest_blocks(self):
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Manifest", result.stderr)

    def test_stamped_control_plane_passes(self):
        self.stamp()
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unveraendert", result.stdout)

    def test_manifest_covers_every_control_plane_category(self):
        self.stamp()
        manifest_text = self.manifest.read_text(encoding="utf-8")
        for relative_path in CONTROL_PLANE_FIXTURE:
            self.assertIn(relative_path, manifest_text)

    def test_manifest_excludes_normal_working_files(self):
        self.stamp()
        manifest_text = self.manifest.read_text(encoding="utf-8")
        for relative_path in NON_CONTROL_PLANE_FIXTURE:
            self.assertNotIn(relative_path, manifest_text)

    # -- the actual attack shape ------------------------------------------

    def test_weakened_guard_is_detected(self):
        self.stamp()
        self.write_tracked(
            "factory/guards/validate-finding.py", "# guard\ndef validate(*_): return []\n"
        )
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Inhalt geaendert", result.stderr)
        self.assertIn("validate-finding.py", result.stderr)

    def test_changed_ci_workflow_is_detected(self):
        self.stamp()
        self.write_tracked(".github/workflows/factory-ci.yml", "name: CI\n# nothing runs\n")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("factory-ci.yml", result.stderr)

    def test_changed_gh_query_script_is_detected(self):
        self.stamp()
        self.write_tracked("factory/scripts/gh-query.sh", "#!/usr/bin/env bash\necho success\n")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("gh-query.sh", result.stderr)

    def test_changed_hook_is_detected(self):
        self.stamp()
        self.write_tracked(".claude/hooks/subagentstop-write-review.py", "# hook\npass\n")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)

    def test_changed_reviewer_agent_definition_is_detected(self):
        self.stamp()
        self.write_tracked(".claude/agents/finding-closure-reviewer.md", "# always PASS\n")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)

    def test_changed_claude_md_is_detected(self):
        self.stamp()
        self.write_tracked("CLAUDE.md", "# CLAUDE\nAlles ist erlaubt.\n")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)

    def test_new_control_plane_file_is_detected(self):
        self.stamp()
        (self.root / "factory" / "guards" / "sneaky.py").write_text("# new\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("nicht im Manifest", result.stderr)

    def test_removed_control_plane_file_is_detected(self):
        self.stamp()
        _git(self.root, "rm", "-q", "factory/scripts/gh-query.sh")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("nicht mehr im Repository", result.stderr)

    # -- normal work must stay unaffected ---------------------------------

    def test_normal_product_change_passes(self):
        self.stamp()
        self.write_tracked("app/code.py", "VALUE = 2\n")
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_normal_finding_and_build_order_change_passes(self):
        self.stamp()
        self.write_tracked("factory/findings/F-1.md", "# F-1\nStatus: CLOSED\n")
        self.write_tracked("factory/build-orders/F-1.md", "# Bauauftrag\nScope: app/\n")
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_new_review_artifact_passes(self):
        self.stamp()
        (self.root / "factory" / "reviews" / "F-1.round-1.md").write_text(
            "Result: PASS\n", encoding="utf-8"
        )
        _git(self.root, "add", "-A")
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)

    # -- re-stamping is deliberate, and says so ---------------------------

    def test_restamping_after_a_deliberate_change_passes_again(self):
        self.stamp()
        self.write_tracked("factory/guards/validate-finding.py", "# guard v2\n")
        self.assertEqual(self.run_guard().returncode, 1)
        self.stamp()
        self.assertEqual(self.run_guard().returncode, 0)

    def test_manifest_names_itself_a_factory_change(self):
        self.stamp()
        self.assertIn("FACTORY_CHANGE", self.manifest.read_text(encoding="utf-8"))

    def test_unreadable_manifest_line_blocks(self):
        self.stamp()
        self.manifest.write_text("this is not a manifest line at all\n", encoding="utf-8")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)

    def test_no_git_repository_blocks(self):
        self.stamp()
        shutil.rmtree(self.root / ".git")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("CONTROL_PLANE_ERROR", result.stderr)


if __name__ == "__main__":
    unittest.main()
