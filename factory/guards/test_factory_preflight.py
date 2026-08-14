"""Tests for factory/scripts/factory-preflight.sh (factory onboarding).

Run with:
    python3 -m unittest factory.guards.test_factory_preflight

Every test builds a throwaway repository that contains a copy of the real
preflight script plus whatever the individual test wants to be present or
missing, and runs the preflight there in --local-only mode (no network, no
GitHub, no credentials, nothing installed). The real repository this file
lives in is never modified, and no test ever creates a PR, pushes, or
writes .claude/settings.local.json anywhere but in its own temp tree.

The onboarding contract these tests pin down:
  - a missing prerequisite is reported precisely, with the exact one-time
    human step, and never silently auto-fixed;
  - nothing is hardcoded to one machine, one owner, one repository or one
    default-branch name -- the suggested local permission snippet is built
    from the repository the preflight actually runs in;
  - a fully prepared repository reports FACTORY_PREFLIGHT: PASS and exits 0.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SCRIPT = REPO_ROOT / "factory" / "scripts" / "factory-preflight.sh"
REAL_SETTINGS_JSON = REPO_ROOT / ".claude" / "settings.json"

# Mirrors the REQUIRED_FILES list inside the preflight script.
REQUIRED_FILES = [
    "factory/guards/run-factory-checks.py",
    "factory/guards/validate-finding.py",
    "factory/guards/validate-review.py",
    "factory/guards/run-project-tests.py",
    "factory/scripts/gh-api.sh",
    "factory/scripts/gh-query.sh",
    "factory/scripts/create-finding-worktree.sh",
    ".claude/hooks/stop-validate-findings.py",
    ".claude/hooks/subagentstop-write-review.py",
    ".claude/agents/finding-closure-reviewer.md",
    ".claude/skills/verify-finding/SKILL.md",
    ".claude/rules/factory-workflow.md",
    ".claude/settings.json",
    ".github/workflows/factory-ci.yml",
]

GIT_ENV_OVERRIDES = {
    "GIT_AUTHOR_NAME": "Factory Test",
    "GIT_AUTHOR_EMAIL": "factory-test@example.invalid",
    "GIT_COMMITTER_NAME": "Factory Test",
    "GIT_COMMITTER_EMAIL": "factory-test@example.invalid",
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


class FactoryPreflightTests(unittest.TestCase):
    def setUp(self):
        # resolve(): the preflight compares physical paths, so the fixture
        # must not rely on a symlinked temp root (/var -> /private/var).
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-preflight-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.root = self.tmp_dir / "project"
        self.root.mkdir()

        self.script = self.root / "factory" / "scripts" / "factory-preflight.sh"
        self.script.parent.mkdir(parents=True)
        shutil.copy2(REAL_SCRIPT, self.script)

    # -- fixture builders -------------------------------------------------

    def make_git_repo(self, origin_url="https://github.com/example-owner/example-repo.git"):
        _git(self.root, "init", "--initial-branch=trunk")
        if origin_url is not None:
            _git(self.root, "remote", "add", "origin", origin_url)

    def make_required_files(self):
        for rel in REQUIRED_FILES:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("placeholder\n", encoding="utf-8")
        shutil.copy2(REAL_SETTINGS_JSON, self.root / ".claude" / "settings.json")

    def make_gitignore(self):
        (self.root / ".gitignore").write_text(".claude/settings.local.json\n", encoding="utf-8")

    def write_local_settings(self, allow):
        path = self.root / ".claude" / "settings.local.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"permissions": {"allow": allow}}, indent=2), encoding="utf-8"
        )

    def run_preflight(self, *args):
        return subprocess.run(
            ["bash", str(self.script), *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )

    def suggested_allow_list(self):
        """The allow list the preflight itself proposes for this repository."""
        result = self.run_preflight("--local-only")
        marker = '"allow": ['
        self.assertIn(marker, result.stdout)
        snippet = result.stdout[result.stdout.index("{", result.stdout.index(marker) - 40) :]
        return json.loads(snippet)["permissions"]["allow"]

    # -- individual prerequisites -----------------------------------------

    def test_missing_git_repository_is_reported_and_blocks(self):
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Kein Git-Repository", result.stdout)
        self.assertIn("git init", result.stdout)
        self.assertIn("FACTORY_PREFLIGHT: BLOCKED", result.stdout)

    def test_missing_origin_is_reported_with_the_exact_step(self):
        self.make_git_repo(origin_url=None)
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Kein 'origin'-Remote konfiguriert", result.stdout)
        self.assertIn("git remote add origin", result.stdout)

    def test_non_github_origin_is_reported(self):
        self.make_git_repo(origin_url="https://example.invalid/some/repo.git")
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("kein github.com-Remote", result.stdout)

    def test_missing_factory_files_are_named_individually(self):
        self.make_git_repo()
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Factory-Dateien fehlen", result.stdout)
        self.assertIn(".claude/agents/finding-closure-reviewer.md", result.stdout)
        self.assertIn(".github/workflows/factory-ci.yml", result.stdout)

    def test_shipped_settings_json_satisfies_the_protection_checks(self):
        """The settings.json shipped with this template must itself pass --
        otherwise the template would ship an onboarding it cannot survive."""
        self.make_git_repo()
        self.make_required_files()
        result = self.run_preflight("--local-only")
        self.assertIn("Geschuetzte Factory-/Review-/Hook-Dateien", result.stdout)

    def test_deny_on_routine_git_push_is_reported_as_approval_blocker(self):
        self.make_git_repo()
        self.make_required_files()
        settings_path = self.root / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        settings["permissions"]["deny"].append("Bash(git push *)")
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Bash(git push *)", result.stdout)
        self.assertIn("blockiert die normale", result.stdout)

    def test_missing_local_settings_yields_a_repo_specific_snippet(self):
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn(".claude/settings.local.json fehlt", result.stdout)
        # The read-only reviewer grant is built from THIS repository's path,
        # never from a hardcoded one.
        self.assertIn(f'"Read({self.root}/**)"', result.stdout)
        # And it stays narrow: no blanket bash/curl/python grants.
        allow = self.suggested_allow_list()
        for forbidden in ["Bash(*)", "Bash(curl *)", "Bash(python3 *)", "Bash(git *)"]:
            self.assertNotIn(forbidden, allow)

    def test_broad_local_grants_are_rejected(self):
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(["Bash(curl *)"])
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Zu breite lokale Freigaben", result.stdout)
        self.assertIn("Bash(curl *)", result.stdout)

    def test_missing_gitignore_entry_is_reported(self):
        self.make_git_repo()
        self.make_required_files()
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("nicht in .gitignore", result.stdout)

    def test_project_dir_write_grants_are_only_required_when_it_exists(self):
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        without_project = self.suggested_allow_list()
        self.assertNotIn("Edit(/app/**)", without_project)

        (self.root / "app").mkdir()
        with_project = self.suggested_allow_list()
        self.assertIn("Edit(/app/**)", with_project)
        self.assertIn("Write(/app/**)", with_project)

    # -- the fully prepared repository ------------------------------------

    def test_fully_prepared_repository_passes_local_preflight(self):
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list())

        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FACTORY_PREFLIGHT: PASS", result.stdout)
        self.assertIn("ohne Routine-Approvals", result.stdout)
        self.assertNotIn("[FEHLT]", result.stdout)

    def test_local_only_mode_skips_network_checks(self):
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list())
        result = self.run_preflight("--local-only")
        self.assertIn("Netzwerk-/GitHub-Pruefungen uebersprungen", result.stdout)

    def test_usage_error_on_unknown_argument(self):
        result = self.run_preflight("--wat")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)

    # -- transferability (static checks on the script itself) -------------

    def test_script_hardcodes_no_machine_owner_or_default_branch(self):
        source = REAL_SCRIPT.read_text(encoding="utf-8")
        for forbidden in ["/Users/", "origin/main", "refs/heads/main"]:
            self.assertNotIn(
                forbidden,
                source,
                f"factory-preflight.sh must not hardcode {forbidden!r}",
            )

    def test_pr_permission_probe_can_never_create_a_pull_request(self):
        """Contents:write and Pull requests:write are different token
        permissions -- a push can succeed while POST /pulls is refused. The
        preflight therefore probes the real endpoint, but with head == base,
        which GitHub can never turn into a pull request."""
        source = REAL_SCRIPT.read_text(encoding="utf-8")
        probe_lines = [
            line
            for line in source.splitlines()
            if "POST /pulls" in line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(len(probe_lines), 1, probe_lines)
        probe = probe_lines[0]
        self.assertIn('\\"head\\":\\"$DEFAULT_BRANCH\\"', probe)
        self.assertIn('\\"base\\":\\"$DEFAULT_BRANCH\\"', probe)
        # And the refusal is classified as a missing prerequisite, not as a
        # generic error the operator has to interpret.
        self.assertIn("Pull requests: read/write", source)

    def test_script_never_prints_the_credential(self):
        """The credential check must prove presence without ever emitting the
        value: the only use of the credential-helper output is a grep -q."""
        source = REAL_SCRIPT.read_text(encoding="utf-8")
        credential_lines = [
            line for line in source.splitlines() if "git credential fill" in line
        ]
        self.assertTrue(credential_lines)
        for line in credential_lines:
            self.assertIn("grep -q", line)
            self.assertNotIn("echo", line)


if __name__ == "__main__":
    unittest.main()
