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
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SCRIPT = REPO_ROOT / "factory" / "scripts" / "factory-preflight.sh"
REAL_SETTINGS_JSON = REPO_ROOT / ".claude" / "settings.json"

# Mirrors the REQUIRED_FILES list inside the preflight script.
REQUIRED_FILES = [
    "factory/guards/run-factory-checks.py",
    "factory/guards/run-factory-tests.py",
    "factory/guards/validate-finding.py",
    "factory/guards/validate-review.py",
    "factory/guards/validate-build-order.py",
    "factory/guards/validate-control-plane.py",
    "factory/guards/scope_hash.py",
    "factory/guards/gh_evidence.py",
    "factory/guards/finding_state.py",
    "factory/guards/run-project-tests.py",
    "factory/control-plane.sha256",
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

# The fixture ships the REAL files, not stubs. Audit finding F-14: the
# preflight no longer asks whether a file with the right name exists, it runs
# the control-plane guard, the canonical runner and the discovered test suite.
# A fixture full of "placeholder" would now -- correctly -- fail, so building
# one would mean testing the preflight against a repository it is supposed to
# reject.
FILES_COPIED_VERBATIM = [rel for rel in REQUIRED_FILES if rel != "factory/control-plane.sha256"]

# One tiny, genuinely passing test so the discovery runner has something to
# find. Discovering nothing is a hard failure (F-19), which is the correct
# behaviour and not what these preflight tests are about.
SMOKE_TEST = """\
import unittest


class Smoke(unittest.TestCase):
    def test_the_fixture_factory_runs(self):
        self.assertTrue(True)
"""

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

    def make_required_files(self, stamp=True):
        """Build a fixture that is a real, working factory -- not a name-shaped
        shell. See FILES_COPIED_VERBATIM for why."""
        for rel in FILES_COPIED_VERBATIM:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, path)
        for extra in ("factory/findings", "factory/reviews", "factory/build-orders"):
            (self.root / extra).mkdir(parents=True, exist_ok=True)
        (self.root / "factory" / "guards" / "test_smoke.py").write_text(
            SMOKE_TEST, encoding="utf-8"
        )
        if stamp:
            self.stamp_control_plane()

    def make_placeholder_files(self):
        """The repository audit finding F-14 describes: every required file
        exists, and every one of them is a stub."""
        for rel in REQUIRED_FILES:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("placeholder\n", encoding="utf-8")

    def stamp_control_plane(self):
        """Track the fixture's files and stamp the control-plane manifest.

        The control-plane guard reads `git ls-files`, so the fixture has to
        be a real repository with its files added, not just a directory.
        """
        _git(self.root, "add", "-A")
        result = subprocess.run(
            [
                sys.executable,
                str(self.root / "factory" / "guards" / "validate-control-plane.py"),
                "--repo-root",
                str(self.root),
                "--update",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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
        self.assertIn("Unbekannte Shell-Freigaben", result.stdout)
        self.assertIn("Bash(curl *)", result.stdout)

    def test_an_unlisted_shell_grant_is_rejected_even_if_it_looks_harmless(self):
        """Audit finding F-14/E: the check used to be a blacklist, so a grant
        it had never heard of passed silently. Whether `Bash(rm -rf /tmp/x)`
        looks harmless is not the point -- an unattended agent's shell
        permissions are not decided by what a fixed list happens to mention."""
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list() + ["Bash(rsync *)"])
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unbekannte Shell-Freigaben", result.stdout)
        self.assertIn("Bash(rsync *)", result.stdout)

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

    def test_fully_prepared_repository_reports_partial_in_local_only_mode(self):
        """Audit finding F-11, inverted from what this test used to assert.

        It used to demand `FACTORY_PREFLIGHT: PASS` and "laeuft ohne
        Routine-Approvals" from a run that had skipped every GitHub gate --
        a verdict about a layer the run never entered. A fully prepared local
        repository is now PARTIAL with its own exit code, and PASS is
        unreachable without the remote checks.
        """
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list())
        self.stamp_control_plane()

        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("FACTORY_PREFLIGHT: PARTIAL", result.stdout)
        self.assertNotIn("FACTORY_PREFLIGHT: PASS", result.stdout)
        self.assertNotIn("[FEHLT]", result.stdout)
        # And it says plainly what was NOT checked.
        self.assertIn("NICHT geprueft", result.stdout)
        self.assertIn("Branch-Schutz", result.stdout)

    def test_local_only_can_never_reach_pass(self):
        """Static guarantee, independent of any fixture: the only PASS in the
        script is unreachable while MODE is local."""
        source = REAL_SCRIPT.read_text(encoding="utf-8")
        pass_index = source.index('echo "FACTORY_PREFLIGHT: PASS"')
        partial_index = source.index('echo "FACTORY_PREFLIGHT: PARTIAL"')
        self.assertLess(
            partial_index,
            pass_index,
            "the PARTIAL branch must return before PASS can be printed",
        )
        self.assertEqual(source.count('echo "FACTORY_PREFLIGHT: PASS"'), 1)

    def test_a_repository_of_placeholders_never_passes(self):
        """Audit finding F-14: every required file existed, every one was a
        stub, and the preflight reported the factory as fully equipped."""
        self.make_git_repo()
        self.make_placeholder_files()
        self.make_gitignore()
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Platzhalter", result.stdout)
        self.assertNotIn("FACTORY_PREFLIGHT: PASS", result.stdout)
        self.assertNotIn("FACTORY_PREFLIGHT: PARTIAL", result.stdout)

    def test_the_factory_is_actually_executed_not_only_inventoried(self):
        """A guard that cannot run is not a guard. The preflight runs the
        canonical runner and the discovered test suite."""
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list())
        self.stamp_control_plane()
        result = self.run_preflight("--local-only")
        self.assertIn("Kanonischer Runner laeuft und besteht", result.stdout)
        self.assertIn("Factory-Testsuite laeuft und besteht", result.stdout)

    def test_a_broken_factory_test_blocks_the_preflight(self):
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list())
        (self.root / "factory" / "guards" / "test_smoke.py").write_text(
            "import unittest\n\n\n"
            "class Broken(unittest.TestCase):\n"
            "    def test_broken(self):\n"
            "        self.assertTrue(False)\n",
            encoding="utf-8",
        )
        self.stamp_control_plane()
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Factory-Testsuite schlaegt fehl", result.stdout)

    def test_sandbox_verification_is_reported_as_not_performed_outside_a_sandbox(self):
        """F-19: a skipped sandbox test must never be sold as evidence that
        the sandbox protects anything."""
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list())
        self.stamp_control_plane()
        result = self.run_preflight("--local-only")
        self.assertIn("Sandbox-Verifikation NICHT durchgefuehrt", result.stdout)
        self.assertIn("belegt den Sandbox-Schutz damit ausdruecklich NICHT", result.stdout)

    def test_local_only_mode_skips_network_checks(self):
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list())
        self.stamp_control_plane()
        result = self.run_preflight("--local-only")
        self.assertIn("Netzwerk-/GitHub-Pruefungen uebersprungen", result.stdout)

    # -- control plane (audit finding F-05) --------------------------------

    def test_control_plane_drift_is_reported(self):
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list())
        self.stamp_control_plane()

        # A normal finding run must never be able to do this unnoticed.
        (self.root / "factory" / "guards" / "validate-finding.py").write_text(
            "# quietly weakened\n", encoding="utf-8"
        )
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Control-Plane weicht vom Manifest ab", result.stdout)
        self.assertIn("FACTORY_CHANGE", result.stdout)

    def test_control_plane_guard_is_actually_executed_not_just_present(self):
        """A file that merely exists under that name is not a guard."""
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.write_local_settings(self.suggested_allow_list())
        # No manifest at all.
        (self.root / "factory" / "control-plane.sha256").unlink(missing_ok=True)
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Control-Plane", result.stdout)

    def test_control_plane_write_grants_are_rejected_as_too_broad(self):
        """Granting write access to the guards was audit finding F-05."""
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        self.stamp_control_plane()
        self.write_local_settings(
            self.suggested_allow_list() + ["Edit(/factory/guards/**)"]
        )
        result = self.run_preflight("--local-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Schreibrechte auf die Kontrollebene", result.stdout)
        self.assertIn("Edit(/factory/guards/**)", result.stdout)

    def test_suggested_allow_list_does_not_grant_control_plane_writes(self):
        self.make_git_repo()
        self.make_required_files()
        self.make_gitignore()
        allow = self.suggested_allow_list()
        for forbidden in (
            "Edit(/factory/guards/**)",
            "Write(/factory/guards/**)",
            "Edit(/factory/scripts/**)",
            "Write(/factory/scripts/**)",
        ):
            self.assertNotIn(forbidden, allow)

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
        factory therefore probes the real endpoint, but with head == base,
        which GitHub can never turn into a pull request.

        The probe moved out of this script and into gh-query.sh/gh_evidence.py
        (audit finding F-12) so that its classification is regression-tested
        without a network. What stays pinned here is the invariant that it
        cannot create anything, and that a refusal is reported as a concrete
        missing prerequisite rather than a generic error."""
        query_source = (REPO_ROOT / "factory" / "scripts" / "gh-query.sh").read_text(
            encoding="utf-8"
        )
        probe_block = query_source[query_source.index("pr-permission-probe)") :]
        probe_block = probe_block[: probe_block.index(";;")]
        self.assertIn('head "$ARG" base "$ARG"', probe_block)

        source = REAL_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("pr-permission-probe", source)
        self.assertIn("Pull requests: read/write", source)
        # The preflight must not post to /pulls itself any more. Comments may
        # still explain why the probe exists; executable lines may not do it.
        posting_lines = [
            line
            for line in source.splitlines()
            if "POST /pulls" in line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(posting_lines, [])

    def test_script_never_prints_the_credential(self):
        """The credential check must prove presence without ever emitting the
        value: the only use of the credential-helper output is a grep -q."""
        source = REAL_SCRIPT.read_text(encoding="utf-8")
        credential_lines = [
            line
            for line in source.splitlines()
            if "credential fill" in line and not line.lstrip().startswith("#")
        ]
        self.assertTrue(credential_lines)
        for line in credential_lines:
            self.assertIn("grep -q", line)
            self.assertNotIn("echo", line)
            # F-20: the same invocation must be non-interactive, or a missing
            # credential hangs the onboarding run instead of reporting it.
            self.assertIn("GIT_TERMINAL_PROMPT=0", line)
            self.assertIn("GIT_ASKPASS=", line)


if __name__ == "__main__":
    unittest.main()
