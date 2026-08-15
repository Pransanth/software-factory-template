"""Regression tests for the operational-robustness package.

Run with:
    python3 -m unittest factory.guards.test_ops_robustness

Covers audit findings F-12, F-13, F-16, F-19 and F-20. Each group states the
false answer the pre-repair code gave, because that is what makes these tests
regression tests rather than descriptions of the current implementation.

  F-12  The pull-request permission probe classified by EXCLUSION: anything
        that was not recognisably a 403 became PERMITTED. A 401 from a wrong
        token, a 404 from a repository the token cannot see, an empty body and
        a rate limit all reported "Token darf Pull Requests erstellen".
  F-13  Branch protection was COUNTED, not read. A ruleset containing only a
        force-push rule counted as 1 and satisfied "Branch-Schutz aktiv" --
        while allowing a direct push to the default branch. Classic branch
        protection was not consulted at all, and required approvals (which make
        an unattended merge impossible) were never noticed.
  F-16  Nothing survived a crashed session. Whether a branch was pushed, a
        pull request existed, CI was green for THIS head or a review still
        covered the code all had to be guessed.
  F-19  The CI test list was hand-maintained, so a new test file simply did
        not run; and a sandbox test that SKIPPED (because no sandbox exists on
        a CI runner) was folded into "all tests passed".
  F-20  A missing credential made `git credential fill` wait on /dev/tty, so
        an unattended run hung instead of failing.

Nothing here touches the network, and nothing writes outside its own temp
tree.
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
GUARDS_DIR = REPO_ROOT / "factory" / "guards"
GH_EVIDENCE = GUARDS_DIR / "gh_evidence.py"
FINDING_STATE = GUARDS_DIR / "finding_state.py"
TEST_RUNNER = GUARDS_DIR / "run-factory-tests.py"
GH_API = REPO_ROOT / "factory" / "scripts" / "gh-api.sh"
WORKTREE_SCRIPT = REPO_ROOT / "factory" / "scripts" / "create-finding-worktree.sh"

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


def run_evidence(payload, *args):
    """Feed a recorded payload to gh_evidence.py, exactly as gh-query.sh does."""
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(GH_EVIDENCE), *args],
        input=body,
        capture_output=True,
        text=True,
    )


# --------------------------------------------------------------------------
# F-12: the pull-request permission probe
# --------------------------------------------------------------------------


class PrPermissionProbeTests(unittest.TestCase):
    """Permission is recognised POSITIVELY or not at all."""

    def assertBlocked(self, result):
        self.assertNotEqual(
            result.returncode,
            0,
            "probe reported permission where none was proven:\n" + result.stdout,
        )
        self.assertNotIn("probe: permitted", result.stdout)

    def test_validation_error_proves_the_permission(self):
        payload = {
            "message": "Validation Failed",
            "errors": [{"resource": "PullRequest", "message": "No commits between x and x"}],
        }
        result = run_evidence(payload, "pr-permission-probe", "3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("probe: permitted", result.stdout)

    def test_401_bad_credentials_is_blocked_not_permitted(self):
        result = run_evidence({"message": "Bad credentials"}, "pr-permission-probe", "3")
        self.assertBlocked(result)
        self.assertIn("probe: blocked", result.stdout)

    def test_404_not_found_is_blocked_not_permitted(self):
        result = run_evidence({"message": "Not Found"}, "pr-permission-probe", "3")
        self.assertBlocked(result)

    def test_403_forbidden_is_blocked(self):
        payload = {"message": "Resource not accessible by personal access token"}
        result = run_evidence(payload, "pr-permission-probe", "3")
        self.assertBlocked(result)

    def test_rate_limit_is_blocked(self):
        payload = {"message": "API rate limit exceeded for user ID 1."}
        result = run_evidence(payload, "pr-permission-probe", "3")
        self.assertBlocked(result)

    def test_empty_body_is_blocked(self):
        result = run_evidence("", "pr-permission-probe", "3")
        self.assertBlocked(result)

    def test_non_json_body_is_blocked(self):
        result = run_evidence("<html>502 Bad Gateway</html>", "pr-permission-probe", "3")
        self.assertBlocked(result)

    def test_network_failure_is_reported_as_api_error_not_permitted(self):
        result = run_evidence({"message": "whatever"}, "pr-permission-probe", "4")
        self.assertBlocked(result)
        self.assertIn("probe: api_error", result.stdout)

    def test_an_unknown_message_is_blocked(self):
        """The point of the repair: an answer this code has never seen is
        blocked, not waved through."""
        payload = {"message": "Something entirely new happened"}
        result = run_evidence(payload, "pr-permission-probe", "3")
        self.assertBlocked(result)

    def test_a_created_pull_request_is_a_blocker(self):
        """head == base can never create one, so this means something is
        badly wrong -- and it must not read as success."""
        result = run_evidence({"number": 7}, "pr-permission-probe", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("probe: created", result.stdout)


# --------------------------------------------------------------------------
# F-13: branch protection, read instead of counted
# --------------------------------------------------------------------------


class RulesetGuaranteeTests(unittest.TestCase):
    FORCE_PUSH_ONLY = [{"type": "non_fast_forward"}]

    FULL = [
        {"type": "pull_request", "parameters": {"required_approving_review_count": 0}},
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": "factory-checks"}]},
        },
    ]

    WITH_APPROVALS = [
        {"type": "pull_request", "parameters": {"required_approving_review_count": 2}},
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": "factory-checks"}]},
        },
    ]

    def guarantees(self, payload):
        result = run_evidence(payload, "ruleset-guarantees", "factory-checks")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return dict(
            line.split(": ", 1) for line in result.stdout.splitlines() if ": " in line
        )

    def test_force_push_only_ruleset_guarantees_nothing_about_merging(self):
        """It counts as one rule. Counting was the bug."""
        facts = self.guarantees(self.FORCE_PUSH_ONLY)
        self.assertEqual(facts["rule_count"], "1")
        self.assertEqual(facts["pull_request_required"], "false")
        self.assertEqual(facts["required_check_present"], "false")

    def test_full_ruleset_is_recognised(self):
        facts = self.guarantees(self.FULL)
        self.assertEqual(facts["pull_request_required"], "true")
        self.assertEqual(facts["required_check_present"], "true")
        self.assertEqual(facts["required_approving_review_count"], "0")

    def test_a_differently_named_required_check_is_not_ours(self):
        payload = [
            {"type": "pull_request", "parameters": {}},
            {
                "type": "required_status_checks",
                "parameters": {"required_status_checks": [{"context": "build"}]},
            },
        ]
        facts = self.guarantees(payload)
        self.assertEqual(facts["required_check_present"], "false")

    def test_required_approvals_are_reported(self):
        facts = self.guarantees(self.WITH_APPROVALS)
        self.assertEqual(facts["required_approving_review_count"], "2")

    def test_an_api_error_is_not_an_empty_ruleset(self):
        result = run_evidence({"message": "Not Found"}, "ruleset-guarantees", "factory-checks")
        self.assertEqual(result.returncode, 4, result.stdout)
        self.assertIn("api_error", result.stdout)


class ClassicProtectionTests(unittest.TestCase):
    def facts(self, payload, api_rc):
        result = run_evidence(payload, "classic-protection", str(api_rc), "factory-checks")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return dict(
            line.split(": ", 1) for line in result.stdout.splitlines() if ": " in line
        )

    def test_branch_not_protected_is_a_legitimate_answer(self):
        """A repository that uses rulesets has no classic protection. That is
        not an error and must not be reported as one."""
        facts = self.facts({"message": "Branch not protected"}, 3)
        self.assertEqual(facts["classic_protection"], "absent")

    def test_classic_protection_is_read_semantically(self):
        payload = {
            "required_pull_request_reviews": {"required_approving_review_count": 1},
            "required_status_checks": {"contexts": ["factory-checks"], "strict": True},
        }
        facts = self.facts(payload, 0)
        self.assertEqual(facts["classic_protection"], "present")
        self.assertEqual(facts["pull_request_required"], "true")
        self.assertEqual(facts["required_check_present"], "true")
        self.assertEqual(facts["required_approving_review_count"], "1")

    def test_classic_protection_without_pull_request_requirement(self):
        payload = {"required_status_checks": {"contexts": ["factory-checks"]}}
        facts = self.facts(payload, 0)
        self.assertEqual(facts["pull_request_required"], "false")

    def test_a_real_api_error_is_still_an_api_error(self):
        result = run_evidence({"message": "Bad credentials"}, "classic-protection", "3", "factory-checks")
        self.assertEqual(result.returncode, 4, result.stdout)


# --------------------------------------------------------------------------
# F-16: resume
# --------------------------------------------------------------------------


class PrForBranchTests(unittest.TestCase):
    def test_no_pull_request_is_its_own_verdict(self):
        result = run_evidence([], "pr-for-branch", "fix/F-1")
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("pr_for_branch: none", result.stdout)

    def test_an_open_pull_request_is_found(self):
        payload = [
            {
                "number": 4,
                "state": "open",
                "merged_at": None,
                "head": {"ref": "fix/F-1", "sha": "a" * 40},
                "base": {"ref": "main"},
            }
        ]
        result = run_evidence(payload, "pr-for-branch", "fix/F-1")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("current_pr: 4", result.stdout)
        self.assertIn("current_pr_merged: false", result.stdout)

    def test_an_already_merged_pull_request_is_recognised_as_merged(self):
        payload = [
            {
                "number": 4,
                "state": "closed",
                "merged_at": "2026-08-15T10:00:00Z",
                "head": {"ref": "fix/F-1", "sha": "b" * 40},
                "base": {"ref": "main"},
            }
        ]
        result = run_evidence(payload, "pr-for-branch", "fix/F-1")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("current_pr_merged: true", result.stdout)

    def test_an_open_one_wins_over_an_older_closed_one(self):
        payload = [
            {
                "number": 4,
                "state": "closed",
                "merged_at": None,
                "head": {"ref": "fix/F-1", "sha": "c" * 40},
                "base": {"ref": "main"},
            },
            {
                "number": 9,
                "state": "open",
                "merged_at": None,
                "head": {"ref": "fix/F-1", "sha": "d" * 40},
                "base": {"ref": "main"},
            },
        ]
        result = run_evidence(payload, "pr-for-branch", "fix/F-1")
        self.assertIn("current_pr: 9", result.stdout)

    def test_another_branchs_pull_request_is_not_ours(self):
        payload = [
            {
                "number": 4,
                "state": "open",
                "merged_at": None,
                "head": {"ref": "fix/OTHER", "sha": "e" * 40},
                "base": {"ref": "main"},
            }
        ]
        result = run_evidence(payload, "pr-for-branch", "fix/F-1")
        self.assertEqual(result.returncode, 3, result.stdout)

    def test_an_api_error_is_not_no_pull_request(self):
        result = run_evidence({"message": "Bad credentials"}, "pr-for-branch", "fix/F-1")
        self.assertEqual(result.returncode, 4, result.stdout)


class FindingStateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-state-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.root = self.tmp_dir / "project"
        (self.root / "factory" / "guards").mkdir(parents=True)
        (self.root / "factory" / "reviews").mkdir(parents=True)
        (self.root / "app").mkdir(parents=True)
        shutil.copy2(GUARDS_DIR / "scope_hash.py", self.root / "factory" / "guards")
        (self.root / "app" / "code.py").write_text("VALUE = 1\n", encoding="utf-8")

        _git(self.root, "init", "--initial-branch=trunk")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "initial")

    def state(self, *args):
        return subprocess.run(
            [sys.executable, str(FINDING_STATE), *args, "--repo-root", str(self.root)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )

    def facts(self, result):
        return dict(
            line.split(": ", 1) for line in result.stdout.splitlines() if ": " in line
        )

    def test_no_state_at_all_is_reported_not_guessed(self):
        result = self.state("assess", "F-1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("recorded_state: none", result.stdout)

    def test_recording_is_idempotent(self):
        first = self.state("record", "F-1", "branch=fix/F-1", "pushed_sha=" + "a" * 40)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.state("record", "F-1", "branch=fix/F-1")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.facts(second)["pushed_sha"], "a" * 40)

    def test_an_unknown_key_is_rejected(self):
        result = self.state("record", "F-1", "wat=1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unbekannter Zustandsschluessel", result.stderr)

    def test_a_pushed_sha_matching_the_branch_head_is_current(self):
        _git(self.root, "switch", "-c", "fix/F-1")
        head = _git(self.root, "rev-parse", "HEAD")
        self.state("record", "F-1", "branch=fix/F-1", f"pushed_sha={head}")
        facts = self.facts(self.state("assess", "F-1"))
        self.assertEqual(facts["push_state"], "current")

    def test_a_stale_pushed_sha_invalidates_the_ci_evidence(self):
        """The rule that matters: evidence from before the branch moved is
        not evidence for what is on the branch now."""
        _git(self.root, "switch", "-c", "fix/F-1")
        old_head = _git(self.root, "rev-parse", "HEAD")
        self.state(
            "record",
            "F-1",
            "branch=fix/F-1",
            f"pushed_sha={old_head}",
            f"ci_head_sha={old_head}",
            "ci_run=123456",
        )

        (self.root / "app" / "code.py").write_text("VALUE = 2\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "more work after CI was green")

        facts = self.facts(self.state("assess", "F-1"))
        self.assertEqual(facts["push_state"], "stale")
        self.assertEqual(facts["ci_state"], "stale")
        self.assertIn("resume_next", facts)

    def test_a_review_is_stale_once_the_scope_hash_moved(self):
        _git(self.root, "switch", "-c", "fix/F-1")
        scope = subprocess.run(
            [sys.executable, str(self.root / "factory" / "guards" / "scope_hash.py")],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        current = next(
            line.split(": ", 1)[1]
            for line in scope.stdout.splitlines()
            if line.startswith("scope_hash:")
        )
        (self.root / "factory" / "reviews" / "F-1.round-1.md").write_text(
            f"Finding: F-1\nResult: PASS\nReviewed Scope Hash: {current}\n", encoding="utf-8"
        )
        facts = self.facts(self.state("assess", "F-1"))
        self.assertEqual(facts["review_state"], "current")
        self.assertEqual(facts["latest_review_result"], "PASS")

        (self.root / "app" / "code.py").write_text("VALUE = 3\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        facts = self.facts(self.state("assess", "F-1"))
        self.assertEqual(facts["review_state"], "stale")

    def test_a_worktree_on_a_foreign_branch_is_a_blocker(self):
        _git(self.root, "switch", "-c", "fix/F-1")
        _git(self.root, "switch", "trunk")
        worktree = self.root / "wt"
        _git(self.root, "worktree", "add", "--no-track", "-b", "fix/OTHER", str(worktree), "trunk")

        self.state("record", "F-1", "branch=fix/F-1", f"worktree={worktree}")
        result = self.state("assess", "F-1")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("worktree_state: conflict", result.stdout)
        self.assertIn("AUTONOMY_BLOCKER", result.stderr)
        self.assertTrue(worktree.is_dir(), "the worktree must never be deleted")

    def test_a_matching_worktree_is_reusable(self):
        _git(self.root, "switch", "trunk")
        worktree = self.root / "wt"
        _git(self.root, "worktree", "add", "--no-track", "-b", "fix/F-1", str(worktree), "trunk")
        self.state("record", "F-1", "branch=fix/F-1", f"worktree={worktree}")
        result = self.state("assess", "F-1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("worktree_state: reusable", result.stdout)


class WorktreeResumeTests(unittest.TestCase):
    """create-finding-worktree.sh must be idempotent and never destructive."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-worktree-resume-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.origin = self.tmp_dir / "origin.git"
        self.root = self.tmp_dir / "project"

        seed = self.tmp_dir / "seed"
        seed.mkdir()
        (seed / "file.txt").write_text("one\n", encoding="utf-8")
        _git(seed, "init", "--initial-branch=trunk")
        _git(seed, "add", "-A")
        _git(seed, "commit", "-m", "initial")
        _git(self.tmp_dir, "clone", "--bare", str(seed), str(self.origin))
        _git(self.tmp_dir, "clone", str(self.origin), str(self.root))

        self.script = self.root / "factory" / "scripts" / "create-finding-worktree.sh"
        self.script.parent.mkdir(parents=True)
        shutil.copy2(WORKTREE_SCRIPT, self.script)
        self.base_sha = _git(self.root, "rev-parse", "origin/trunk")

    def create(self, path, branch, expected=None):
        return subprocess.run(
            [
                "bash",
                str(self.script),
                "create",
                expected or self.base_sha,
                str(path),
                branch,
            ],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            env={**os.environ, **GIT_ENV_OVERRIDES},
        )

    def test_creating_twice_reports_the_existing_worktree_instead_of_failing(self):
        path = self.root / "wt-1"
        first = self.create(path, "fix/F-1")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("WORKTREE_READY", first.stdout)

        second = self.create(path, "fix/F-1")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("WORKTREE_EXISTS", second.stdout)
        self.assertTrue(path.is_dir())

    def test_an_existing_worktree_whose_head_moved_is_reported_not_reset(self):
        path = self.root / "wt-2"
        self.assertEqual(self.create(path, "fix/F-2").returncode, 0)
        (path / "file.txt").write_text("two\n", encoding="utf-8")
        _git(path, "add", "-A")
        _git(path, "commit", "-m", "work in progress")
        moved_head = _git(path, "rev-parse", "HEAD")

        result = self.create(path, "fix/F-2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WORKTREE_EXISTS_MOVED", result.stdout)
        self.assertIn("neu erhoben", result.stdout)
        self.assertEqual(_git(path, "rev-parse", "HEAD"), moved_head)

    def test_an_existing_worktree_on_another_branch_blocks_and_is_kept(self):
        path = self.root / "wt-3"
        self.assertEqual(self.create(path, "fix/F-3").returncode, 0)

        result = self.create(path, "fix/DIFFERENT")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("AUTONOMY_BLOCKER", result.stderr)
        self.assertTrue(path.is_dir(), "an existing worktree must never be deleted")


