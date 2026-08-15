"""Tests for the deterministic GitHub evidence layer (audit F-06/F-07/F-08/F-17).

Run with:
    python3 -m unittest factory.guards.test_gh_evidence

Everything here runs offline against recorded payloads. That is the point:
before this layer existed, the failure modes below could not be tested at
all, because the logic lived in inline `python3 -c` snippets inside a shell
script that only ran against the live API.

Three groups:

  GhEvidenceRequiredCheckTests / ...ErrorTests / ...MergePrecheckTests
      the pure decision functions, fed the payload shapes GitHub actually
      returns, including every check-run status and conclusion the merge
      gate has to survive.

  GhQueryWiringTests
      gh-query.sh with a stub gh-api.sh, proving the exit code of a failing
      API call really reaches the caller instead of being swallowed into an
      innocuous-looking summary.

  GhApiSlugTests
      gh-api.sh's origin-URL normalization, which used to emit malformed API
      URLs for perfectly ordinary remotes.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARDS_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUARDS_DIR.parent.parent
GH_EVIDENCE = GUARDS_DIR / "gh_evidence.py"
GH_API = REPO_ROOT / "factory" / "scripts" / "gh-api.sh"
GH_QUERY = REPO_ROOT / "factory" / "scripts" / "gh-query.sh"

CHECK_NAME = "factory-checks"

EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_PENDING = 2
EXIT_ABSENT = 3
EXIT_API_ERROR = 4
EXIT_MISMATCH = 5

# Error bodies GitHub really returns, with the HTTP status the helper adds.
API_ERROR_BODIES = {
    401: {"message": "Bad credentials", "status": "401"},
    403: {"message": "Resource not accessible by personal access token", "status": "403"},
    404: {"message": "Not Found", "status": "404"},
    422: {"message": "Validation Failed", "errors": [], "status": "422"},
    429: {"message": "API rate limit exceeded for user ID 1.", "status": "429"},
    500: {"message": "Server Error", "status": "500"},
}


def check_run(name=CHECK_NAME, status="completed", conclusion="success", run_id=1):
    return {
        "id": run_id,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "head_sha": "deadbeef",
    }


def check_runs_payload(runs, total_count=None):
    return {
        "total_count": len(runs) if total_count is None else total_count,
        "check_runs": runs,
    }


def run_evidence(payload, *args):
    return subprocess.run(
        [sys.executable, str(GH_EVIDENCE), *args],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
    )


class GhEvidenceRequiredCheckTests(unittest.TestCase):
    """One exact SHA, one exact check name, one verdict, one exit code."""

    def verdict(self, payload, name=CHECK_NAME):
        result = run_evidence(payload, "required-check", name)
        first = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
        self.assertTrue(first.startswith("verdict: "), result.stdout + result.stderr)
        return first[len("verdict: ") :], result.returncode

    def test_single_success(self):
        self.assertEqual(
            self.verdict(check_runs_payload([check_run()])), ("success", EXIT_SUCCESS)
        )

    def test_failure_conclusion(self):
        self.assertEqual(
            self.verdict(check_runs_payload([check_run(conclusion="failure")])),
            ("failed", EXIT_FAILED),
        )

    def test_queued_is_pending_not_absent(self):
        self.assertEqual(
            self.verdict(check_runs_payload([check_run(status="queued", conclusion=None)])),
            ("pending", EXIT_PENDING),
        )

    def test_in_progress_is_pending(self):
        self.assertEqual(
            self.verdict(check_runs_payload([check_run(status="in_progress", conclusion=None)])),
            ("pending", EXIT_PENDING),
        )

    def test_cancelled_is_not_a_pass(self):
        self.assertEqual(
            self.verdict(check_runs_payload([check_run(conclusion="cancelled")])),
            ("failed", EXIT_FAILED),
        )

    def test_skipped_is_not_a_pass(self):
        """A skipped required check must never open a merge."""
        self.assertEqual(
            self.verdict(check_runs_payload([check_run(conclusion="skipped")])),
            ("failed", EXIT_FAILED),
        )

    def test_neutral_is_not_a_pass(self):
        self.assertEqual(
            self.verdict(check_runs_payload([check_run(conclusion="neutral")])),
            ("failed", EXIT_FAILED),
        )

    def test_stale_is_not_a_pass(self):
        self.assertEqual(
            self.verdict(check_runs_payload([check_run(conclusion="stale")])),
            ("failed", EXIT_FAILED),
        )

    def test_timed_out_is_not_a_pass(self):
        self.assertEqual(
            self.verdict(check_runs_payload([check_run(conclusion="timed_out")])),
            ("failed", EXIT_FAILED),
        )

    def test_completed_without_conclusion_is_not_a_pass(self):
        self.assertEqual(
            self.verdict(check_runs_payload([check_run(conclusion=None)])),
            ("failed", EXIT_FAILED),
        )

    def test_absent_when_no_run_carries_the_required_name(self):
        verdict, code = self.verdict(check_runs_payload([check_run(name="other-lint")]))
        self.assertEqual((verdict, code), ("absent", EXIT_ABSENT))

    def test_absent_on_empty_check_run_list(self):
        self.assertEqual(self.verdict(check_runs_payload([])), ("absent", EXIT_ABSENT))

    # -- several runs sharing the required check's name --------------------
    # factory-ci.yml triggers on push AND pull_request, so a finding branch
    # with an open PR normally has two runs named factory-checks per SHA.

    def test_two_same_named_runs_both_success(self):
        payload = check_runs_payload([check_run(run_id=1), check_run(run_id=2)])
        self.assertEqual(self.verdict(payload), ("success", EXIT_SUCCESS))

    def test_two_same_named_runs_one_failing_is_failed(self):
        payload = check_runs_payload(
            [check_run(run_id=1), check_run(run_id=2, conclusion="failure")]
        )
        self.assertEqual(self.verdict(payload), ("failed", EXIT_FAILED))

    def test_two_same_named_runs_one_pending_is_pending(self):
        payload = check_runs_payload(
            [check_run(run_id=1), check_run(run_id=2, status="queued", conclusion=None)]
        )
        self.assertEqual(self.verdict(payload), ("pending", EXIT_PENDING))

    def test_failure_beats_pending(self):
        payload = check_runs_payload(
            [
                check_run(run_id=1, status="queued", conclusion=None),
                check_run(run_id=2, conclusion="failure"),
            ]
        )
        self.assertEqual(self.verdict(payload), ("failed", EXIT_FAILED))

    def test_incomplete_pagination_is_an_api_error_not_a_verdict(self):
        payload = check_runs_payload([check_run()], total_count=42)
        verdict, code = self.verdict(payload)
        self.assertEqual((verdict, code), ("api_error", EXIT_API_ERROR))


class GhEvidenceApiErrorTests(unittest.TestCase):
    """F-07: an API error must never look like an empty normal state."""

    def test_every_error_status_is_reported_as_api_error(self):
        for status, body in sorted(API_ERROR_BODIES.items()):
            with self.subTest(status=status):
                result = run_evidence(body, "required-check", CHECK_NAME)
                self.assertEqual(result.returncode, EXIT_API_ERROR, result.stdout)
                self.assertIn("verdict: api_error", result.stdout)
                self.assertNotIn("no check runs", result.stdout)

    def test_error_body_in_check_runs_summary_is_api_error(self):
        result = run_evidence(API_ERROR_BODIES[429], "check-runs-summary")
        self.assertEqual(result.returncode, EXIT_API_ERROR, result.stdout)
        self.assertIn("api_error", result.stdout)

    def test_error_body_in_default_branch_is_api_error_not_none(self):
        result = run_evidence(API_ERROR_BODIES[401], "repo-default-branch")
        self.assertEqual(result.returncode, EXIT_API_ERROR, result.stdout)
        self.assertIn("api_error", result.stdout)
        self.assertNotIn("default_branch: None", result.stdout)

    def test_error_body_in_merge_result_is_api_error(self):
        body = {"message": 'Required status check "factory-checks" is expected.', "status": "405"}
        result = run_evidence(body, "merge-result")
        self.assertEqual(result.returncode, EXIT_API_ERROR, result.stdout)
        self.assertIn("api_error", result.stdout)
        self.assertNotIn("merged: None", result.stdout)

    def test_empty_body_is_api_error(self):
        result = run_evidence("", "required-check", CHECK_NAME)
        self.assertEqual(result.returncode, EXIT_API_ERROR, result.stdout)

    def test_non_json_body_is_api_error(self):
        result = run_evidence("<html>502 Bad Gateway</html>", "required-check", CHECK_NAME)
        self.assertEqual(result.returncode, EXIT_API_ERROR, result.stdout)

    def test_required_checks_error_body_is_api_error(self):
        result = run_evidence(API_ERROR_BODIES[403], "required-checks")
        self.assertEqual(result.returncode, EXIT_API_ERROR, result.stdout)


class GhEvidenceMergePrecheckTests(unittest.TestCase):
    """F-08: merge only the exact head SHA that CI and review actually saw."""

    def pr(self, head_sha="aaa", state="open", merged=False):
        return {"number": 7, "state": state, "merged": merged, "head": {"sha": head_sha}}

    def test_matching_head_passes(self):
        result = run_evidence(self.pr(), "merge-precheck", "aaa")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("precheck: ok", result.stdout)

    def test_stale_expected_head_is_blocked(self):
        result = run_evidence(self.pr(head_sha="bbb"), "merge-precheck", "aaa")
        self.assertEqual(result.returncode, EXIT_MISMATCH, result.stdout)
        self.assertIn("MERGE BLOCKED", result.stdout)
        self.assertIn("precheck: head_mismatch", result.stdout)

    def test_already_merged_pr_is_blocked(self):
        result = run_evidence(self.pr(merged=True), "merge-precheck", "aaa")
        self.assertEqual(result.returncode, EXIT_MISMATCH, result.stdout)
        self.assertIn("already_merged", result.stdout)

    def test_closed_pr_is_blocked(self):
        result = run_evidence(self.pr(state="closed"), "merge-precheck", "aaa")
        self.assertEqual(result.returncode, EXIT_MISMATCH, result.stdout)
        self.assertIn("not_open", result.stdout)

    def test_api_error_is_not_a_merge_permission(self):
        result = run_evidence(API_ERROR_BODIES[404], "merge-precheck", "aaa")
        self.assertEqual(result.returncode, EXIT_API_ERROR, result.stdout)


class GhEvidenceJsonObjectTests(unittest.TestCase):
    def test_values_with_quotes_and_newlines_survive(self):
        result = subprocess.run(
            [
                sys.executable,
                str(GH_EVIDENCE),
                "--json-object",
                "title",
                'fix: "quoted" \\ and\nnewline',
                "head",
                "fix/x",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["title"], 'fix: "quoted" \\ and\nnewline')
        self.assertEqual(parsed["head"], "fix/x")

    def test_odd_number_of_arguments_is_a_usage_error(self):
        result = subprocess.run(
            [sys.executable, str(GH_EVIDENCE), "--json-object", "title"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)


class GhQueryWiringTests(unittest.TestCase):
    """gh-query.sh must propagate a failing API call, not absorb it."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-gh-query-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        scripts_dir = self.tmp_dir / "factory" / "scripts"
        guards_dir = self.tmp_dir / "factory" / "guards"
        scripts_dir.mkdir(parents=True)
        guards_dir.mkdir(parents=True)
        shutil.copy2(GH_QUERY, scripts_dir / "gh-query.sh")
        shutil.copy2(GH_EVIDENCE, guards_dir / "gh_evidence.py")
        self.gh_query = scripts_dir / "gh-query.sh"
        self.stub = scripts_dir / "gh-api.sh"

    def write_stub(self, body, exit_code=0):
        self.stub.write_text(
            "#!/usr/bin/env bash\n"
            f"cat <<'STUB_BODY_EOF'\n{body}\nSTUB_BODY_EOF\n"
            f"exit {exit_code}\n",
            encoding="utf-8",
        )
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IXUSR)

    def run_query(self, *args):
        return subprocess.run(
            ["bash", str(self.gh_query), *args], capture_output=True, text=True
        )

    def test_successful_required_check_exits_zero(self):
        self.write_stub(json.dumps(check_runs_payload([check_run()])))
        result = self.run_query("required-check", "deadbeef")
        self.assertEqual(result.returncode, EXIT_SUCCESS, result.stdout + result.stderr)
        self.assertIn("verdict: success", result.stdout)

    def test_http_error_from_gh_api_reaches_the_caller(self):
        self.write_stub(json.dumps(API_ERROR_BODIES[403]), exit_code=3)
        result = self.run_query("required-check", "deadbeef")
        self.assertEqual(result.returncode, EXIT_API_ERROR, result.stdout + result.stderr)
        self.assertIn("api_error", result.stdout)

    def test_failing_check_exits_nonzero(self):
        self.write_stub(json.dumps(check_runs_payload([check_run(conclusion="failure")])))
        result = self.run_query("required-check", "deadbeef")
        self.assertEqual(result.returncode, EXIT_FAILED, result.stdout)

    def test_merge_refuses_without_expected_head_sha(self):
        self.write_stub("{}")
        result = self.run_query("merge", "7", "squash")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Head-SHA ist Pflicht", result.stderr)

    def test_merge_stops_at_the_precheck_on_a_stale_head(self):
        self.write_stub(
            json.dumps({"number": 7, "state": "open", "merged": False, "head": {"sha": "bbb"}})
        )
        result = self.run_query("merge", "7", "squash", "aaa")
        self.assertEqual(result.returncode, EXIT_MISMATCH, result.stdout)
        self.assertIn("MERGE BLOCKED", result.stdout)
        self.assertIn("nicht ausgefuehrt", result.stdout)


