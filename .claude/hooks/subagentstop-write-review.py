#!/usr/bin/env python3
"""Claude Code SubagentStop hook: write the closure review artifact.

This is the ONLY place a review artifact under factory/reviews/ is allowed to
come from. It reacts exclusively to the SubagentStop event for the
finding-closure-reviewer subagent (see .claude/agents/finding-closure-reviewer.md)
and writes factory/reviews/<Finding>.md directly from the real Claude Code
event data for that run -- agent_type, agent_id, last_assistant_message --
never from anything the implementing (main) agent claims about the review.

Why this exists: before this hook, the verify-finding skill instructed the
implementing agent to "transcribe verbatim" the reviewer's answer into the
review artifact. That was an instruction, not a technical control -- the
implementing agent had full Edit/Write access and, in principle, could soften
a FAIL to a PASS, or invent a review outright. This hook removes that agent
from the write path entirely: the artifact is produced by Claude Code's own
hook mechanism, from data Claude Code itself supplies about the subagent run,
not by the implementing agent re-typing what it remembers the subagent said.
factory/reviews/ is additionally denied to the Edit/Write tools in
.claude/settings.json so the implementing agent cannot bypass this by hand.

Honest limits, stated plainly (do not oversell this):
  - This is a guard against a normal or accidental agentic bypass. It is NOT
    cryptographic attestation. A local user with filesystem access, or an
    external process writing files directly (bypassing Claude Code's tool
    permission layer entirely, e.g. editing the file from a separate shell),
    is outside what any Claude Code hook or permission rule can prevent.
  - This hook itself does not judge review CONTENT -- it only refuses to
    fabricate or infer a result from unparseable input. Content-level
    structural checks (are all fields present in the artifact, is Result one
    of the three allowed values, does the provenance match the one valid
    reviewer agent type) remain factory/guards/validate-review.py's job, run
    by the canonical runner exactly as before.

Behavior:
  - agent_type != "finding-closure-reviewer": silent no-op, exit 0. (Belt and
    suspenders: the settings.json matcher already restricts which SubagentStop
    events invoke this script at all; this is a second, independent check in
    case the matcher is ever misconfigured.)
  - agent_id missing/empty: provenance is incomplete, no artifact is written,
    exit 2 with a diagnostic on stderr.
  - last_assistant_message does not contain exactly the expected fenced field
    block, or the block is missing/placeholder fields, or Result is not
    exactly one of PASS / FAIL / EXPERT_REVIEW_REQUIRED, or Finding is not a
    safe filename token: malformed, no artifact is written (specifically: no
    PASS is ever produced from unparseable input), exit 2 with diagnostics.
  - Otherwise: factory/reviews/<Finding>.md is written (overwriting any prior
    round for the same finding, matching the existing verify-finding workflow)
    with the reviewer's 10 fields plus two fields this hook alone sets:
    "Reviewer Agent Type" and "Reviewer Agent ID", taken from the event data.
    Exit 0.

See https://code.claude.com/docs/en/hooks.md for the SubagentStop hook
contract (agent_type, agent_id, last_assistant_message are provided directly
in the JSON payload on stdin; SubagentStop cannot block the subagent, which
has already finished -- exit 2 here only surfaces a diagnostic, it does not
undo the subagent run).
"""
import json
import os
import re
import sys
from pathlib import Path

REQUIRED_LLM_FIELDS = [
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

ALLOWED_RESULTS = {"PASS", "FAIL", "EXPERT_REVIEW_REQUIRED"}

PLACEHOLDER_VALUES = {
    "",
    "tbd",
    "todo",
    "not yet analyzed",
    "n/a",
}

EXPECTED_AGENT_TYPE = "finding-closure-reviewer"

FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
FIELD_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?):\s*(.*)$")
FINDING_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def project_root():
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root)
    # Fallback for manual/local runs: this file lives at <root>/.claude/hooks/.
    return Path(__file__).resolve().parents[2]


def extract_last_fenced_block(text):
    matches = list(FENCE_RE.finditer(text or ""))
    if not matches:
        return None
    return matches[-1].group(1)


