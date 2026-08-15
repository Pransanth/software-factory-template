#!/usr/bin/env python3
"""Deterministic, LLM-free structural guard for finding closure review artifacts.

Usage:
    python3 factory/guards/validate-review.py <path-to-review.md>

A review artifact is the recorded output of one round of independent
closure review (see .claude/agents/finding-closure-reviewer.md and
.claude/skills/verify-finding/SKILL.md) for one specific finding. This
guard checks only STRUCTURE. It does NOT and CANNOT judge whether the
review's content is actually correct -- whether the fix really addresses
the root cause, whether the regression evidence is convincing, whether
there are unnoticed bypass paths. That judgment is the independent
reviewer's job, not a Python script's.

What is structural here, and why each part exists:

  - **Canonical file name**: `<Finding-ID>.round-<N>.md`, N >= 1, no
    leading zeros. Review rounds are append-only (audit finding F-04): a
    later round never overwrites an earlier one, so a FAIL cannot quietly
    become a PASS. The round number is part of the file name because that
    keeps "which rounds exist" answerable by a directory listing, with no
    separate ledger to keep in sync.
  - **Identity**: the `Finding:` field must equal the finding ID in the
    file name, and that finding must exist under factory/findings/ (audit
    finding F-02). Without this, one finding's PASS could be pointed at by
    another finding.
  - **Scope binding**: `Reviewed Scope Hash` must be a well-formed
    sha256:<hex> value (audit finding F-03). Whether it still MATCHES the
    current repository state is checked at closure time by
    validate-finding.py -- this guard only enforces that the field is
    present and parseable, because a review artifact is a snapshot and
    stays structurally valid after the code moves on.
  - **Provenance**: `Reviewer Agent Type` and `Reviewer Agent ID` are never
    written by the reviewer subagent's own text and never by hand -- they
    are set exclusively by the SubagentStop hook
    (.claude/hooks/subagentstop-write-review.py) from the real Claude Code
    event data for that run. This guard checks that `Reviewer Agent Type`
    is exactly the one valid reviewer agent type; it cannot verify
    `Reviewer Agent ID` against anything (Claude Code exposes no registry
    of agent IDs), but a present, non-placeholder value is still required
    so an artifact missing provenance entirely -- e.g. one written some
    other way than the hook -- is rejected.
  - **No duplicate field lines**: a field may appear at most once. Two
    `Result:` lines would otherwise make "which one counts" depend on
    parser order, which is exactly the kind of ambiguity a security-
    relevant record must not have.

This is deliberately the mirror image of factory/guards/validate-finding.py,
which separately checks (for a finding trying to reach
READY_FOR_CLOSURE/CLOSED) that the referenced review artifact is this
finding's own latest round, that it says PASS, and that its scope hash
still matches -- WITHOUT re-checking the artifact's own field
completeness. That split keeps each script's job narrow and avoids
duplicating checking logic between the two.

Format (plain text, one field per line, same convention as
factory/findings/*.md):

    # <Finding ID>

    Finding: <finding ID, matching a file under factory/findings/>
    Reviewer: <who/what performed the review>
    Reviewer Agent Type: <the SubagentStop event's agent_type, hook-set only>
    Reviewer Agent ID: <the SubagentStop event's agent_id, hook-set only>
    Reviewed Commit: <commit hash / branch, or a description of the diff basis>
    Reviewed Scope Hash: sha256:<64 hex chars>, hook-set only
    Result: PASS | FAIL | EXPERT_REVIEW_REQUIRED
    Root Cause Addressed: <yes/no + justification>
    Regression Evidence Checked: <what was checked, and how>
    Guard Evidence Checked: <what was checked, and how>
    Scope Checked: <was the approved build order scope respected>
    Remaining Risks: <any risks left, or "None identified">
    Findings And Objections: <concrete objections, or "None">

Exit code 0: file is structurally valid.
Exit code 1: at least one required field is missing/a placeholder, a field
             is duplicated, Result is not one of the three allowed values,
             the file name is not canonical, or the identity/provenance/
             scope-hash checks fail.
"""
import re
import sys
from pathlib import Path

REQUIRED_REVIEW_FIELDS = [
    "Finding",
    "Reviewer",
    "Reviewer Agent Type",
    "Reviewer Agent ID",
    "Reviewed Commit",
    "Reviewed Scope Hash",
    "Result",
    "Root Cause Addressed",
    "Regression Evidence Checked",
    "Guard Evidence Checked",
    "Scope Checked",
    "Remaining Risks",
    "Findings And Objections",
]

ALLOWED_RESULTS = {"PASS", "FAIL", "EXPERT_REVIEW_REQUIRED"}

# The only subagent type ever authorized to produce a closure review artifact
# (see .claude/agents/finding-closure-reviewer.md and
# .claude/hooks/subagentstop-write-review.py).
VALID_REVIEWER_AGENT_TYPE = "finding-closure-reviewer"

PLACEHOLDER_VALUES = {
    "",
    "tbd",
    "todo",
    "not yet analyzed",
    "n/a",
}

