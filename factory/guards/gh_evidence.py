#!/usr/bin/env python3
"""Deterministic interpretation of GitHub API answers for factory routine work.

Usage (JSON body arrives on stdin, printed result is plain "key: value" lines):

    factory/scripts/gh-api.sh GET /commits/<sha>/check-runs \\
        | python3 factory/guards/gh_evidence.py required-check factory-checks

    ... | python3 factory/guards/gh_evidence.py pr-summary
    ... | python3 factory/guards/gh_evidence.py merge-precheck <EXPECTED_HEAD_SHA>
    ... | python3 factory/guards/gh_evidence.py repo-default-branch
    ... | python3 factory/guards/gh_evidence.py required-checks
    ... | python3 factory/guards/gh_evidence.py check-runs-summary
    ... | python3 factory/guards/gh_evidence.py actions-run-summary
    ... | python3 factory/guards/gh_evidence.py actions-jobs-summary
    ... | python3 factory/guards/gh_evidence.py merge-result
    ... | python3 factory/guards/gh_evidence.py pr-create-result

Why this is a Python module with its own tests rather than the inline
`python3 -c` snippets gh-query.sh used before (audit findings F-06/F-07/F-08):

  - **An API error used to look like a normal empty state.** A 401, a 403,
    a rate limit or a 5xx returns a JSON body too, and `data.get("check_runs", [])`
    turned that body into "no check runs yet" -- the exact same output as
    "CI has not started". A polling agent could not tell the difference and
    would wait forever, or conclude the wrong thing. Every mode here
    recognises an error body and says `api_error`, with a non-zero exit code.

  - **The merge decision used to be prose.** `check-runs-summary` printed an
    unfiltered list of every check run and left it to a language model to
    decide whether the required one had passed. `required-check` replaces
    that with one verdict and one exit code, and it handles the states that
    a list of names silently glossed over: queued, in_progress, cancelled,
    skipped, neutral, stale, several runs sharing the required check's name
    (the factory's own workflow triggers on both push and pull_request, so
    that is the normal case, not an exotic one), and incomplete pagination.

  - **It is testable without a network.** factory/guards/test_gh_evidence.py
    feeds recorded payloads through these functions. That is the only way
    the failure modes above can be regression-tested at all.

Verdicts and exit codes for `required-check`:

    success   0   every run with that exact name completed with conclusion success
    failed    1   at least one such run finished in any other way
    pending   2   at least one such run is still queued/in progress, none failed
    absent    3   no check run with that name exists for this commit
    api_error 4   the answer is not a usable check-runs payload

Only `success` (exit 0) may lead to a merge. Everything else, including
`absent`, blocks -- "the check is not there" is not "the check passed".

No token, header or credential value is ever read or printed here: this
module only ever sees a response body.
"""
import json
import sys

# Check-run statuses that mean "not finished yet".
PENDING_STATUSES = {"queued", "in_progress", "waiting", "requested", "pending"}

# The only conclusion that counts as a pass. Everything else -- failure,
# cancelled, timed_out, action_required, startup_failure, stale, and also
# neutral and skipped -- is deliberately NOT a pass: merging on a skipped or
# neutral required check is precisely the false green this replaces.
SUCCESS_CONCLUSION = "success"

VERDICT_EXIT_CODES = {
    "success": 0,
    "failed": 1,
    "pending": 2,
    "absent": 3,
    "api_error": 4,
}

MISMATCH_EXIT_CODE = 5
USAGE_EXIT_CODE = 2


class ApiError(Exception):
    """The payload is not a usable answer of the expected shape."""


def load_payload(stream):
    """Parse the response body, or raise ApiError with a usable description."""
    raw = stream.read()
    if not raw.strip():
        raise ApiError("leere Antwort (kein JSON-Body)")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ApiError(f"Antwort ist kein gueltiges JSON: {exc}") from exc


