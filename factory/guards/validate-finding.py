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
    Severity: <P0|P1|P2|P3>

    ## Analyse

    Root Cause: <text>
    Affected Components: <text>
    ...
    Verification Evidence: <text, required only for READY_FOR_CLOSURE/CLOSED>
    CI Evidence: <text, required only for READY_FOR_CLOSURE/CLOSED>
    Review Artifact: <factory/reviews/<ID>.round-<N>.md, required only for
                       READY_FOR_CLOSURE/CLOSED>

See .claude/rules/factory-workflow.md for the full explanation of the rules
enforced here.

## Severity gate (audit finding F-09)

`Severity` is required from ANALYZED onwards. `Severity: P0` -- an acute,
actively exploited finding -- must never run through the normal autonomous
implement/verify/close pipeline: it is allowed only in OPEN, ANALYZED or
EXPERT_REVIEW_REQUIRED. Anything further is a hard guard failure. Before
this, "a P0 stops the factory" was a sentence in CLAUDE.md that no code
enforced.

## Closure gate (READY_FOR_CLOSURE / CLOSED)

This guard does NOT judge whether a fix is actually correct or secure --
that is the independent reviewer's job
(.claude/agents/finding-closure-reviewer.md). What it checks is narrower,
purely structural, and deterministic: is this finding closing on ITS OWN,
LATEST, PASSING review of EXACTLY THIS code state?

Concretely, `Review Artifact` must satisfy all of:

  1. It is spelled exactly `factory/reviews/<ID>.round-<N>.md`, where <ID>
     is this finding file's own name. Absolute paths, `../` traversal and
     any other directory are rejected (F-01).
  2. Its resolved real path is inside the resolved real
     factory/reviews/ directory, so a symlink cannot point out of it (F-01).
  3. It passes factory/guards/validate-review.py in full -- not merely
     "contains a Result: PASS line" (F-01). Before this repair, ANY file
     containing that line was accepted, including a build order the
     implementing agent wrote itself.
  4. Its `Finding:` field names this finding (F-02). One finding's PASS
     can no longer close another.
  5. It is the HIGHEST round that exists for this finding, and rounds 1..N
     are all present -- an older PASS cannot be cherry-picked past a newer
     FAIL, and a FAIL round cannot be made to disappear (F-04).
  6. Its `Result` is PASS.
  7. Its `Reviewed Scope Hash` equals the repository's current scope hash
     (F-03), so a PASS stops being valid the moment the reviewed code
     changes. See factory/guards/scope_hash.py for what is in scope and,
     just as importantly, what deliberately is not.
  8. No earlier round carries the SAME scope hash with a non-PASS result
     (F-04). FAIL -> change -> new review -> PASS is legitimate; FAIL ->
     ask again against identical code -> PASS is not.

If the scope hash cannot be computed at all, closure is refused. An
unknown code state must block a closure, never silently pass one.
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scope_hash import ScopeHashError, compute_scope_hash  # noqa: E402

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

# CLOSED must satisfy everything READY_FOR_CLOSURE does -- it is a superset,
# not a separate rule set -- so both statuses share this same set.
STATUSES_REQUIRING_CLOSURE_EVIDENCE = {
    "READY_FOR_CLOSURE",
    "CLOSED",
}

REQUIRED_CLOSURE_FIELDS = [
    "Verification Evidence",
    "CI Evidence",
    "Review Artifact",
]

ALLOWED_SEVERITIES = ["P0", "P1", "P2", "P3"]

# Severity must be declared before any work is planned on a finding.
STATUSES_REQUIRING_SEVERITY = STATUSES_REQUIRING_ANALYSIS | {"EXPERT_REVIEW_REQUIRED"}

# A P0 is an acute, actively exploited finding. It is never worked through
# autonomously -- it may be recorded, analysed and escalated, nothing more.
STATUSES_ALLOWED_FOR_P0 = {"OPEN", "ANALYZED", "EXPERT_REVIEW_REQUIRED"}

PLACEHOLDER_VALUES = {
    "",
    "tbd",
    "todo",
    "not yet analyzed",
    "n/a",
}

STATUS_LINE_RE = re.compile(r"^Status:\s*(.*)$", re.IGNORECASE)
SEVERITY_LINE_RE = re.compile(r"^Severity:\s*(.*)$", re.IGNORECASE)
ANALYSE_HEADING_RE = re.compile(r"^##\s*Analyse\s*$", re.IGNORECASE)
FIELD_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?):\s*(.*)$")
REVIEW_RESULT_LINE_RE = re.compile(r"^Result:\s*(.*)$")
REVIEW_FINDING_LINE_RE = re.compile(r"^Finding:\s*(.*)$")
REVIEW_SCOPE_HASH_LINE_RE = re.compile(r"^Reviewed Scope Hash:\s*(.*)$")

