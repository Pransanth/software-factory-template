---
name: verify-finding
description: Drive a factory finding through IMPLEMENTING -> VERIFYING -> independent review -> READY_FOR_CLOSURE -> CLOSED, including push, autonomous PR, external GitHub CI and merge over the protected default branch. Use when a finding's fix is implemented and its gates need to be verified and an independent review obtained before closure.
argument-hint: [finding-id]
disable-model-invocation: true
---

This skill is the standardized, reusable procedure for verifying and closing a factory finding.
It does not invent security judgments itself — it systematically checks existing evidence
(finding, build order, tests, guards, CI) and delegates the actual security judgment to the
independent `finding-closure-reviewer` subagent. If you find yourself deciding "this looks fine"
on your own authority instead of citing a passed gate or the reviewer's verdict, stop — that is
exactly the shortcut this skill exists to prevent.

Argument: a finding ID. Its file is `factory/findings/<ID>.md`, its build order (if any) is
`factory/build-orders/<ID>.md`.

Every command below is a simple command run from the repository root (or the finding's worktree)
— no `git -C`, no `cd … &&`, no pipelines, no command substitution. See `CLAUDE.md`, "Git-Routine".

## Preconditions

- The finding's status must be `IMPLEMENTING` (to start this procedure) or already `VERIFYING`
  (to resume it). If it is anything else, stop — this skill does not analyze findings or start
  implementation, see the finding's own workflow rules (`.claude/rules/factory-workflow.md`).
- The finding's `Severity` must be filled in. A `Severity: P0` **cannot** be driven through this
  skill at all: the guard rejects any status past `ANALYZED` for a P0. Record the finding,
  describe the immediate situation, stop, involve a human.
- The finding must have a **valid build order** at `factory/build-orders/<ID>.md` (audit finding
  F-10). From IMPLEMENTING onwards `validate-finding.py` rejects the finding without one, so this
  is not a courtesy check: run
  `python3 factory/guards/validate-build-order.py factory/build-orders/<ID>.md` and fix whatever
  it reports before going further. A build order that is an empty shell of headings leaves the
  independent reviewer with nothing to hold the code against.
- Read the finding file and its build order in full before doing anything else.

## Step 0 — Resume: establish what already happened (audit finding F-16)

A session can die between any two steps below. Before doing anything, find out what is already
true instead of guessing. Redoing a push is harmless; carrying an old green result forward onto
new code is not.

```
python3 factory/guards/finding_state.py assess <ID>
git fetch origin
factory/scripts/gh-query.sh pr-for-branch <finding-branch>
```

`assess` prints one deterministic block: does the branch exist, is the recorded `pushed_sha` still
the branch head (`push_state: current|stale`), does the recorded CI evidence belong to that head
(`ci_state`), how many review rounds exist and does the newest still cover the current scope hash
(`review_state`), plus a single `resume_next:` line. `pr-for-branch` answers the GitHub half with
its own exit code: `0` a pull request exists, `3` none does, `4` the query failed — "no PR" and
"the query failed" are never the same answer.

**`stale` means invalid, not "probably fine".** If `push_state` or `ci_state` is `stale`, that
evidence belongs to a commit that is no longer the branch head: collect it again for the current
SHA. If `review_state` is `stale`, the review has expired and a new round is needed (Step 3).

Record what you establish, so the next session need not re-derive it:

```
python3 factory/guards/finding_state.py record <ID> branch=<branch> pushed_sha=<sha>
python3 factory/guards/finding_state.py record <ID> pr_number=<n> ci_head_sha=<sha> ci_run=<id>
```

That state lives under `.factory/`, is gitignored, and is an index into git, GitHub and
`factory/reviews/` — never a substitute for them, and never evidence in its own right. If a
worktree is involved, `factory/scripts/create-finding-worktree.sh create ...` is idempotent: it
reports `WORKTREE_READY`, `WORKTREE_EXISTS`, `WORKTREE_EXISTS_MOVED` or an `AUTONOMY_BLOCKER`, and
never deletes an existing worktree, which may hold unfinished work.

## Step 1 — IMPLEMENTING → VERIFYING: collect local gate evidence

Set `Status: VERIFYING` if not already there. Then run, and record the *actual* result of, each
of these gates — do not claim a gate passed without having just run it:

1. **Regression test** named in the finding's Regression Test Plan / the build order — must be
   green now (it was proven red before the fix; re-confirm it is green now).
2. **Relevant existing tests** — the test groups the build order identifies as touched by the
   fix.
3. **Central guard(s)** the build order's Central Guard Plan describes — run each directly
   against the relevant files, not just via the canonical runner.
4. **Canonical factory runner**: `python3 factory/guards/run-factory-checks.py` — must exit 0.
   This now also verifies the control plane against `factory/control-plane.sha256`. If it reports
   a control-plane difference, a normal finding has changed something it must not touch: revert
   that change rather than re-stamping the manifest.
5. **Project test suite**: `python3 factory/guards/run-project-tests.py` — must exit 0 (this is
   what CI will run too).
6. **Factory's own tests**: `python3 factory/guards/run-factory-tests.py` — must exit 0. Every
   `factory/guards/test_*.py` and `.claude/hooks/test_*.py` is discovered automatically (audit
   finding F-19), so a test file you added is executed without being registered anywhere. Read the
   `SANDBOX_VERIFICATION:` line rather than the pass count: `not_performed` means the OS-sandbox
   check skipped, which is not evidence that the sandbox protects anything.

Write what you found into the finding's `## Analyse` section as `Verification Evidence` (a
concise summary with concrete test/guard names and outcomes).