def error_message(payload):
    """Return GitHub's error text if the payload is an error object, else None.

    GitHub reports errors as a JSON object with a "message" field and no
    payload-specific keys. Callers pass the keys they expect, so a legitimate
    answer that happens to contain "message" (a merge result, for example) is
    not mistaken for an error.
    """
    if isinstance(payload, dict) and "message" in payload:
        status = payload.get("status")
        message = str(payload.get("message"))
        return f"{message}" if status is None else f"HTTP {status}: {message}"
    return None


def _require_dict_without_error(payload, expected_key):
    if not isinstance(payload, dict):
        raise ApiError(f"unerwartete Antwortform: {type(payload).__name__}")
    if expected_key not in payload:
        detail = error_message(payload) or "unerwartete Antwort ohne erwartete Felder"
        raise ApiError(detail)
    return payload


def classify_required_check(payload, check_name):
    """Return (verdict, [detail lines]) for one required check name.

    Aggregation across several runs with the same name is deliberately
    pessimistic: any failure wins, then any pending, and only an all-success
    set is a success.
    """
    data = _require_dict_without_error(payload, "check_runs")
    runs = data.get("check_runs")
    if not isinstance(runs, list):
        raise ApiError("'check_runs' ist keine Liste")

    total_count = data.get("total_count")
    if isinstance(total_count, int) and total_count > len(runs):
        raise ApiError(
            f"unvollstaendige Seite: total_count={total_count}, aber nur {len(runs)} "
            "check_runs geliefert. Ohne vollstaendige Liste wird kein Urteil gefaellt."
        )

    matching = [run for run in runs if isinstance(run, dict) and run.get("name") == check_name]
    details = [f"check_name: {check_name}", f"matching_runs: {len(matching)}"]

    if not matching:
        other_names = sorted({str(run.get("name")) for run in runs if isinstance(run, dict)})
        details.append("other_checks: " + (", ".join(other_names) if other_names else "(keine)"))
        return "absent", details

    has_failure = False
    has_pending = False
    for run in matching:
        status = str(run.get("status") or "").lower()
        conclusion = run.get("conclusion")
        conclusion_text = str(conclusion).lower() if conclusion is not None else "none"
        details.append(
            f"run: id={run.get('id')} status={status or 'none'} "
            f"conclusion={conclusion_text} head_sha={run.get('head_sha')}"
        )
        if status in PENDING_STATUSES:
            has_pending = True
        elif conclusion_text != SUCCESS_CONCLUSION:
            has_failure = True

    if has_failure:
        return "failed", details
    if has_pending:
        return "pending", details
    return "success", details


def pr_summary(payload):
    data = _require_dict_without_error(payload, "number")
    head = data.get("head") or {}
    base = data.get("base") or {}
    return [
        f"number: {data.get('number')}",
        f"state: {data.get('state')}",
        f"merged: {data.get('merged')}",
        f"mergeable: {data.get('mergeable')}",
        f"mergeable_state: {data.get('mergeable_state')}",
        f"head_ref: {head.get('ref')}",
        f"head_sha: {head.get('sha')}",
        f"base_ref: {base.get('ref')}",
        f"base_sha: {base.get('sha')}",
    ]


def merge_precheck(payload, expected_head_sha):
    """Refuse to merge a head the review and CI never saw (audit finding F-08)."""
    data = _require_dict_without_error(payload, "number")
    head = (data.get("head") or {}).get("sha")
    state = data.get("state")
    merged = data.get("merged")
    lines = [
        f"number: {data.get('number')}",
        f"state: {state}",
        f"merged: {merged}",
        f"head_sha: {head}",
        f"expected_head_sha: {expected_head_sha}",
    ]
    if merged is True:
        lines.append("precheck: already_merged")
        return False, lines
    if state != "open":
        lines.append(f"precheck: not_open ({state})")
        return False, lines
    if head != expected_head_sha:
        lines.append("precheck: head_mismatch")
        return False, lines
    lines.append("precheck: ok")
    return True, lines


def repo_default_branch(payload):
    data = _require_dict_without_error(payload, "default_branch")
    return [f"default_branch: {data.get('default_branch')}"]


