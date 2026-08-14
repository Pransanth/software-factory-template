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
- Read the finding file and its build order in full before doing anything else.

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
5. **Project test suite**: `python3 factory/guards/run-project-tests.py` — must exit 0 (this is
   what CI will run too).

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
factory/scripts/gh-query.sh pr-summary <PR-NUMBER>
factory/scripts/gh-query.sh check-runs-summary <HEAD-SHA>
```

`<default-branch>` is never guessed — take it from `factory/scripts/gh-query.sh default-branch`
(or from `factory/scripts/create-finding-worktree.sh resolve`, which prints `DEFAULT_BRANCH`).
Poll `check-runs-summary` for the head SHA until the required check has `status=completed`; use
`actions-run-summary <finding-branch>` and `actions-jobs-summary <RUN_ID>` when you need to see
*why* a run failed.

Record the concrete run reference (run id and/or URL, plus its conclusion) as `CI Evidence` in
the finding. Do not fabricate or assume a green CI run: a claimed CI Evidence that does not match
a real run is exactly the kind of thing the independent reviewer is there to catch.

A red CI run is a normal outcome, not a blocker to route around: fix the cause, push again, and
re-check. Never weaken a test, a guard or the workflow to make CI green.

## Step 3 — Independent review

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

**Hard rule: you must not rewrite, soften, or reinterpret the reviewer's `Result`.** You do not
transcribe it at all — see Step 4. If you disagree with the verdict, say so plainly — do not
silently override it. Re-invoking the reviewer to "try again" hoping for a different answer
defeats its independence; only re-invoke it if you are giving it materially new information
(e.g. you fixed something it flagged) and are running an entirely new review round.

## Step 4 — Confirm the review artifact the hook produced

You do not write `factory/reviews/<ID>.md` yourself. The moment the reviewer subagent in Step 3
finishes, a `SubagentStop` hook (`.claude/hooks/subagentstop-write-review.py`) fires
automatically: it reads the real Claude Code event data for that subagent run (`agent_type`,
`agent_id`, `last_assistant_message`) and writes `factory/reviews/<ID>.md` directly from it —
never from your own memory or summary of what the reviewer said. `factory/reviews/` is also
denied to the `Edit`/`Write` tools in `.claude/settings.json` and to the sandbox, so you cannot
create or modify a review artifact there even if you tried.

After the Agent tool call in Step 3 returns, confirm what the hook actually produced — do not
assume it worked:
```
python3 factory/guards/validate-review.py factory/reviews/<ID>.md
```
- If `factory/reviews/<ID>.md` doesn't exist, or this command fails: the reviewer's answer either
  didn't come from the expected agent type, was malformed (missing field, ambiguous or invalid
  `Result` value, wrong number of fenced blocks), or was otherwise rejected by the hook — the hook
  deliberately never writes a `PASS` artifact from unparseable input. Read the reviewer's actual
  response to understand what went wrong, then either fix the reviewer's prompt/format guidance
  and get a fresh answer (a new review round, not a retry of the same one), or escalate. **Never
  hand-author or patch the review artifact yourself** — if the hook didn't produce it, it isn't a
  valid review artifact, full stop.
- If it validates: proceed to Step 5. The `Result` you act on there is read from this file, which
  by construction matches the hook's SubagentStop capture, not any restatement by you.

## Step 5 — Act on the verdict

- **Result: FAIL** — Do not touch the finding's status beyond where it already is (stay at
  `VERIFYING`). Report the reviewer's objections. Closure is blocked by
  `factory/guards/validate-finding.py` regardless (it requires `Result: PASS`). Either repair
  what was objected to and run a new review round, or stop and escalate — never argue the verdict
  away.
- **Result: EXPERT_REVIEW_REQUIRED** — Set the finding's `Status: EXPERT_REVIEW_REQUIRED` and
  fill its five required fields (`Risk Assessment`, `Expert Review Reason`, `What Is Known`,
  `What Remains Uncertain`, `What An Expert Would Need To Review`) using the reviewer's stated
  remaining risks and objections as the basis. **Stop here.** This is a human decision point per
  `CLAUDE.md` — do not merge, do not close.
- **Result: PASS** — proceed to Step 6.

## Step 6 — VERIFYING → READY_FOR_CLOSURE → CLOSED

Fill in `Review Artifact: factory/reviews/<ID>.md` (relative to the repo root) in the finding's
`## Analyse` section alongside the `Verification Evidence` and `CI Evidence` already written.
Set `Status: READY_FOR_CLOSURE`. Validate:
```
python3 factory/guards/validate-finding.py factory/findings/<ID>.md
python3 factory/guards/run-factory-checks.py
```
Both must pass. If they don't, the guard is telling you something concrete is still missing or
inconsistent (e.g. a CI Evidence field left as a placeholder, or the review artifact's Result
isn't PASS) — fix that specific thing, never work around the guard.

A normal finding (no outstanding `EXPERT_REVIEW_REQUIRED`, `FAIL`, or unresolved high-risk
objection) may then be set to `Status: CLOSED` — this does not require separate human sign-off
beyond the independent review already obtained, per `CLAUDE.md`'s principle that Claude makes
normal technical decisions itself. Re-run both commands to confirm `CLOSED` also validates.

## Step 7 — Merge over the protected default branch

Push the closure commit, wait for the required status check on the new head SHA, and merge only
then:

```
git push origin <finding-branch>
factory/scripts/gh-query.sh check-runs-summary <HEAD-SHA>
factory/scripts/gh-query.sh merge <PR-NUMBER> squash
```

Merge **only** when the required status check for that exact head SHA is
`status=completed conclusion=success`. If the merge call reports `merged: False`, read its
`message` — the protected branch refused the merge for a reason (missing required check, stale
head, insufficient permission). Report that reason; never work around branch protection.

Afterwards verify the real remote state rather than assuming it:
```
git fetch origin
git rev-parse origin/<default-branch>
```