# --------------------------------------------------------------------------
# F-19: test discovery, and skip != pass
# --------------------------------------------------------------------------


PASSING_TEST = """\
import unittest


class Passing(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
"""

SKIPPING_SANDBOX_TEST = """\
import unittest


class SandboxProbe(unittest.TestCase):
    def test_sandbox_blocks_the_write(self):
        raise unittest.SkipTest("no active sandbox here")
"""

FAILING_TEST = """\
import unittest


class Failing(unittest.TestCase):
    def test_not_ok(self):
        self.assertTrue(False)
"""


class TestDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-discovery-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.root = self.tmp_dir / "project"
        self.guards = self.root / "factory" / "guards"
        self.hooks = self.root / ".claude" / "hooks"
        self.guards.mkdir(parents=True)
        self.hooks.mkdir(parents=True)

    def run_runner(self, *extra):
        return subprocess.run(
            [sys.executable, str(TEST_RUNNER), "--repo-root", str(self.root), "--quiet", *extra],
            capture_output=True,
            text=True,
        )

    def facts(self, result):
        return dict(
            line.split(": ", 1) for line in result.stdout.splitlines() if ": " in line
        )

    def test_a_new_test_file_runs_without_being_registered_anywhere(self):
        """The whole point of F-19: nothing has to be added to a list."""
        (self.guards / "test_brand_new.py").write_text(PASSING_TEST, encoding="utf-8")
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("factory/guards/test_brand_new.py", result.stdout)
        self.assertEqual(self.facts(result)["ci_tests_run"], "1")

    def test_hook_tests_are_discovered_too(self):
        (self.hooks / "test_hooky.py").write_text(PASSING_TEST, encoding="utf-8")
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(".claude/hooks/test_hooky.py", result.stdout)

    def test_discovering_nothing_is_a_hard_failure(self):
        """'no tests found' and 'all tests passed' must never look alike."""
        result = self.run_runner()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Kein einziges Testmodul gefunden", result.stderr)

    def test_a_failing_test_fails_the_runner(self):
        (self.guards / "test_broken.py").write_text(FAILING_TEST, encoding="utf-8")
        result = self.run_runner()
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_a_skipped_sandbox_test_is_not_reported_as_verification(self):
        (self.guards / "test_ok.py").write_text(PASSING_TEST, encoding="utf-8")
        (self.hooks / "test_sandbox_probe.py").write_text(
            SKIPPING_SANDBOX_TEST, encoding="utf-8"
        )
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SANDBOX_VERIFICATION: not_performed", result.stdout)
        self.assertIn("belegt NICHT", result.stdout)

    def test_require_sandbox_turns_a_skipped_verification_into_a_failure(self):
        (self.hooks / "test_sandbox_probe.py").write_text(
            SKIPPING_SANDBOX_TEST, encoding="utf-8"
        )
        result = self.run_runner("--require-sandbox")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("--require-sandbox", result.stderr)

    def test_a_really_executed_sandbox_test_counts_as_performed(self):
        (self.hooks / "test_sandbox_probe.py").write_text(PASSING_TEST, encoding="utf-8")
        result = self.run_runner("--require-sandbox")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SANDBOX_VERIFICATION: performed", result.stdout)