def required_checks(payload):
    if not isinstance(payload, list):
        detail = error_message(payload) or "unerwartete Antwort (keine Regel-Liste)"
        raise ApiError(detail)
    contexts = []
    for rule in payload:
        if isinstance(rule, dict) and rule.get("type") == "required_status_checks":
            parameters = rule.get("parameters") or {}
            for check in parameters.get("required_status_checks") or []:
                if isinstance(check, dict):
                    contexts.append(str(check.get("context")))
    rule_types = sorted({str(r.get("type")) for r in payload if isinstance(r, dict)})
    lines = [f"rule_count: {len(payload)}", "rule_types: " + (", ".join(rule_types) or "(keine)")]
    if not contexts:
        lines.append("required_status_check: (keine konfiguriert)")
    for context in contexts:
        lines.append(f"required_status_check: {context}")
    return lines


def pr_for_branch(payload, branch):
    """Which pull request already exists for this branch (audit finding F-16)?

    Resume needs this: after a crashed session a new agent must be able to
    tell "no PR yet" from "PR #4 is open" from "PR #4 was already merged"
    without guessing from local state, which may be gone. Absence is reported
    as its own verdict with its own exit code -- "there is no PR" must never
    look like "the query failed", and vice versa.
    """
    if not isinstance(payload, list):
        detail = error_message(payload) or "unerwartete Antwort (keine PR-Liste)"
        raise ApiError(detail)

    matching = [
        pr
        for pr in payload
        if isinstance(pr, dict) and ((pr.get("head") or {}).get("ref") == branch)
    ]

    lines = [f"branch: {branch}", f"pr_count: {len(matching)}"]
    if not matching:
        lines.append("pr_for_branch: none")
        return "absent", lines

    for pr in matching:
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        lines.append(
            f"pr: number={pr.get('number')} state={pr.get('state')} "
            f"merged={'true' if pr.get('merged_at') else 'false'} "
            f"head_sha={head.get('sha')} base_ref={base.get('ref')}"
        )

    # At most one pull request per head branch can be open at a time, so an
    # open one is unambiguous. Otherwise take the highest number, which is the
    # most recently created -- deterministic, unlike "most recently updated".
    open_prs = [pr for pr in matching if pr.get("state") == "open"]
    chosen = open_prs[0] if open_prs else max(matching, key=lambda pr: pr.get("number") or 0)
    lines += [
        f"current_pr: {chosen.get('number')}",
        f"current_pr_state: {chosen.get('state')}",
        f"current_pr_merged: {'true' if chosen.get('merged_at') else 'false'}",
        f"current_pr_head_sha: {(chosen.get('head') or {}).get('sha')}",
    ]
    return "present", lines


def pr_permission_probe(payload, api_exit_code):
    """Can this token open pull requests (audit finding F-12)?

    The probe posts head == base, which can never create a pull request, and
    GitHub checks token permission before it validates the payload. So a
    validation error proves the permission is there.

    The pre-repair version classified by exclusion: anything that was not
    recognisably a 403 was reported as PERMITTED. A 401 from a wrong or
    expired token, a 404 from a repository the token cannot see, an empty
    body, a rate limit and an HTML error page all ended up as "Token darf
    Pull Requests erstellen". Onboarding then declared the factory ready, and
    the truth surfaced much later -- at the moment the first real pull request
    was supposed to be opened, in an unattended run.

    This version recognises permission POSITIVELY and only positively: the
    request must have failed with GitHub's own validation error. Everything
    else is blocked, including answers this code has never seen.
    """
    lines = [f"api_exit_code: {api_exit_code}"]

    if api_exit_code == 0:
        # A pull request was actually created -- impossible for head == base,
        # so something is wrong enough that a human has to look.
        number = payload.get("number") if isinstance(payload, dict) else None
        lines += [f"created_pr: {number}", "probe: created"]
        return "created", lines

    message = ""
    if isinstance(payload, dict):
        message = str(payload.get("message") or "")
    lines.append(f"github_message: {message or '(keine)'}")

    if api_exit_code == VERDICT_EXIT_CODES["api_error"]:
        lines.append("probe: api_error")
        return "api_error", lines

    if message.strip().lower() == "validation failed":
        lines.append("probe: permitted")
        return "permitted", lines

    lines.append("probe: blocked")
    return "blocked", lines