def parse_fields(block_text):
    fields = {}
    for raw_line in block_text.splitlines():
        match = FIELD_LINE_RE.match(raw_line.strip())
        if match:
            name, value = match.group(1).strip(), match.group(2).strip()
            fields[name] = value
    return fields


def validate_fields(fields):
    """Return a list of human-readable error strings; empty list means valid."""
    errors = []

    for field_name in REQUIRED_LLM_FIELDS:
        value = fields.get(field_name)
        if value is None or value.strip().lower() in PLACEHOLDER_VALUES:
            errors.append(f"Pflichtfeld fehlt oder ist ein Platzhalter: '{field_name}'.")

    result_value = fields.get("Result")
    if (
        result_value is not None
        and result_value.strip().lower() not in PLACEHOLDER_VALUES
        and result_value.strip() not in ALLOWED_RESULTS
    ):
        errors.append(
            f"'Result' hat ungueltigen Wert '{result_value}'. Erlaubt sind exakt: "
            + ", ".join(sorted(ALLOWED_RESULTS))
        )

    finding_value = fields.get("Finding", "").strip()
    if finding_value and (
        not FINDING_TOKEN_RE.match(finding_value)
        or ".." in finding_value
        or finding_value in (".", "..")
    ):
        errors.append(f"'Finding' ist kein sicherer Dateiname-Token: '{finding_value}'.")

    return errors


def build_artifact_text(fields, agent_type, agent_id):
    lines = [
        f"# {fields['Finding']}",
        "",
        f"Finding: {fields['Finding']}",
        f"Reviewer: {fields['Reviewer']}",
        f"Reviewer Agent Type: {agent_type}",
        f"Reviewer Agent ID: {agent_id}",
        f"Reviewed Commit: {fields['Reviewed Commit']}",
        f"Result: {fields['Result']}",
        f"Root Cause Addressed: {fields['Root Cause Addressed']}",
        f"Regression Evidence Checked: {fields['Regression Evidence Checked']}",
        f"Guard Evidence Checked: {fields['Guard Evidence Checked']}",
        f"Scope Checked: {fields['Scope Checked']}",
        f"Remaining Risks: {fields['Remaining Risks']}",
        f"Findings And Objections: {fields['Findings And Objections']}",
        "",
    ]
    return "\n".join(lines)


def fail(message):
    print(
        "SubagentStop-Hook (finding-closure-reviewer): kein Review-Artefakt geschrieben.\n"
        + message,
        file=sys.stderr,
    )
    return 2


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        hook_input = {}

    agent_type = hook_input.get("agent_type")
    if agent_type != EXPECTED_AGENT_TYPE:
        # Not our subagent -- silent no-op. Defense in depth alongside the
        # settings.json matcher; this hook must never touch factory/reviews/
        # for any other agent type.
        return 0

    agent_id = hook_input.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        return fail(
            "'agent_id' fehlt oder ist leer im SubagentStop-Event. Provenienz ist "
            "unvollstaendig -- ohne agent_id wird kein Artefakt geschrieben."
        )

    last_message = hook_input.get("last_assistant_message")
    block_text = extract_last_fenced_block(last_message)
    if block_text is None:
        return fail(
            "Kein Triple-Backtick-Fenced-Block in 'last_assistant_message' gefunden. "
            "Die Antwort des Reviewers ist nicht maschinenlesbar."
        )

    fields = parse_fields(block_text)
    errors = validate_fields(fields)
    if errors:
        return fail("Malformed Reviewer-Ausgabe:\n" + "\n".join(f"  - {e}" for e in errors))

    root = project_root()
    review_dir = root / "factory" / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_dir / f"{fields['Finding']}.md"
    review_path.write_text(build_artifact_text(fields, agent_type, agent_id), encoding="utf-8")

    print(
        f"SubagentStop-Hook: Review-Artefakt geschrieben: {review_path} "
        f"(Result: {fields['Result']}, Reviewer Agent ID: {agent_id})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