# --------------------------------------------------------------------------
# F-20: the credential lookup must never wait for a human
# --------------------------------------------------------------------------


class NonInteractiveCredentialTests(unittest.TestCase):
    """A missing credential must fail fast, not hang on /dev/tty."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-credential-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.root = self.tmp_dir / "project"
        self.root.mkdir()
        self.script = self.root / "factory" / "scripts" / "gh-api.sh"
        self.script.parent.mkdir(parents=True)
        shutil.copy2(GH_API, self.script)

        _git(self.root, "init", "--initial-branch=trunk")
        _git(self.root, "remote", "add", "origin", "https://github.com/example/repo.git")

        # An empty global config with no credential helper at all: nothing can
        # answer the fill request, which is exactly the situation that used to
        # open a prompt.
        self.empty_config = self.tmp_dir / "gitconfig"
        self.empty_config.write_text("", encoding="utf-8")

    def test_a_missing_credential_blocks_immediately_instead_of_prompting(self):
        env = dict(os.environ)
        env.update(
            {
                "HOME": str(self.tmp_dir),
                "GIT_CONFIG_GLOBAL": str(self.empty_config),
                "GIT_CONFIG_SYSTEM": "/dev/null",
                # Deliberately hostile: an askpass that would hang forever if
                # the script ever fell back to it.
                "GIT_ASKPASS": "/bin/cat",
                "SSH_ASKPASS": "/bin/cat",
            }
        )
        try:
            result = subprocess.run(
                ["bash", str(self.script), "GET", "/pulls"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                env=env,
                stdin=subprocess.DEVNULL,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            self.fail(
                "gh-api.sh waited for input instead of blocking -- exactly the "
                "unattended hang audit finding F-20 describes."
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kein GitHub-Credential", result.stderr)
        self.assertIn("nicht-interaktiv", result.stderr)

    def test_the_credential_value_is_never_printed(self):
        source = GH_API.read_text(encoding="utf-8")
        fill_lines = [line for line in source.splitlines() if "credential fill" in line]
        self.assertTrue(fill_lines)
        for line in fill_lines:
            self.assertNotIn("echo", line)
        # And the non-interactive settings are on the same invocation.
        joined = "\n".join(source.splitlines())
        self.assertIn("GIT_TERMINAL_PROMPT=0", joined)
        self.assertIn("GIT_ASKPASS=", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