def _protection_facts(parameters, check_name, contexts):
    """Shared rendering for ruleset rules and classic protection."""
    approvals = parameters.get("required_approving_review_count")
    return [
        f"required_approving_review_count: {approvals if approvals is not None else 0}",
        "required_status_checks: " + (", ".join(contexts) if contexts else "(keine)"),
        f"required_check_present: {'true' if check_name in contexts else 'false'}",
    ]


def ruleset_guarantees(payload, check_name):
    """What a ruleset on this branch actually guarantees (audit finding F-13).

    The pre-repair preflight only counted the rules it got back: `COUNT 1` was
    reported as "Branch-Schutz aktiv". A ruleset that only blocks force-pushes
    counts as 1 and guarantees nothing whatsoever about merging. This reads the
    rules instead: is a pull request required at all, is the factory's required
    status check among the required contexts, and do required approvals mean a
    human has to approve before anything can merge.
    """
    if not isinstance(payload, list):
        detail = error_message(payload) or "unerwartete Antwort (keine Regel-Liste)"
        raise ApiError(detail)

    rule_types = sorted({str(rule.get("type")) for rule in payload if isinstance(rule, dict)})
    pull_request_params = {}
    contexts = []
    for rule in payload:
        if not isinstance(rule, dict):
            continue
        parameters = rule.get("parameters") or {}
        if rule.get("type") == "pull_request":
            pull_request_params = parameters
        elif rule.get("type") == "required_status_checks":
            for check in parameters.get("required_status_checks") or []:
                if isinstance(check, dict):
                    contexts.append(str(check.get("context")))

    lines = [
        "source: ruleset",
        f"rule_count: {len(payload)}",
        "rule_types: " + (", ".join(rule_types) if rule_types else "(keine)"),
        f"pull_request_required: {'true' if 'pull_request' in rule_types else 'false'}",
    ]
    lines += _protection_facts(pull_request_params, check_name, contexts)
    return lines


def classic_protection(payload, api_exit_code, check_name):
    """Classic branch protection, for repositories that do not use rulesets.

    A branch may be protected by a ruleset, by classic branch protection, or by
    both. Reading only one of them and reporting "kein Schutz" for the other is
    a false negative that pushes a project towards adding protection it already
    has -- or worse, towards concluding the check is unreliable and ignoring it.
    GitHub answers 404 "Branch not protected" when no classic protection
    exists, which is a legitimate state and not an error.
    """
    lines = [f"api_exit_code: {api_exit_code}"]
    message = str(payload.get("message") or "") if isinstance(payload, dict) else ""

    if api_exit_code != 0:
        if message.strip().lower() == "branch not protected":
            lines += ["source: classic", "classic_protection: absent"]
            return lines
        raise ApiError(message or f"gh-api.sh endete mit Exit {api_exit_code}")

    if not isinstance(payload, dict):
        raise ApiError(f"unerwartete Antwortform: {type(payload).__name__}")

    reviews = payload.get("required_pull_request_reviews")
    status_checks = payload.get("required_status_checks") or {}
    contexts = [str(context) for context in (status_checks.get("contexts") or [])]

    lines += [
        "source: classic",
        "classic_protection: present",
        f"pull_request_required: {'true' if isinstance(reviews, dict) else 'false'}",
    ]
    lines += _protection_facts(reviews or {}, check_name, contexts)
    return lines