ROUND_FILENAME_RE = re.compile(r"^(?P<finding>[A-Za-z0-9._-]+)\.round-(?P<round>[1-9][0-9]*)\.md$")

# factory/guards/validate-finding.py -> parents[0]=guards, [1]=factory, [2]=repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWS_DIR = REPO_ROOT / "factory" / "reviews"
REVIEW_GUARD = Path(__file__).resolve().parent / "validate-review.py"


def parse_finding(text):
    """Parse a finding's raw text into {"status", "severity", "fields"}."""
    status = None
    severity = None
    fields = {}
    in_analyse_section = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if status is None:
            match = STATUS_LINE_RE.match(stripped)
            if match:
                status = match.group(1).strip()
                continue

        if severity is None:
            match = SEVERITY_LINE_RE.match(stripped)
            if match:
                severity = match.group(1).strip()
                continue

        if ANALYSE_HEADING_RE.match(stripped):
            in_analyse_section = True
            continue

        if in_analyse_section:
            if stripped.startswith("##"):
                in_analyse_section = False
                continue
            match = FIELD_LINE_RE.match(stripped)
            if match:
                name, value = match.group(1).strip(), match.group(2).strip()
                fields[name] = value

    return {"status": status, "severity": severity, "fields": fields}


def validate_finding(parsed, finding_path):
    """Return a list of human-readable error strings; empty list means valid."""
    errors = []
    status = parsed["status"]
    severity = parsed["severity"]
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

    errors.extend(_check_severity(status, severity))

    if status in STATUSES_REQUIRING_ANALYSIS:
        errors.extend(_check_required_fields(fields, REQUIRED_ANALYSIS_FIELDS))

    if status == "EXPERT_REVIEW_REQUIRED":
        errors.extend(_check_required_fields(fields, REQUIRED_EXPERT_REVIEW_FIELDS))

    if status in STATUSES_REQUIRING_CLOSURE_EVIDENCE:
        errors.extend(_check_required_fields(fields, REQUIRED_CLOSURE_FIELDS))
        errors.extend(_check_review_artifact(fields, finding_path))

    return errors


def _check_severity(status, severity):
    """Severity presence, validity, and the P0 hard stop."""
    errors = []
    normalized = (severity or "").strip().upper()

    if status in STATUSES_REQUIRING_SEVERITY:
        if not normalized or normalized.lower() in PLACEHOLDER_VALUES:
            errors.append(
                "Pflichtfeld 'Severity' fehlt oder ist ein Platzhalter. Erlaubt sind: "
                + ", ".join(ALLOWED_SEVERITIES)
            )
            return errors

    if normalized and normalized.lower() not in PLACEHOLDER_VALUES:
        if normalized not in ALLOWED_SEVERITIES:
            errors.append(
                f"Unbekannte 'Severity' '{severity}'. Erlaubt sind: "
                + ", ".join(ALLOWED_SEVERITIES)
            )
            return errors

        if normalized == "P0" and status not in STATUSES_ALLOWED_FOR_P0:
            errors.append(
                f"Severity P0 mit Status '{status}': ein P0 wird nicht autonom "
                "durchgearbeitet. Erlaubt sind fuer P0 ausschliesslich: "
                + ", ".join(sorted(STATUSES_ALLOWED_FOR_P0))
                + ". Befund festhalten, Sofortlage beschreiben, Menschen einbeziehen "
                "(siehe CLAUDE.md, 'Wann die Factory wirklich stoppt')."
            )

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


def _read_review_field(path, line_re):
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = line_re.match(raw_line.strip())
        if match:
            return match.group(1).strip()
    return None


def _existing_rounds(finding_id):
    """{round_number: path} for every canonical round file of this finding."""
    rounds = {}
    if not REVIEWS_DIR.is_dir():
        return rounds
    for candidate in REVIEWS_DIR.iterdir():
        match = ROUND_FILENAME_RE.match(candidate.name)
        if match and match.group("finding") == finding_id:
            rounds[int(match.group("round"))] = candidate
    return rounds


