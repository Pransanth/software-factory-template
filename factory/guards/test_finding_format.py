#!/usr/bin/env python3
"""Regression tests for the canonical finding format (audit finding F-18).

Observed against the unmodified parser, with a ticket excerpt quoted above the
canonical fields:

    geparster Status:   'OPEN'        (canonical field said IMPLEMENTING)
    geparste Severity:  'P1'          (canonical field said P0)
    P0-Hard-Stop ausgeloest: False

    Root Cause geparst: 'Der Dienst laeuft in einen Deadlock, weil zwei Locks in'
    (the remaining two lines of the value were silently dropped)

    Risk Assessment geparst: 'Erste Zeile klingt nach Inhalt.'
    Platzhalter erkannt: False        (the TBD on line 2 was invisible)

The tests below pin each of those, plus the invariant that matters most: a
quoted `Severity: P1` must not be able to switch off the P0 hard stop from
audit finding F-09.
"""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

GUARDS_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUARDS_DIR.parents[1]


def _load(filename, name):
    spec = importlib.util.spec_from_file_location(name, GUARDS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ff = _load("finding_format.py", "finding_format_under_test")
vf = _load("validate-finding.py", "validate_finding_under_test")


class CanonicalMetadataBlockTests(unittest.TestCase):
    def test_quoted_status_does_not_replace_the_canonical_status(self):
        text = """# T

Status: OPEN
Severity: P2

## Befund

Aus dem Ticketsystem uebernommen:

    Status: CLOSED
    Severity: P0

Das Ticket war voreilig geschlossen worden.
"""
        parsed = ff.parse_finding(text)
        self.assertEqual(parsed["status"], "OPEN")
        self.assertEqual(parsed["severity"], "P2")

    def test_quoted_severity_p0_does_not_raise_a_p1_finding(self):
        text = """# T

Status: IMPLEMENTING
Severity: P1

## Befund

Der Monitoring-Alarm meldete:

    Severity: P0
    Status: OPEN
"""
        parsed = ff.parse_finding(text)
        self.assertEqual(parsed["severity"], "P1")
        self.assertEqual(
            vf._check_severity(parsed["status"], parsed["severity"]),
            [],
            "ein zitiertes P0 darf den Hard-Stop nicht ausloesen",
        )

    def test_quoted_severity_p1_does_not_switch_off_the_p0_hard_stop(self):
        """The dangerous direction: a real P0 must not be readable as a P1."""
        text = """# T

Status: IMPLEMENTING
Severity: P0

## Befund

Aus dem Ticket kopiert, wo es zunaechst niedriger eingestuft war:

    Severity: P1
"""
        parsed = ff.parse_finding(text)
        self.assertEqual(parsed["severity"], "P0")
        errors = vf._check_severity(parsed["status"], parsed["severity"])
        self.assertTrue(errors, "der P0-Hard-Stop hat nicht ausgeloest")
        self.assertIn("P0", errors[0])

    def test_fenced_block_in_the_metadata_area_cannot_set_metadata(self):
        text = """# T

```
Status: CLOSED
Severity: P0
```

Status: OPEN
Severity: P3
"""
        parsed = ff.parse_finding(text)
        self.assertEqual(parsed["status"], "OPEN")
        self.assertEqual(parsed["severity"], "P3")

    def test_metadata_outside_the_canonical_block_is_not_read(self):
        """Not a silent default: no canonical block means no status at all,
        which the validator reports as an error rather than guessing."""
        text = """# T

## Befund

Status: CLOSED
Severity: P0
"""
        parsed = ff.parse_finding(text)
        self.assertIsNone(parsed["status"])
        self.assertIsNone(parsed["severity"])
        errors = vf.validate_finding(parsed, Path("factory/findings/T.md"))
        self.assertTrue(errors)
        self.assertIn("Status", errors[0])

    def test_status_inside_the_analysis_section_is_not_read(self):
        text = """# T

Status: OPEN
Severity: P2

## Analyse

Root Cause: Der Dienst meldete Status: CLOSED, was irrefuehrend war.
"""
        parsed = ff.parse_finding(text)
        self.assertEqual(parsed["status"], "OPEN")


class MultiLineFieldTests(unittest.TestCase):
    def test_multi_line_root_cause_is_read_completely(self):
        text = """# T

Status: ANALYZED
Severity: P2

## Analyse

Root Cause: Der Dienst laeuft in einen Deadlock, weil zwei Locks in
  unterschiedlicher Reihenfolge genommen werden. Der zweite Teil dieser
  Erklaerung ist zwingend erforderlich.
Affected Components: api
"""
        parsed = ff.parse_finding(text)
        value = parsed["fields"]["Root Cause"]
        self.assertIn("Deadlock", value)
        self.assertIn("Reihenfolge", value)
        self.assertIn("zwingend erforderlich", value)
        self.assertEqual(parsed["fields"]["Affected Components"], "api")

    def test_multi_line_evidence_is_read_completely(self):
        text = """# T

Status: ANALYZED
Severity: P2

## Analyse

Verification Evidence: Erster Lauf gruen.
  Zweiter Lauf ebenfalls gruen, inklusive der Guard-Pruefung.
  Dritter Lauf gegen die externe CI.
"""
        parsed = ff.parse_finding(text)
        value = parsed["fields"]["Verification Evidence"]
        self.assertIn("Erster Lauf", value)
        self.assertIn("Zweiter Lauf", value)
        self.assertIn("Dritter Lauf", value)

    def test_placeholder_inside_a_multi_line_field_is_detected(self):
        text = """# T

Status: ANALYZED
Severity: P2

## Analyse

Risk Assessment: Erste Zeile klingt nach Inhalt.
  TBD
"""
        parsed = ff.parse_finding(text)
        errors = vf._check_required_fields(parsed["fields"], ["Risk Assessment"])
        self.assertTrue(errors, "Platzhalter in Zeile 2 wurde nicht erkannt")
        self.assertIn("Zeile 2", errors[0])

    def test_a_fully_filled_multi_line_field_passes(self):
        text = """# T

Status: ANALYZED
Severity: P2

## Analyse

Risk Assessment: Erste Zeile mit Inhalt.
  Zweite Zeile mit weiterem Inhalt.
"""
        parsed = ff.parse_finding(text)
        self.assertEqual(
            vf._check_required_fields(parsed["fields"], ["Risk Assessment"]), []
        )

    def test_blank_line_ends_a_value(self):
        text = """# T

Status: ANALYZED
Severity: P2

## Analyse

Root Cause: Nur diese Zeile.

  Diese eingerueckte Zeile steht nach einer Leerzeile und gehoert nicht dazu.
"""
        parsed = ff.parse_finding(text)
        self.assertEqual(parsed["fields"]["Root Cause"], "Nur diese Zeile.")


class BackwardsCompatibilityTests(unittest.TestCase):
    """Every finding already in this repository must stay valid unchanged."""

    def _findings(self):
        return sorted((REPO_ROOT / "factory" / "findings").glob("*.md"))

    def test_example_finding_stays_valid(self):
        example = REPO_ROOT / "factory" / "findings" / "EXAMPLE-FINDING.md"
        self.assertTrue(example.is_file())
        parsed = ff.parse_finding(example.read_text(encoding="utf-8"))
        self.assertIsNotNone(parsed["status"])
        self.assertEqual(
            vf.validate_finding(parsed, example),
            [],
            "das mitgelieferte Beispiel-Finding ist nicht mehr gueltig",
        )

    def test_every_existing_finding_still_parses_with_status_and_severity(self):
        for path in self._findings():
            with self.subTest(finding=path.name):
                parsed = ff.parse_finding(path.read_text(encoding="utf-8"))
                self.assertIsNotNone(
                    parsed["status"], f"{path.name} hat keinen lesbaren Status mehr"
                )

    def test_every_existing_finding_still_passes_its_guard(self):
        guard = REPO_ROOT / "factory" / "guards" / "validate-finding.py"
        for path in self._findings():
            with self.subTest(finding=path.name):
                result = subprocess.run(
                    [sys.executable, str(guard), str(path)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{path.name} ist nicht mehr gueltig: "
                    f"{result.stdout}{result.stderr}",
                )


class SingleParserTests(unittest.TestCase):
    """There must not be a second, subtly different finding parser."""

    def test_validate_finding_does_not_define_its_own_parser(self):
        source = (GUARDS_DIR / "validate-finding.py").read_text(encoding="utf-8")
        self.assertIn("from finding_format import parse_finding", source)
        self.assertNotIn("def parse_finding(", source)

    def test_build_order_guard_reads_status_through_the_shared_parser(self):
        source = (GUARDS_DIR / "validate-build-order.py").read_text(encoding="utf-8")
        self.assertIn("from finding_format import parse_finding", source)
        self.assertNotIn("STATUS_LINE_RE = ", source)

    def test_build_order_lifecycle_uses_the_canonical_status(self):
        """A quoted `Status: OPEN` must not switch off the evidence
        requirement that the finding's real status implies."""
        vbo = _load("validate-build-order.py", "validate_build_order_under_test")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            finding = Path(tmp) / "F.md"
            finding.write_text(
                "# F\n\nStatus: VERIFYING\nSeverity: P2\n\n"
                "## Befund\n\nDas Ticket sagte:\n\n    Status: OPEN\n",
                encoding="utf-8",
            )
            self.assertEqual(vbo.read_finding_status(finding), "VERIFYING")



class DuplicateFieldTests(unittest.TestCase):
    """Ambiguous metadata fails deterministically (final re-audit, finding A).

    Observed against the unmodified parser, which resolved a repeated field by
    "last wins" and said nothing:

        A1 doppelte Severity -> geparst: 'P1' (kanonisch zuerst: P0)
        A1 P0-Hard-Stop-Fehler: []
        A2 doppelter Status -> geparst: 'OPEN'
        A3 doppeltes Review Artifact -> geparst: 'factory/reviews/DEMO.round-1.md'

    A document that states `Severity: P0` and `Severity: P1` does not have a
    severity, and the parser is not entitled to pick one. `Status`, `Severity`
    and `Review Artifact` are the cases where that matters most, but the rule
    covers every field name: a curated list of security-relevant fields would
    be a second list to keep in step, which is what F-18 removed.
    """

    ANALYSIS = "\n".join(
        f"{name}: belastbarer Inhalt fuer {name}, mehr als ein Platzhalter."
        for name in vf.REQUIRED_ANALYSIS_FIELDS
    )
    DUMMY_PATH = Path("factory/findings/DUP.md")

    def _finding(self, metadata, analysis=None):
        return (
            "# DUP\n\n"
            + metadata
            + "\n\n## Analyse\n\n"
            + (self.ANALYSIS if analysis is None else analysis)
            + "\n"
        )

    def test_duplicate_severity_is_reported_instead_of_last_wins(self):
        parsed = ff.parse_finding(
            self._finding("Status: ANALYZED\nSeverity: P0\nSeverity: P1")
        )
        self.assertEqual(parsed["duplicate_metadata_fields"], ["Severity"])

    def test_duplicate_severity_cannot_silently_downgrade_a_p0(self):
        parsed = ff.parse_finding(
            self._finding("Status: IMPLEMENTING\nSeverity: P0\nSeverity: P1")
        )
        errors = vf.validate_finding(parsed, self.DUMMY_PATH)
        self.assertNotEqual(
            errors,
            [],
            "Zwei widersprechende Severity-Zeilen wurden stillschweigend "
            "aufgeloest -- genau die Luecke des finalen Re-Audits",
        )
        self.assertTrue(
            any("Severity" in error and "mehrfach" in error for error in errors),
            f"Die Mehrdeutigkeit wird nicht benannt: {errors}",
        )

    def test_duplicate_status_is_rejected(self):
        parsed = ff.parse_finding(
            self._finding("Status: CLOSED\nStatus: OPEN\nSeverity: P2")
        )
        self.assertEqual(parsed["duplicate_metadata_fields"], ["Status"])
        errors = vf.validate_finding(parsed, self.DUMMY_PATH)
        self.assertTrue(any("Status" in error for error in errors), errors)

    def test_duplicate_review_artifact_is_rejected(self):
        analysis = (
            self.ANALYSIS
            + "\nVerification Evidence: alle Tests gruen.\n"
            + "CI Evidence: Actions-Run 1234567890.\n"
            + "Review Artifact: factory/reviews/DUP.round-9.md\n"
            + "Review Artifact: factory/reviews/DUP.round-1.md\n"
        )
        parsed = ff.parse_finding(
            self._finding("Status: CLOSED\nSeverity: P2", analysis)
        )
        self.assertEqual(parsed["duplicate_analysis_fields"], ["Review Artifact"])
        errors = vf.validate_finding(parsed, self.DUMMY_PATH)
        self.assertTrue(
            any("Review Artifact" in error for error in errors),
            f"Ein zweimal genanntes Review-Artefakt wurde aufgeloest: {errors}",
        )

    def test_duplicate_detection_is_case_insensitive(self):
        parsed = ff.parse_finding(
            self._finding("Status: ANALYZED\nSeverity: P0\nseverity: P1")
        )
        self.assertEqual(parsed["duplicate_metadata_fields"], ["Severity"])

    def test_an_ambiguous_finding_is_not_judged_any_further(self):
        """The guard must stop, not report ambiguity plus a verdict derived
        from one arbitrarily chosen value."""
        parsed = ff.parse_finding("# DUP\n\nStatus: CLOSED\nStatus: OPEN\n")
        errors = vf.validate_finding(parsed, self.DUMMY_PATH)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("mehrfach", errors[0])

    def test_an_indented_repetition_stays_a_continuation_line(self):
        parsed = ff.parse_finding(
            self._finding("Status: ANALYZED\nSeverity: P1\n  Severity: P0 laut Ticket")
        )
        self.assertEqual(parsed["duplicate_metadata_fields"], [])
        self.assertEqual(parsed["severity"], "P1\nSeverity: P0 laut Ticket")

    def test_a_repetition_inside_a_fenced_block_is_not_a_duplicate(self):
        text = (
            "# DUP\n\nStatus: ANALYZED\nSeverity: P1\n\n## Befund\n\n"
            "```\nSeverity: P0\nSeverity: P3\n```\n\n## Analyse\n\n"
            + self.ANALYSIS
            + "\n"
        )
        parsed = ff.parse_finding(text)
        self.assertEqual(parsed["duplicate_metadata_fields"], [])
        self.assertEqual(parsed["severity"], "P1")

    def test_no_existing_finding_repeats_a_field(self):
        """Backwards compatibility: the new rule must not invalidate history."""
        for path in sorted((REPO_ROOT / "factory" / "findings").glob("*.md")):
            with self.subTest(finding=path.name):
                parsed = ff.parse_finding(path.read_text(encoding="utf-8"))
                self.assertEqual(parsed["duplicate_metadata_fields"], [])
                self.assertEqual(parsed["duplicate_analysis_fields"], [])

    def test_the_build_order_guard_refuses_an_ambiguous_status(self):
        """The evidence lifecycle is driven by the finding's status, so an
        ambiguous status must block the build order too -- not fall through to
        whichever value came last."""
        vbo = _load("validate-build-order.py", "validate_build_order_ambiguity")
        import tempfile

        sections = "".join(
            f"## {name}\n\nBelastbarer Inhalt fuer den Abschnitt {name}, "
            "deutlich laenger als die Platzhaltergrenze.\n\n"
            "```\n$ echo Lauf\nLauf\n```\n\n"
            for name in vbo.REQUIRED_SECTIONS
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "factory" / "findings").mkdir(parents=True)
            (root / "factory" / "build-orders").mkdir(parents=True)
            (root / "factory" / "findings" / "DUP.md").write_text(
                "# DUP\n\nStatus: VERIFYING\nStatus: OPEN\nSeverity: P2\n",
                encoding="utf-8",
            )
            build_order = root / "factory" / "build-orders" / "DUP.md"
            build_order.write_text(
                "# Bauauftrag: DUP\n\n" + sections, encoding="utf-8"
            )
            errors = vbo.validate_build_order(build_order, repo_root=root)

        self.assertTrue(
            any("mehrfach" in error for error in errors),
            f"Der Bauauftrags-Guard akzeptiert einen mehrdeutigen Status: {errors}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