def check_runs_summary(payload):
    data = _require_dict_without_error(payload, "check_runs")
    runs = data.get("check_runs") or []
    lines = [f"total_count: {data.get('total_count')}", f"returned: {len(runs)}"]
    if not runs:
        lines.append("check_runs: (keine)")
    for run in runs:
        if isinstance(run, dict):
            lines.append(
                f"check_run: name={run.get('name')} status={run.get('status')} "
                f"conclusion={run.get('conclusion')} head_sha={run.get('head_sha')}"
            )
    return lines


def actions_run_summary(payload):
    data = _require_dict_without_error(payload, "workflow_runs")
    runs = data.get("workflow_runs") or []
    if not runs:
        return ["workflow_runs: (keine)"]
    lines = []
    for run in runs[:5]:
        if isinstance(run, dict):
            lines.append(
                f"run: id={run.get('id')} name={run.get('name')} "
                f"status={run.get('status')} conclusion={run.get('conclusion')} "
                f"head_sha={run.get('head_sha')} event={run.get('event')}"
            )
    return lines


def actions_jobs_summary(payload):
    data = _require_dict_without_error(payload, "jobs")
    lines = []
    for job in data.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        lines.append(
            f"job: {job.get('name')} status={job.get('status')} "
            f"conclusion={job.get('conclusion')}"
        )
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                lines.append(
                    f"  step: {step.get('name')} status={step.get('status')} "
                    f"conclusion={step.get('conclusion')}"
                )
    return lines or ["jobs: (keine)"]


def merge_result(payload):
    if not isinstance(payload, dict):
        raise ApiError(f"unerwartete Antwortform: {type(payload).__name__}")
    if "merged" not in payload:
        raise ApiError(error_message(payload) or "unerwartete Antwort ohne 'merged'")
    return [
        f"merged: {payload.get('merged')}",
        f"sha: {payload.get('sha')}",
        f"message: {payload.get('message')}",
    ]


def pr_create_result(payload):
    data = _require_dict_without_error(payload, "number")
    head = data.get("head") or {}
    return [
        f"number: {data.get('number')}",
        f"html_url: {data.get('html_url')}",
        f"state: {data.get('state')}",
        f"head_sha: {head.get('sha')}",
    ]


SIMPLE_MODES = {
    "pr-summary": pr_summary,
    "repo-default-branch": repo_default_branch,
    "required-checks": required_checks,
    "check-runs-summary": check_runs_summary,
    "actions-run-summary": actions_run_summary,
    "actions-jobs-summary": actions_jobs_summary,
    "merge-result": merge_result,
    "pr-create-result": pr_create_result,
}


def _print_api_error(exc):
    print(f"api_error: {exc}")
    print(
        "hinweis: das ist KEIN leerer Normalzustand. Die Abfrage hat keine "
        "verwertbare Antwort geliefert (Token, Rechte, Rate-Limit, Netz oder "
        "unerwartetes Format)."
    )


def build_json_object(pairs):
    """Build a JSON object from alternating key/value arguments.

    Used by gh-query.sh to construct request bodies. Doing it here rather
    than by interpolating values into a JSON string in shell means a title
    or PR body containing quotes, newlines or backslashes cannot break the
    payload -- and it keeps the caller a single static command shape with
    only plain-data arguments.
    """
    if len(pairs) % 2 != 0:
        raise ValueError("--json-object braucht Paare aus Schluessel und Wert")
    return json.dumps({pairs[i]: pairs[i + 1] for i in range(0, len(pairs), 2)})


