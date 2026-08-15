"""Regression tests for the build-order gate (audit finding F-10).

Run with:
    python3 -m unittest factory.guards.test_build_order

Before this repair, "ein Finding bekommt einen Bauauftrag" was prose in
factory/build-orders/README.md and nothing else. A finding could reach
IMPLEMENTING, VERIFYING, READY_FOR_CLOSURE and CLOSED with no build order at
all, or with one that consisted of empty headings -- and every layer
(validate-finding.py, the canonical runner, the Stop hook, CI) reported
success. The independent reviewer is explicitly told to hold the build order
against the actual code; with no build order, that instruction has nothing to
hold.

These tests were written to FAIL against the pre-repair guards, which accepted
all of the following:

  - a finding at IMPLEMENTING with no factory/build-orders/<ID>.md at all
  - a build order whose sections are placeholders ("TBD", "TODO", empty)
  - a build order missing required sections entirely
  - a build order whose title names a different finding
  - an orphan build order with no finding behind it
  - "Red Regression Evidence" that asserts a red run without quoting one
  - a finding reaching VERIFYING with no green evidence recorded

Each test builds a throwaway git repository containing copies of the real
guards, so <repo-root> (which the guards resolve from their own location) is
that temp tree. The real factory/findings/, factory/build-orders/ and
factory/reviews/ of this repository are never read or written.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REAL_GUARDS_DIR = Path(__file__).resolve().parent

GUARD_FILES = (
    "validate-finding.py",
    "validate-review.py",
    "validate-build-order.py",
    "run-factory-checks.py",
    "validate-control-plane.py",
    "scope_hash.py",
)

GIT_ENV_OVERRIDES = {
    "GIT_AUTHOR_NAME": "Factory Test",
    "GIT_AUTHOR_EMAIL": "factory-test@example.invalid",
    "GIT_COMMITTER_NAME": "Factory Test",
    "GIT_COMMITTER_EMAIL": "factory-test@example.invalid",
}

ANALYSIS_BLOCK = """\
Root Cause: Fehlende Pruefung der Organisation beim Erstellen neuer Jobs.
Affected Components: Job-Scheduler, Job-Worker.
Relevant Architecture: Hintergrundjobs laufen ohne zentralen Org-Filter.
Recommended Repair: Zentralen Guard einfuehren, der die Org-ID erzwingt.
Regression Test Plan: Neue Tests fuer Jobs mit falscher/fehlender Org-ID.
Central Guard Plan: Guard-Funktion, die jeder Job-Registrierung vorgeschaltet wird.
Expected Blast Radius: Nur neue Hintergrundjobs, keine bestehenden Endpunkte.
Risk Assessment: Gering, da rein additive Pruefung ohne bestehendes Verhalten zu aendern.
"""

# A build order that satisfies every rule. Individual tests damage exactly one
# aspect of it, so a failure names one cause rather than a pile of them.
GOOD_SECTIONS = {
    "Primaere Sicherheitsgrenze": (
        "Die eigentliche Reparatur ist eine Datenstrukturgrenze: die Org-ID wird nicht mehr\n"
        "als Parameter durchgereicht, sondern aus dem Auftragskontext abgeleitet.\n"
    ),
    "Verbindliche Reihenfolge": (
        "1. Regressionstest schreiben und ROT beobachten.\n"
        "2. Laufzeitgrenze umsetzen, bis derselbe Test GRUEN ist.\n"
        "3. Zentralen Guard ergaenzen.\n"
        "4. Kanonischen Runner und Projekttests laufen lassen.\n"
    ),
    "Acceptance Criteria": (
        "Ein Job ohne abgeleitete Org-ID ist nicht mehr registrierbar, und der zentrale\n"
        "Guard erkennt jeden erneuten Versuch, sie als Parameter zu uebergeben.\n"
    ),
    "Scope": (
        "Erlaubt und abschliessend: app/jobs/**, app/tests/test_jobs.py.\n"
        "Alles andere ist out of scope, insbesondere die geschuetzten Factory-Pfade.\n"
    ),
    "Red Regression Evidence": (
        "Der zitierte, tatsaechliche Fehlschlag vor dem Fix:\n"
        "\n"
        "```\n"
        "FAIL: test_job_without_org_is_rejected\n"
        "AssertionError: 0 != 1 : guard accepted what it must reject.\n"
        "Ran 4 tests -- FAILED (failures=1)\n"
        "```\n"
    ),
    "Green Runtime Fix Evidence": (
        "Dieselben Tests nach dem Fix, plus kanonischer Runner:\n"
        "\n"
        "```\n"
        "$ python3 -m unittest app.tests.test_jobs\n"
        "Ran 4 tests in 0.112s\n"
        "OK\n"
        "```\n"
    ),
}

SECTION_ORDER = list(GOOD_SECTIONS)


def _git(cwd, *args):
    env = dict(os.environ)
    env.update(GIT_ENV_OVERRIDES)
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


class BuildOrderTestCase(unittest.TestCase):
    """Throwaway git project containing copies of the real guards."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-build-order-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.root = self.tmp_dir / "project"

        self.guards_dir = self.root / "factory" / "guards"
        self.findings_dir = self.root / "factory" / "findings"
        self.reviews_dir = self.root / "factory" / "reviews"
        self.build_orders_dir = self.root / "factory" / "build-orders"
        for directory in (
            self.guards_dir,
            self.findings_dir,
            self.reviews_dir,
            self.build_orders_dir,
            self.root / "app",
        ):
            directory.mkdir(parents=True)

        for name in GUARD_FILES:
            source = REAL_GUARDS_DIR / name
            if source.is_file():
                shutil.copy2(source, self.guards_dir / name)

        (self.root / "app" / "code.py").write_text("VALUE = 1\n", encoding="utf-8")

        _git(self.root, "init", "--initial-branch=trunk")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "initial")

        stamp = subprocess.run(
            [
                sys.executable,
                str(self.guards_dir / "validate-control-plane.py"),
                "--repo-root",
                str(self.root),
                "--update",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(stamp.returncode, 0, stamp.stderr)

    # -- helpers ---------------------------------------------------------

    def write_finding(self, finding_id, status="IMPLEMENTING", severity="P1"):
        body = [
            f"# {finding_id}",
            "",
            f"Status: {status}",
            f"Severity: {severity}",
            "",
            "## Befund",
            "",
            "Beispielbefund.",
            "",
            "## Analyse",
            "",
            ANALYSIS_BLOCK.rstrip(),
        ]
        path = self.findings_dir / f"{finding_id}.md"
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        return path

    def write_build_order(self, finding_id, title_id=None, sections=None, omit=(), directory=None):
        """Write a build order, optionally damaged in exactly one way."""
        used = dict(GOOD_SECTIONS if sections is None else sections)
        for name in omit:
            used.pop(name, None)

        lines = [f"# Bauauftrag: {title_id or finding_id}", ""]
        for name in SECTION_ORDER:
            if name not in used:
                continue
            lines.append(f"## {name}")
            lines.append("")
            lines.append(used[name].rstrip())
            lines.append("")

        target_dir = self.build_orders_dir if directory is None else directory
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{finding_id}.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def validate_finding(self, path):
        return subprocess.run(
            [sys.executable, str(self.guards_dir / "validate-finding.py"), str(path)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )

    def validate_build_order(self, path):
        return subprocess.run(
            [sys.executable, str(self.guards_dir / "validate-build-order.py"), str(path)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )

    def run_factory_checks(self):
        return subprocess.run(
            [sys.executable, str(self.guards_dir / "run-factory-checks.py")],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )

    def assertRejected(self, result, *expected_fragments):
        self.assertEqual(
            result.returncode,
            1,
            f"guard accepted what it must reject.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        combined = result.stdout + result.stderr
        for fragment in expected_fragments:
            self.assertIn(fragment, combined)

    def assertAccepted(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class BuildOrderRequiredTests(BuildOrderTestCase):
    """A finding must not get past ANALYZED without a valid build order."""

    def test_implementing_without_a_build_order_is_rejected(self):
        finding = self.write_finding("F-1", status="IMPLEMENTING")
        self.assertRejected(self.validate_finding(finding), "Bauauftrag")

    def test_verifying_without_a_build_order_is_rejected(self):
        finding = self.write_finding("F-1", status="VERIFYING")
        self.assertRejected(self.validate_finding(finding), "Bauauftrag")

    def test_closed_without_a_build_order_is_rejected(self):
        finding = self.write_finding("F-1", status="CLOSED")
        self.assertRejected(self.validate_finding(finding), "Bauauftrag")

    def test_analyzed_does_not_require_a_build_order(self):
        """The build order is written after ANALYZED -- requiring it there
        would make the state unreachable."""
        finding = self.write_finding("F-1", status="ANALYZED")
        self.assertAccepted(self.validate_finding(finding))

    def test_open_does_not_require_a_build_order(self):
        finding = self.write_finding("F-1", status="OPEN", severity=None or "P2")
        self.assertAccepted(self.validate_finding(finding))

    def test_expert_review_required_does_not_require_a_build_order(self):
        """The escalation must stay reachable from anywhere, including from a
        state where no build order could be written yet."""
        path = self.findings_dir / "F-1.md"
        path.write_text(
            "# F-1\n\nStatus: EXPERT_REVIEW_REQUIRED\nSeverity: P1\n\n## Analyse\n\n"
            "Risk Assessment: Unklar, potenziell hoch.\n"
            "Expert Review Reason: Auswirkung auf Bestandsdaten nicht abschaetzbar.\n"
            "What Is Known: Der Endpunkt akzeptiert fremde Org-IDs.\n"
            "What Remains Uncertain: Ob bereits Daten betroffen sind.\n"
            "What An Expert Would Need To Review: Migrationspfad und Datenbestand.\n",
            encoding="utf-8",
        )
        self.assertAccepted(self.validate_finding(path))

    def test_a_valid_build_order_lets_implementing_pass(self):
        finding = self.write_finding("F-1", status="IMPLEMENTING")
        self.write_build_order("F-1")
        self.assertAccepted(self.validate_finding(finding))


class BuildOrderStructureTests(BuildOrderTestCase):
    """The build order itself must be a build order, not an empty shell."""

    def test_missing_required_section_is_rejected(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        path = self.write_build_order("F-1", omit=("Acceptance Criteria",))
        self.assertRejected(self.validate_build_order(path), "Acceptance Criteria")

    def test_missing_scope_section_is_rejected(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        path = self.write_build_order("F-1", omit=("Scope",))
        self.assertRejected(self.validate_build_order(path), "Scope")

    def test_placeholder_section_is_rejected(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        sections = dict(GOOD_SECTIONS)
        sections["Acceptance Criteria"] = "TBD\n"
        path = self.write_build_order("F-1", sections=sections)
        self.assertRejected(self.validate_build_order(path), "Acceptance Criteria")

    def test_empty_section_is_rejected(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        sections = dict(GOOD_SECTIONS)
        sections["Scope"] = "\n"
        path = self.write_build_order("F-1", sections=sections)
        self.assertRejected(self.validate_build_order(path), "Scope")

    def test_todo_placeholder_in_scope_is_rejected(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        sections = dict(GOOD_SECTIONS)
        sections["Scope"] = "TODO\n"
        path = self.write_build_order("F-1", sections=sections)
        self.assertRejected(self.validate_build_order(path), "Scope")

    def test_a_wholly_valid_build_order_is_accepted(self):
        self.write_finding("F-1", status="VERIFYING")
        path = self.write_build_order("F-1")
        self.assertAccepted(self.validate_build_order(path))


class BuildOrderIdentityTests(BuildOrderTestCase):
    """Build order, finding ID and file name are bound to each other."""

    def test_build_order_titled_for_another_finding_is_rejected(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        path = self.write_build_order("F-1", title_id="F-2")
        self.assertRejected(self.validate_build_order(path), "F-2")

    def test_orphan_build_order_without_a_finding_is_rejected(self):
        path = self.write_build_order("F-99")
        self.assertRejected(self.validate_build_order(path), "F-99")

    def test_build_order_outside_the_canonical_directory_is_rejected(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        elsewhere = self.root / "docs"
        path = self.write_build_order("F-1", directory=elsewhere)
        self.assertRejected(self.validate_build_order(path), "factory/build-orders")

    def test_another_findings_build_order_cannot_satisfy_this_finding(self):
        """F-1 must not pass because SOME build order exists somewhere."""
        finding = self.write_finding("F-1", status="IMPLEMENTING")
        self.write_finding("F-2", status="IMPLEMENTING")
        self.write_build_order("F-2")
        self.assertRejected(self.validate_finding(finding), "Bauauftrag")


class BuildOrderEvidenceLifecycleTests(BuildOrderTestCase):
    """Evidence requirements follow the finding's lifecycle."""

    def test_red_evidence_without_quoted_output_is_rejected_at_implementing(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        sections = dict(GOOD_SECTIONS)
        sections["Red Regression Evidence"] = (
            "Der Regressionstest war vor dem Fix rot. Das wurde beobachtet und ist gesichert.\n"
        )
        path = self.write_build_order("F-1", sections=sections)
        self.assertRejected(self.validate_build_order(path), "Red Regression Evidence")

    def test_empty_red_evidence_is_rejected_at_implementing(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        sections = dict(GOOD_SECTIONS)
        sections["Red Regression Evidence"] = "Not yet analyzed\n"
        path = self.write_build_order("F-1", sections=sections)
        self.assertRejected(self.validate_build_order(path), "Red Regression Evidence")

    def test_green_evidence_is_not_required_at_implementing(self):
        """At IMPLEMENTING the fix is still being written -- demanding green
        evidence there would force the record to be written before it is true."""
        self.write_finding("F-1", status="IMPLEMENTING")
        sections = dict(GOOD_SECTIONS)
        sections["Green Runtime Fix Evidence"] = "Steht nach der Umsetzung. Noch nicht gelaufen.\n"
        path = self.write_build_order("F-1", sections=sections)
        self.assertAccepted(self.validate_build_order(path))

    def test_green_evidence_is_required_from_verifying_onwards(self):
        self.write_finding("F-1", status="VERIFYING")
        sections = dict(GOOD_SECTIONS)
        sections["Green Runtime Fix Evidence"] = "Steht nach der Umsetzung. Noch nicht gelaufen.\n"
        path = self.write_build_order("F-1", sections=sections)
        self.assertRejected(self.validate_build_order(path), "Green Runtime Fix Evidence")

    def test_green_evidence_is_required_at_closed(self):
        self.write_finding("F-1", status="CLOSED")
        sections = dict(GOOD_SECTIONS)
        sections["Green Runtime Fix Evidence"] = "TBD\n"
        path = self.write_build_order("F-1", sections=sections)
        self.assertRejected(self.validate_build_order(path), "Green Runtime Fix Evidence")

    def test_a_finding_at_verifying_inherits_the_build_order_failure(self):
        """The finding validator does not merely check existence -- it fails
        when the build order itself fails."""
        finding = self.write_finding("F-1", status="VERIFYING")
        sections = dict(GOOD_SECTIONS)
        sections["Green Runtime Fix Evidence"] = "TBD\n"
        self.write_build_order("F-1", sections=sections)
        self.assertRejected(self.validate_finding(finding), "Bauauftrag")


class BuildOrderRunnerTests(BuildOrderTestCase):
    """The canonical runner is the layer CI actually executes."""

    def test_runner_rejects_a_finding_without_a_build_order(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        self.assertRejected(self.run_factory_checks(), "Bauauftrag")

    def test_runner_validates_every_build_order(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        sections = dict(GOOD_SECTIONS)
        sections["Scope"] = "TBD\n"
        self.write_build_order("F-1", sections=sections)
        self.assertRejected(self.run_factory_checks(), "Scope")

    def test_runner_accepts_a_consistent_pair(self):
        self.write_finding("F-1", status="IMPLEMENTING")
        self.write_build_order("F-1")
        self.assertAccepted(self.run_factory_checks())

    def test_readme_in_build_orders_is_not_treated_as_a_build_order(self):
        """The directory's own README documents the format; it is not an
        orphan build order for a finding called 'README'."""
        (self.build_orders_dir / "README.md").write_text(
            "# Bauauftraege\n\nFormatbeschreibung, kein Bauauftrag.\n", encoding="utf-8"
        )
        self.write_finding("F-1", status="IMPLEMENTING")
        self.write_build_order("F-1")
        self.assertAccepted(self.run_factory_checks())


if __name__ == "__main__":
    unittest.main(verbosity=2)