def _check_review_artifact(fields, finding_path):
    """Closure-gate cross-check: is this the finding's own latest passing
    review, of exactly this code state? See the module docstring for the
    eight conditions and the audit findings each one closes."""
    errors = []
    value = fields.get("Review Artifact")
    if value is None or value.strip().lower() in PLACEHOLDER_VALUES:
        return errors  # already reported by _check_required_fields above

    value = value.strip()
    finding_id = finding_path.stem
    expected_prefix = f"factory/reviews/{finding_id}.round-"

    # 1. canonical spelling, bound to THIS finding
    if not value.startswith(expected_prefix) or not value.endswith(".md"):
        errors.append(
            f"'Review Artifact' ist '{value}'. Erlaubt ist ausschliesslich das "
            f"kanonische Review-Artefakt dieses Findings: "
            f"'{expected_prefix}<N>.md'."
        )
        return errors

    round_match = ROUND_FILENAME_RE.match(value[len("factory/reviews/") :])
    if round_match is None or round_match.group("finding") != finding_id:
        errors.append(
            f"'Review Artifact' ist '{value}' und damit kein kanonischer "
            f"Rundenname '{expected_prefix}<N>.md'."
        )
        return errors
    referenced_round = int(round_match.group("round"))

    review_path = REPO_ROOT / value

    # 2. real path must stay inside factory/reviews/ (no symlink escape)
    try:
        resolved_reviews_dir = REVIEWS_DIR.resolve(strict=True)
        resolved_review = review_path.resolve(strict=True)
    except (OSError, RuntimeError):
        errors.append(
            f"'Review Artifact' verweist auf '{value}', aber dort existiert keine "
            f"aufloesbare Datei ({review_path})."
        )
        return errors

    if not resolved_review.is_file():
        errors.append(f"'Review Artifact' '{value}' ist keine regulaere Datei.")
        return errors

    if resolved_reviews_dir not in resolved_review.parents:
        errors.append(
            f"'Review Artifact' '{value}' zeigt nach Aufloesung auf "
            f"'{resolved_review}' und damit aus {resolved_reviews_dir} heraus "
            "(Symlink- oder Traversal-Ausbruch)."
        )
        return errors

    # 3. the artifact must pass the review guard itself
    guard_result = subprocess.run(
        [sys.executable, str(REVIEW_GUARD), str(review_path)],
        capture_output=True,
        text=True,
    )
    if guard_result.returncode != 0:
        errors.append(
            f"'Review Artifact' '{value}' besteht validate-review.py nicht: "
            + " | ".join(
                line.strip()
                for line in (guard_result.stdout + guard_result.stderr).splitlines()
                if line.strip()
            )
        )
        return errors

    # 4. identity
    review_finding = _read_review_field(review_path, REVIEW_FINDING_LINE_RE)
    if review_finding != finding_id:
        errors.append(
            f"Review-Artefakt '{value}' gehoert laut seinem 'Finding'-Feld zu "
            f"'{review_finding}', nicht zu '{finding_id}'."
        )
        return errors

    # 5. latest round, and no round missing
    rounds = _existing_rounds(finding_id)
    if rounds:
        highest = max(rounds)
        if referenced_round != highest:
            errors.append(
                f"'Review Artifact' verweist auf Runde {referenced_round}, aber die "
                f"neueste vorhandene Runde ist {highest} "
                f"({rounds[highest].name}). Eine aeltere Runde schliesst nicht."
            )
            return errors
        missing = [n for n in range(1, highest + 1) if n not in rounds]
        if missing:
            errors.append(
                "Review-Runden sind nicht luekenlos: es fehlen "
                + ", ".join(f"round-{n}" for n in missing)
                + ". Review-Runden sind append-only und werden nicht geloescht."
            )
            return errors

    # 6. verdict
    result_value = _read_review_field(review_path, REVIEW_RESULT_LINE_RE)
    if result_value != "PASS":
        errors.append(
            f"Review-Artefakt '{value}' hat Result '{result_value}' -- "
            "erforderlich fuer Closure ist 'PASS'."
        )
        return errors

    # 7. scope binding
    try:
        current_hash, _ = compute_scope_hash(REPO_ROOT)
    except ScopeHashError as exc:
        errors.append(
            "Scope-Hash des Repositories ist nicht bestimmbar, deshalb ist die "
            f"Bindung des Reviews nicht pruefbar: {exc}"
        )
        return errors

    reviewed_hash = _read_review_field(review_path, REVIEW_SCOPE_HASH_LINE_RE)
    if reviewed_hash != current_hash:
        errors.append(
            f"Scope-Hash-Abweichung: Review-Artefakt '{value}' wurde gegen "
            f"{reviewed_hash} erstellt, der aktuelle Stand ist {current_hash}. "
            "Der geprüfte Codezustand ist nicht mehr der aktuelle -- ein neuer "
            "Review-Durchgang ist noetig."
        )
        return errors

    # 8. no non-PASS round for the identical code state
    for number in sorted(rounds):
        if number >= referenced_round:
            continue
        earlier = rounds[number]
        earlier_result = _read_review_field(earlier, REVIEW_RESULT_LINE_RE)
        earlier_hash = _read_review_field(earlier, REVIEW_SCOPE_HASH_LINE_RE)
        if earlier_result != "PASS" and earlier_hash == reviewed_hash:
            errors.append(
                f"Runde {number} ({earlier.name}) hatte Result '{earlier_result}' fuer "
                f"exakt denselben Codezustand ({reviewed_hash}). Ein erneuter Review "
                "ohne zwischenzeitliche Aenderung ergibt kein gueltiges PASS."
            )
            return errors

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
    errors = validate_finding(parsed, path)

    if errors:
        print(f"UNGÜLTIG: {path}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"GÜLTIG: {path} (Status: {parsed['status']}, Severity: {parsed['severity']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