class GhApiSlugTests(unittest.TestCase):
    """F-17: every supported remote spelling, and a hard stop for the rest."""

    def slug(self, url):
        return subprocess.run(
            ["bash", str(GH_API), "slug", url], capture_output=True, text=True
        )

    def assertSlug(self, url, expected):
        result = self.slug(url)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"slug: {expected}", result.stdout)

    def test_https_with_git_suffix(self):
        self.assertSlug("https://github.com/owner/repo.git", "owner/repo")

    def test_https_without_git_suffix(self):
        self.assertSlug("https://github.com/owner/repo", "owner/repo")

    def test_https_with_trailing_slash(self):
        self.assertSlug("https://github.com/owner/repo/", "owner/repo")

    def test_https_with_user(self):
        self.assertSlug("https://user@github.com/owner/repo.git", "owner/repo")

    def test_scp_style(self):
        self.assertSlug("git@github.com:owner/repo.git", "owner/repo")

    def test_ssh_url(self):
        self.assertSlug("ssh://git@github.com/owner/repo.git", "owner/repo")

    def test_repo_name_with_dots_and_dashes(self):
        self.assertSlug("https://github.com/my-org/my.repo-name.git", "my-org/my.repo-name")

    def test_non_github_host_is_rejected(self):
        result = self.slug("https://gitlab.com/owner/repo.git")
        self.assertEqual(result.returncode, 1)
        self.assertIn("OWNER/REPO", result.stderr)

    def test_url_with_extra_path_segments_is_rejected(self):
        result = self.slug("https://github.com/owner/repo/tree/main")
        self.assertEqual(result.returncode, 1)

    def test_empty_url_is_rejected(self):
        result = self.slug("")
        self.assertEqual(result.returncode, 1)

    def test_credential_path_keeps_the_git_suffix_when_present(self):
        result = self.slug("https://github.com/owner/repo.git")
        self.assertIn("credential_path: owner/repo.git", result.stdout)

    def test_credential_path_without_git_suffix(self):
        result = self.slug("https://github.com/owner/repo")
        self.assertIn("credential_path: owner/repo", result.stdout)


if __name__ == "__main__":
    unittest.main()
