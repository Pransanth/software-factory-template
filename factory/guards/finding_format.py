#!/usr/bin/env python3
"""The single parser for factory findings (audit finding F-18).

Every consumer -- `validate-finding.py`, the hooks, anything that needs to know
a finding's status -- reads through this module. There must not be a second,
subtly different parser: the P0 hard stop (F-09), the build-order requirement
(F-10) and the entire closure gate all hang off the status this returns.

## What was wrong

The previous parser scanned the WHOLE document for `Status:` and `Severity:`,
first match wins. A real finding quotes logs, tickets and configuration --
text that plausibly contains those very words. Observed against the unmodified
guard, with a ticket excerpt above the canonical fields:

    geparster Status:   'OPEN'        (canonical field said IMPLEMENTING)
    geparste Severity:  'P1'          (canonical field said P0)
    P0-Hard-Stop ausgeloest: False

A finding whose real severity is P0 was parsed as P1, and the hard stop that
exists precisely to keep a P0 out of the autonomous pipeline did not fire. A
closed invariant hung on the order of two blocks of text.

Two smaller defects came from the same design: a field value ended at the line
break, so a multi-line Root Cause was silently truncated to its first line --
and the placeholder check therefore only ever saw that first line. A `TBD` on
the second line of a mandatory field passed.

## What was still open afterwards (final re-audit, finding A)

Restricting metadata to the canonical block fixed WHERE a field may be read.
It did not fix what happens when the same field is written TWICE in that block.
The rule was "later occurrences overwrite earlier ones", and it was silent.
Observed against the unmodified parser:

    A1 doppelte Severity -> geparst: 'P1' (kanonisch zuerst: P0)
    A1 P0-Hard-Stop-Fehler: []
    A2 doppelter Status -> geparst: 'OPEN'
    A3 doppeltes Review Artifact -> geparst: 'factory/reviews/DEMO.round-1.md'

`Severity: P0` followed by `Severity: P1` produced P1 and no hard stop at all.
"Last wins" is a decision the parser is not entitled to make: two contradictory
values for a lifecycle or security field mean the document does not say what
the status is, and an unknown status must block, never resolve to whichever
line happens to come last. Duplicates are therefore reported and the guards
turn them into a hard failure -- for EVERY field name, not a curated list of
security-relevant ones, because such a list would be the second, silently
diverging list that F-18 exists to prevent.

## The format

    # <FINDING-ID>                  <- title line

    Status: <STATUS>                <- canonical metadata block:
    Severity: <P0|P1|P2|P3>            everything between the title and the
                                       first `##` heading. Lifecycle metadata
    ## Befund                          is read from HERE AND NOWHERE ELSE.

    ...prose, quoted logs, anything...

    ## Analyse

    Root Cause: first line
      continuation lines are indented
    Affected Components: ...

Rules, deliberately few and mechanical:

1. `Status` and `Severity` are read only from the canonical metadata block. A
   `Status:` line anywhere else is prose and is ignored -- including inside the
   analysis section.
2. Analysis fields are read only inside `## Analyse`.
3. A field value continues onto following INDENTED lines. Indentation is the
   only continuation marker, so there is never a guess about where a value
   ends. The full value -- not just its first line -- is what the placeholder
   check sees.
4. Fenced code blocks (``` or ~~~) are skipped everywhere. A quoted log can
   therefore never introduce a field, in the metadata block or in the analysis.
5. A field name must not occur twice in the same section (case-insensitively).
   A repetition is ambiguity, not an override; the parser reports it and the
   guards refuse the document. Rules 3 and 4 keep this narrow: an indented
   repetition is a continuation line and a repetition inside a fenced block is
   quoted text, so neither is a duplicate.

Backwards compatibility: every existing finding in this repository already has
exactly this shape (title, `Status:`, `Severity:`, then `## Befund`), and none
of them repeats a field name, so they stay valid unchanged. What is no longer
accepted is metadata OUTSIDE the canonical block, and metadata stated twice
INSIDE it -- that is the point of the repair, not a regression.
"""
import re

TITLE_RE = re.compile(r"^#\s+\S")
HEADING_RE = re.compile(r"^#{1,6}\s")
ANALYSE_HEADING_RE = re.compile(r"^##\s*Analyse\s*$", re.IGNORECASE)
FENCE_RE = re.compile(r"^\s*(```|~~~)")