FIELD_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?):\s*(.*)$")
SCOPE_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# <Finding-ID>.round-<N>.md -- N >= 1, no leading zeros.
ROUND_FILENAME_RE = re.compile(r"^(?P<finding>[A-Za-z0-9._-]+)\.round-(?P<round>[1-9][0-9]*)\.md$")

# factory/guards/validate-review.py -> parents[0]=guards, [1]=factory, [2]=repo root
REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_round_filename(name):
    """Return (finding_id, round_number) or None if the name is not canonical."""
    match = ROUND_FILENAME_RE.match(name)
    if not match:
        return None
    return match.group("finding"), int(match.group("round"))


def parse_review(text):
    """Parse a review artifact into ({field: value}, [duplicate field names])."""
    fields = {}
    duplicates = []
    for raw_line in text.splitlines():
        match = FIELD_LINE_RE.match(raw_line.strip())
        if match:
            name, value = match.group(1).strip(), match.group(2).strip()
            if name in fields:
                duplicates.append(name)
            fields[name] = value
    return fields, duplicates


def validate_review(fields, duplicates, path):
    """Return a list of human-readable error strings; empty list means valid."""
    errors = []

    for field_name in sorted(set(duplicates)):
        errors.append(
            f"Feld '{field_name}' kommt mehrfach vor. Ein Review-Artefakt darf jedes "
            "Feld hoechstens einmal enthalten -- sonst haengt die Bedeutung von der "
            "Parser-Reihenfolge ab."
        )

    for field_name in REQUIRED_REVIEW_FIELDS:
        value = fields.get(field_name)
        if value is None:
            errors.append(f"Pflichtfeld fehlt: '{field_name}'.")
            continue
        if value.strip().lower() in PLACEHOLDER_VALUES:
            errors.append(
                f"Pflichtfeld '{field_name}' ist leer oder ein Platzhalter ('{value}')."
            )

    result_value = fields.get("Result")
    if result_value is not None and result_value.strip().lower() not in PLACEHOLDER_VALUES:
        if result_value.strip() not in ALLOWED_RESULTS:
            errors.append(
                f"'Result' hat ungültigen Wert '{result_value}'. Erlaubt sind: "
                + ", ".join(sorted(ALLOWED_RESULTS))
            )

    reviewer_agent_type_value = fields.get("Reviewer Agent Type")
    if (
        reviewer_agent_type_value is not None
        and reviewer_agent_type_value.strip().lower() not in PLACEHOLDER_VALUES
        and reviewer_agent_type_value.strip() != VALID_REVIEWER_AGENT_TYPE
    ):
        errors.append(
            f"'Reviewer Agent Type' hat ungültigen Wert '{reviewer_agent_type_value}'. "
            f"Erlaubt ist ausschließlich: '{VALID_REVIEWER_AGENT_TYPE}'."
        )

    scope_hash_value = fields.get("Reviewed Scope Hash")
    if (
        scope_hash_value is not None
        and scope_hash_value.strip().lower() not in PLACEHOLDER_VALUES
        and not SCOPE_HASH_RE.match(scope_hash_value.strip())
    ):
        errors.append(
            f"'Reviewed Scope Hash' hat kein gültiges Format ('{scope_hash_value}'). "
            "Erwartet wird 'sha256:' plus 64 Hex-Zeichen, gesetzt vom SubagentStop-Hook."
        )

    # -- canonical file name and identity ---------------------------------
    parsed_name = parse_round_filename(path.name)
    if parsed_name is None:
        errors.append(
            f"Dateiname '{path.name}' ist nicht kanonisch. Erwartet wird "
            "'<Finding-ID>.round-<N>.md' (N >= 1) -- Review-Runden sind append-only."
        )
    finding_value = fields.get("Finding")
    if finding_value is not None and finding_value.strip().lower() not in PLACEHOLDER_VALUES:
        finding_id = finding_value.strip()
        if parsed_name is not None and finding_id != parsed_name[0]:
            errors.append(
                f"'Finding' ({finding_id}) stimmt nicht mit der Finding-ID im Dateinamen "
                f"({parsed_name[0]}) ueberein. Ein Review gehoert genau zu einem Finding."
            )
        referenced_finding = REPO_ROOT / "factory" / "findings" / f"{finding_id}.md"
        if not referenced_finding.is_file():
            errors.append(
                f"'Finding' verweist auf '{finding_id}', aber {referenced_finding} "
                "existiert nicht."
            )

    return errors


def main(argv):
    if len(argv) != 2:
        print("Usage: validate-review.py <path-to-review.md>", file=sys.stderr)
        return 1

    path = Path(argv[1])
    if not path.is_file():
        print(f"Datei nicht gefunden: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    fields, duplicates = parse_review(text)
    errors = validate_review(fields, duplicates, path)

    if errors:
        print(f"UNGÜLTIG: {path}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"GÜLTIG: {path} (Result: {fields.get('Result')})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