def main(argv):
    if len(argv) < 2:
        print(
            "usage: gh_evidence.py {required-check <NAME>|merge-precheck <SHA>|"
            "--json-object <key> <value> ...|"
            + "|".join(sorted(SIMPLE_MODES))
            + "}",
            file=sys.stderr,
        )
        return USAGE_EXIT_CODE

    mode = argv[1]

    if mode == "--json-object":
        # Payload construction, not answer interpretation: reads no stdin.
        try:
            print(build_json_object(argv[2:]))
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return USAGE_EXIT_CODE
        return 0

    try:
        payload = load_payload(sys.stdin)
    except ApiError as exc:
        _print_api_error(exc)
        return VERDICT_EXIT_CODES["api_error"]

    if mode == "required-check":
        if len(argv) != 3:
            print("usage: gh_evidence.py required-check <CHECK_NAME>", file=sys.stderr)
            return USAGE_EXIT_CODE
        try:
            verdict, details = classify_required_check(payload, argv[2])
        except ApiError as exc:
            print("verdict: api_error")
            _print_api_error(exc)
            return VERDICT_EXIT_CODES["api_error"]
        print(f"verdict: {verdict}")
        for line in details:
            print(line)
        return VERDICT_EXIT_CODES[verdict]

    if mode == "pr-for-branch":
        if len(argv) != 3:
            print("usage: gh_evidence.py pr-for-branch <BRANCH>", file=sys.stderr)
            return USAGE_EXIT_CODE
        try:
            verdict, details = pr_for_branch(payload, argv[2])
        except ApiError as exc:
            print("pr_for_branch: api_error")
            _print_api_error(exc)
            return VERDICT_EXIT_CODES["api_error"]
        for line in details:
            print(line)
        return 0 if verdict == "present" else VERDICT_EXIT_CODES["absent"]

    if mode == "pr-permission-probe":
        if len(argv) != 3:
            print(
                "usage: gh_evidence.py pr-permission-probe <GH_API_EXIT_CODE>",
                file=sys.stderr,
            )
            return USAGE_EXIT_CODE
        try:
            api_exit_code = int(argv[2])
        except ValueError:
            print("usage: gh_evidence.py pr-permission-probe <GH_API_EXIT_CODE>", file=sys.stderr)
            return USAGE_EXIT_CODE
        verdict, details = pr_permission_probe(payload, api_exit_code)
        for line in details:
            print(line)
        if verdict == "permitted":
            return 0
        if verdict == "api_error":
            return VERDICT_EXIT_CODES["api_error"]
        return 1

    if mode == "ruleset-guarantees":
        if len(argv) != 3:
            print("usage: gh_evidence.py ruleset-guarantees <CHECK_NAME>", file=sys.stderr)
            return USAGE_EXIT_CODE
        try:
            lines = ruleset_guarantees(payload, argv[2])
        except ApiError as exc:
            _print_api_error(exc)
            return VERDICT_EXIT_CODES["api_error"]
        for line in lines:
            print(line)
        return 0

    if mode == "classic-protection":
        if len(argv) != 4:
            print(
                "usage: gh_evidence.py classic-protection <GH_API_EXIT_CODE> <CHECK_NAME>",
                file=sys.stderr,
            )
            return USAGE_EXIT_CODE
        try:
            api_exit_code = int(argv[2])
        except ValueError:
            print(
                "usage: gh_evidence.py classic-protection <GH_API_EXIT_CODE> <CHECK_NAME>",
                file=sys.stderr,
            )
            return USAGE_EXIT_CODE
        try:
            lines = classic_protection(payload, api_exit_code, argv[3])
        except ApiError as exc:
            _print_api_error(exc)
            return VERDICT_EXIT_CODES["api_error"]
        for line in lines:
            print(line)
        return 0

    if mode == "merge-precheck":
        if len(argv) != 3:
            print("usage: gh_evidence.py merge-precheck <EXPECTED_HEAD_SHA>", file=sys.stderr)
            return USAGE_EXIT_CODE
        try:
            ok, details = merge_precheck(payload, argv[2])
        except ApiError as exc:
            _print_api_error(exc)
            return VERDICT_EXIT_CODES["api_error"]
        for line in details:
            print(line)
        if not ok:
            print("MERGE BLOCKED")
            return MISMATCH_EXIT_CODE
        return 0

    handler = SIMPLE_MODES.get(mode)
    if handler is None:
        print(f"ERROR: unbekannter Modus '{mode}'", file=sys.stderr)
        return USAGE_EXIT_CODE

    try:
        lines = handler(payload)
    except ApiError as exc:
        _print_api_error(exc)
        return VERDICT_EXIT_CODES["api_error"]

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
