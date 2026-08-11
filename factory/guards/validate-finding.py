#!/usr/bin/env python3
"""Deterministic, LLM-free guard for factory findings.

Usage:
    python3 factory/guards/validate-finding.py <path-to-finding.md>

Exit code 0 = finding is valid for its status.
Exit code 1 = finding is invalid; details are printed to stderr.

The finding file format is plain text, not YAML/JSON, so it stays readable
without any special tooling:

    # <ID>

    Status: <STATUS>

    ## Analyse

    Root Cause: <text>
    Affected Components: <text>
    ...

See .claude/rules/factory-workflow.md for the full explanation of the rules
enforced here.
"""
import re
import sys
from pathlib import Path

ALLOWED_STATUSES = {
    "OPEN",
    "ANALYZED",
    "IMPLEMENTING",
    "VERIFYING",
    "READY_FOR_CLOSURE",
    "CLOSED",
    "EXPERT_REVIEW_REQUIRED",
}

# Statuses that require the full analysis fields to be filled in.
STATUSES_REQUIRING_ANALYSIS = {
    "ANALYZED",
    "IMPLEMENTING",
    "VERIFYING",
    "READY_FOR_CLOSURE",
    "CLOSED",
}

REQUIRED_ANALYSIS_FIELDS = [
    "Root Cause",
    "Affected Components",
    "Relevant Architecture",
    "Recommended Repair",
    "Regression Test Plan",
    "Central Guard Plan",
    "Expected Blast Radius",
    "Risk Assessment",
]

# EXPERT_REVIEW_REQUIRED is an escalation, not a shortcut around an incomplete
# analysis: it must justify itself with these fields, even though it is
# exempt from REQUIRED_ANALYSIS_FIELDS above.
REQUIRED_EXPERT_REVIEW_FIELDS = [
    "Risk Assessment",
    "Expert Review Reason",
    "What Is Known",
    "What Remains Uncertain",
    "What An Expert Would Need To Review",
]

PLACEHOLDER_VALUES = {
    "",
    "tbd",
    "todo",
    "not yet analyzed",
    "n/a",
}

STATUS_LINE_RE = re.compile(r"^Status:\s*(.*)$", re.IGNORECASE)
ANALYSE_HEADING_RE = re.compile(r"^##\s*Analyse\s*$", re.IGNORECASE)
FIELD_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?):\s*(.*)$")


def parse_finding(text):
    """Parse a finding's raw text into {"status": str|None, "fields": {name: value}}."""
    status = None
    fields = {}
    in_analyse_section = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if status is None:
            match = STATUS_LINE_RE.match(line.strip())
            if match:
                status = match.group(1).strip()
                continue

        if ANALYSE_HEADING_RE.match(line.strip()):
            in_analyse_section = True
            continue

        if in_analyse_section:
            if line.strip().startswith("##"):
                in_analyse_section = False
                continue
            match = FIELD_LINE_RE.match(line.strip())
            if match:
                name, value = match.group(1).strip(), match.group(2).strip()
                fields[name] = value

    return {"status": status, "fields": fields}


def validate_finding(parsed):
    """Return a list of human-readable error strings; empty list means valid."""
    errors = []
    status = parsed["status"]
    fields = parsed["fields"]

    if not status:
        errors.append("Kein 'Status:'-Feld gefunden.")
        return errors

    if status not in ALLOWED_STATUSES:
        errors.append(
            f"Unbekannter Status '{status}'. Erlaubt sind: "
            + ", ".join(sorted(ALLOWED_STATUSES))
        )
        return errors

    if status in STATUSES_REQUIRING_ANALYSIS:
        errors.extend(_check_required_fields(fields, REQUIRED_ANALYSIS_FIELDS))

    if status == "EXPERT_REVIEW_REQUIRED":
        errors.extend(_check_required_fields(fields, REQUIRED_EXPERT_REVIEW_FIELDS))

    return errors


def _check_required_fields(fields, required_fields):
    errors = []
    for field_name in required_fields:
        value = fields.get(field_name)
        if value is None:
            errors.append(f"Pflichtfeld fehlt: '{field_name}'.")
            continue
        if value.strip().lower() in PLACEHOLDER_VALUES:
            errors.append(
                f"Pflichtfeld '{field_name}' ist leer oder ein Platzhalter "
                f"('{value}')."
            )
    return errors


def main(argv):
    if len(argv) != 2:
        print("Usage: validate-finding.py <path-to-finding.md>", file=sys.stderr)
        return 1

    path = Path(argv[1])
    if not path.is_file():
        print(f"Datei nicht gefunden: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    parsed = parse_finding(text)
    errors = validate_finding(parsed)

    if errors:
        print(f"UNGÜLTIG: {path}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"GÜLTIG: {path} (Status: {parsed['status']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