If any gate fails: stop here, report the failure, and do not proceed. A finding with a red gate
is not ready for review or for CI.

## Step 2 — External CI: push, PR, required status check

This is routine, pre-authorized factory work — it does not need a separate approval, and you do
not ask the user technical routine questions about it. Commit the finding's work on its own
finding branch, then:

```
git push origin <finding-branch>
factory/scripts/gh-query.sh pr-create "<title>" <finding-branch> <default-branch> "<body>"
git rev-parse HEAD
factory/scripts/gh-query.sh required-check <HEAD-SHA>
```

`<default-branch>` is never guessed — take it from `factory/scripts/gh-query.sh default-branch`
(or from `factory/scripts/create-finding-worktree.sh resolve`, which prints `DEFAULT_BRANCH`).

**`required-check` is the gate, not a summary you interpret.** It prints exactly one verdict and
exits with a matching code:

| Verdict | Exit | What to do |
|---|---|---|
| `success` | 0 | The required check passed for exactly this SHA. Proceed. |
| `pending` | 2 | Still running. Wait and re-run the same command. |
| `failed` | 1 | Fix the cause, push again, re-check. Never weaken a test, a guard or the workflow. |
| `absent` | 3 | No check with that name exists for this SHA. This is **not** a pass — CI may not have started, or the workflow/required-check name is misconfigured. |
| `api_error` | 4 | The answer was not usable (token, permissions, rate limit, network). Report it; do not treat it as "nothing there yet". |

Use `check-runs-summary <SHA>`, `actions-run-summary <finding-branch>` and
`actions-jobs-summary <RUN_ID>` when you need to see *why* a run failed.

Record the concrete run reference (run id and/or URL, its conclusion, and the head SHA it ran
against) as `CI Evidence` in the finding. Do not fabricate or assume a green CI run.

## Step 3 — Independent review

Only start the review once `required-check` returned `success` for the current head SHA, and do
not change any file between that point and the review. The reviewer's verdict will be bound to
the repository state at the moment it finishes (see Step 4), so a change in between simply
forces another round.

Use the Agent tool with `subagent_type: finding-closure-reviewer` to run the review in a
genuinely separate context. The reviewer has no memory of this conversation and read-only tools
(Read, Grep, Glob) — it cannot run commands or see a live diff unless you give it one. In the
prompt, include:
- The finding ID and path, and the build order path.
- What changed: ideally the actual diff (`git diff` / `git log`, gathered by you beforehand,
  since the reviewer cannot run Bash) or, at minimum, an explicit list of changed files.
- The diff basis to record as `Reviewed Commit`: a commit hash if committed, otherwise a clear
  statement like "uncommitted working tree changes since commit `<hash>`".
- Explicit instruction to check the ten points listed in its own agent definition and to end
  with exactly one of `PASS` / `FAIL` / `EXPERT_REVIEW_REQUIRED`, formatted as the field block
  described there.
- If the build order declares the finding a `FACTORY_CHANGE`, say so explicitly and ask for the
  **entire** control-plane diff to be reviewed, including whether
  `factory/control-plane.sha256` was re-stamped deliberately.

**Hard rule: you must not rewrite, soften, or reinterpret the reviewer's `Result`.** You do not
transcribe it at all — see Step 4. If you disagree with the verdict, say so plainly — do not
silently override it.

**Re-invoking the reviewer against unchanged code cannot help you.** Review rounds are
append-only and each one records the scope hash it saw; the closure guard rejects a `PASS` whose
scope hash matches an earlier non-PASS round. The only legitimate route after a `FAIL` is: repair
what was objected to, which changes the scope hash, then run a new round.

## Step 4 — Confirm the review artifact the hook produced