# A field starts at column 0, has a letter-only name and a colon. Continuation
# lines are indented, so `  Status: x` inside a value is part of that value.
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?):\s*(.*)$")

METADATA_KEYS = ("status", "severity")


class FindingFormatError(Exception):
    """The document cannot be parsed into a finding at all."""


def _strip_fenced_blocks(lines):
    """Yield (index, line) for lines outside fenced code blocks."""
    in_fence = False
    fence_marker = None
    for index, line in enumerate(lines):
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
                continue
            if marker == fence_marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        yield index, line


def _collect_fields(pairs):
    """Turn (index, line) pairs into ({name: full value}, [duplicate names]).

    A field name that appears a second time in the same section is recorded as
    a duplicate. It is NOT resolved here, in either direction: the parser has
    no basis for deciding whether the first or the last of two contradictory
    values was meant, and inventing one is how `Severity: P0` followed by
    `Severity: P1` used to turn into a P1 with no hard stop. The mapping still
    keeps the last value so that callers which only report the ambiguity have
    something well-defined in hand -- but every caller in this repository
    treats a non-empty duplicate list as a hard error before it reads any value.

    Comparison is case-insensitive (`Status` and `status` name the same field);
    the reported spelling is the one that occurred first.
    """
    fields = {}
    first_spelling = {}
    duplicates = []
    current_name = None
    current_parts = []

    def flush():
        nonlocal current_name, current_parts
        if current_name is not None:
            key = current_name.strip().lower()
            if key in first_spelling:
                if first_spelling[key] not in duplicates:
                    duplicates.append(first_spelling[key])
            else:
                first_spelling[key] = current_name
            fields[current_name] = "\n".join(current_parts).strip()
        current_name = None
        current_parts = []

    for _, raw_line in pairs:
        line = raw_line.rstrip()
        if not line.strip():
            # A blank line ends a value but does not start a new field.
            flush()
            continue
        if line[:1].isspace():
            if current_name is not None:
                current_parts.append(line.strip())
            continue
        match = FIELD_RE.match(line)
        if match:
            flush()
            current_name = match.group(1).strip()
            current_parts = [match.group(2).strip()]
            continue
        flush()

    flush()
    return fields, duplicates


def split_sections(text):
    """Return (metadata_lines, analysis_lines) as (index, line) pairs.

    A single pass over the fence-stripped document with three states:

        before title -> metadata block -> body

    The metadata block runs from the title line to the first heading and never
    resumes; that is what makes "read the status from here and nowhere else"
    mechanically true. Inside the body, `## Analyse` switches analysis
    collection on and any other heading switches it off again.
    """
    visible = list(_strip_fenced_blocks(text.splitlines()))

    metadata = []
    analysis = []
    seen_title = False
    metadata_closed = False
    in_analysis = False

    for index, line in visible:
        if not seen_title:
            if TITLE_RE.match(line):
                seen_title = True
            continue

        if HEADING_RE.match(line):
            metadata_closed = True
            in_analysis = bool(ANALYSE_HEADING_RE.match(line.strip()))
            continue

        if in_analysis:
            analysis.append((index, line))
        elif not metadata_closed:
            metadata.append((index, line))

    return metadata, analysis


def parse_finding(text):
    """Parse a finding into status, severity, fields and duplicate reports.

    `status` / `severity` come exclusively from the canonical metadata block;
    `fields` exclusively from the `## Analyse` section. Both are None if
    absent, which callers must treat as an error rather than a default.

    `duplicate_metadata_fields` and `duplicate_analysis_fields` list the field
    names stated more than once in their section. A caller must check them
    BEFORE using `status`, `severity` or any value in `fields`: if they are
    non-empty the document is ambiguous about exactly those values, and no
    reading of it is authoritative.
    """
    metadata_pairs, analysis_pairs = split_sections(text)

    metadata_fields, metadata_duplicates = _collect_fields(metadata_pairs)
    analysis_fields, analysis_duplicates = _collect_fields(analysis_pairs)

    status = None
    severity = None
    for name, value in metadata_fields.items():
        lowered = name.strip().lower()
        if lowered == "status":
            status = value.strip()
        elif lowered == "severity":
            severity = value.strip()

    return {
        "status": status,
        "severity": severity,
        "fields": analysis_fields,
        "metadata": metadata_fields,
        "duplicate_metadata_fields": metadata_duplicates,
        "duplicate_analysis_fields": analysis_duplicates,
    }