You do not write `factory/reviews/<ID>.round-<N>.md` yourself. The moment the reviewer subagent
in Step 3 finishes, a `SubagentStop` hook (`.claude/hooks/subagentstop-write-review.py`) fires
automatically: it reads the real Claude Code event data for that subagent run (`agent_type`,
`agent_id`, `last_assistant_message`), computes the repository's current scope hash, and writes
the next free round file from that — never from your own memory or summary of what the reviewer
said. `factory/reviews/` is also denied to the `Edit`/`Write` tools in `.claude/settings.json`
and to the sandbox, so you cannot create or modify a review artifact there even if you tried.

After the Agent tool call in Step 3 returns, confirm what the hook actually produced — do not
assume it worked. List the rounds and validate the newest one:
```
python3 factory/guards/validate-review.py factory/reviews/<ID>.round-<N>.md
```
- If no new round file exists, or this command fails: the reviewer's answer either didn't come
  from the expected agent type, was malformed (missing field, ambiguous or invalid `Result`
  value, wrong number of fenced blocks), or the scope hash could not be computed — the hook
  deliberately never writes a `PASS` artifact from unparseable input, and never writes an
  artifact it cannot bind to a code state. Read the reviewer's actual response to understand what
  went wrong, then either fix the reviewer's prompt/format guidance and get a fresh answer (a new
  review round, not a retry of the same one), or escalate. **Never hand-author or patch the
  review artifact yourself** — if the hook didn't produce it, it isn't a valid review artifact,
  full stop.
- If it validates: proceed to Step 5. The `Result` you act on there is read from this file, which
  by construction matches the hook's SubagentStop capture, not any restatement by you.

## Step 5 — Act on the verdict

- **Result: FAIL** — Do not touch the finding's status beyond where it already is (stay at
  `VERIFYING`). Report the reviewer's objections. Closure is blocked by
  `factory/guards/validate-finding.py` regardless. Either repair what was objected to and run a
  new review round, or stop and escalate — never argue the verdict away.
- **Result: EXPERT_REVIEW_REQUIRED** — Set the finding's `Status: EXPERT_REVIEW_REQUIRED` and
  fill its five required fields (`Risk Assessment`, `Expert Review Reason`, `What Is Known`,
  `What Remains Uncertain`, `What An Expert Would Need To Review`) using the reviewer's stated
  remaining risks and objections as the basis. **Stop here.** This is a human decision point per
  `CLAUDE.md` — do not merge, do not close.
- **Result: PASS** — proceed to Step 6.

## Step 6 — VERIFYING → READY_FOR_CLOSURE → CLOSED

Fill in `Review Artifact: factory/reviews/<ID>.round-<N>.md` (relative to the repo root, the
round you just validated) in the finding's `## Analyse` section alongside the
`Verification Evidence` and `CI Evidence` already written. Set `Status: READY_FOR_CLOSURE`.
Validate:
```
python3 factory/guards/validate-finding.py factory/findings/<ID>.md
python3 factory/guards/run-factory-checks.py
```
Both must pass. If they don't, the guard is telling you something concrete is still missing or
inconsistent — fix that specific thing, never work around the guard. Two failures are worth
recognising by name:

- *Scope-Hash-Abweichung*: something in the repository changed after the review. That is the
  mechanism working, not a nuisance. Run a new review round against the current state.
- *Runde X hatte Result FAIL fuer exakt denselben Codezustand*: an earlier round rejected this
  exact code. Repair, then review again.

Writing `Review Artifact` and `Status` into the finding does **not** invalidate the review: the
scope hash deliberately excludes `factory/findings/` and `factory/reviews/`.

A normal finding (no outstanding `EXPERT_REVIEW_REQUIRED`, `FAIL`, or unresolved high-risk
objection) may then be set to `Status: CLOSED` — this does not require separate human sign-off
beyond the independent review already obtained, per `CLAUDE.md`'s principle that Claude makes
normal technical decisions itself. A `FACTORY_CHANGE` is the documented exception and does
require a human decision. Re-run both commands to confirm `CLOSED` also validates.

## Step 7 — Merge over the protected default branch

Push the closure commit, confirm the required status check for the **new** head SHA, and merge
only that exact SHA:

```
git push origin <finding-branch>
git rev-parse HEAD
factory/scripts/gh-query.sh required-check <HEAD-SHA>
factory/scripts/gh-query.sh merge <PR-NUMBER> squash <HEAD-SHA>
```

The head SHA is a required argument to `merge`. It is checked locally first and then passed to
GitHub's merge API, so a push that landed after your evidence was collected makes the merge fail
server-side instead of riding along unreviewed. If the precheck reports `MERGE BLOCKED`, the head
moved, the PR is closed, or it was already merged — read the printed `precheck:` line and act on
it; never work around it.

If the merge call itself reports `merged: False` or `api_error`, read the `message` — the
protected branch refused the merge for a reason (missing required check, stale head,
insufficient permission). Report that reason; never work around branch protection.

Afterwards verify the real remote state rather than assuming it:
```
git fetch origin
git rev-parse origin/<default-branch>
```
