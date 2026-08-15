#!/usr/bin/env python3
"""The worktree protection model, decided by observation (audit finding F-15).

## What was open

The audit did not claim the worktree mode was broken. It said the SECURITY
ASSUMPTIONS behind it were unproven: does `permissions.deny` anchor to the
worktree or to the main repository? Is `<worktree>/factory/reviews/` actually
protected? Where does the SubagentStop hook write, and does it resolve the
right project root? Can review evidence land in the main repo instead of the
finding's worktree?

## What was actually observed

Run in the real repository (not a copy), inside an active Claude Code session,
using the factory's own canonical mechanism:

    $ factory/scripts/create-finding-worktree.sh create <BASE_SHA> \\
          .claude/worktrees/F15-PROBE fix/F15-PROBE
    Preparing worktree (new branch 'fix/F15-PROBE')
    error: unable to create file .claude/agents/finding-closure-reviewer.md:
           Operation not permitted
    fatal: Could not reset index file to revision 'HEAD'.

Repeated with a target OUTSIDE `.claude/` (`wt-probe`), with the identical
result -- so this is not about where the worktree is placed.

**A finding worktree cannot be created at all while the factory's own sandbox
is active.** Checking out a worktree means writing every tracked file, and the
control plane (`.claude/agents/**`, `.claude/hooks/**`, `factory/guards/**`,
...) is exactly what the sandbox refuses to let this agent write. The F-05
protection and the worktree mode are mutually exclusive by construction.

Nothing here is malfunctioning: the sandbox does precisely what it is meant to
do. What was wrong was the documentation, which described parallel worktree
work as an available mode.

## The conclusion: B, not A

Factory v1 is **deliberately sequential**. One finding at a time, in the main
repository, on its own branch. That is not a preference -- it is the observed
consequence of the control-plane protection, and it is recorded here so that no
one re-introduces the parallelism claim without re-running the observation.

The questions about `<worktree>/factory/reviews/`, the hook's project root and
scope-hash attribution inside a worktree are therefore **not answered and not
answerable** in this configuration: there is no worktree in which to answer
them. Claiming they are safe would be exactly the unproven assurance F-15 is
about.

## What this file tests

Automatically, everywhere:
  - the documentation does not promise parallel worktree sessions
  - the control-plane paths are still denied for write in settings.json
  - the worktree script reports the incompatibility as a clear blocker rather
    than a raw git error

Only inside an active sandbox (reported separately, like F-19's
SANDBOX_VERIFICATION, never counted as a pass when skipped):
  - creating a worktree really is refused
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

GUARDS_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUARDS_DIR.parents[1]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
WORKTREE_SCRIPT = REPO_ROOT / "factory" / "scripts" / "create-finding-worktree.sh"

# Phrases that would re-introduce the unproven claim. Deliberately narrow: the
# documentation must be able to DISCUSS parallelism in order to rule it out.
PARALLELISM_CLAIM_RE = re.compile(
    r"(parallel\s+sicher|sicher\s+parallel|parallele\s+Claude-Worktree-Sessions\s+"
    r"(?:sind|werden)\s+unterstuetzt)",
    re.IGNORECASE,
)


class DocumentationTests(unittest.TestCase):
    """No unproven parallelism claim may exist in the repository."""

    DOCS = (
        "CLAUDE.md",
        ".claude/rules/factory-workflow.md",
        "factory/README.md",
        "factory/ONBOARDING.md",
    )

    def test_no_document_claims_parallel_worktree_safety(self):
        for relative in self.DOCS:
            path = REPO_ROOT / relative
            if not path.is_file():
                continue
            with self.subTest(document=relative):
                text = path.read_text(encoding="utf-8")
                match = PARALLELISM_CLAIM_RE.search(text)
                self.assertIsNone(
                    match,
                    f"{relative} behauptet Parallelitaet: "
                    f"{match.group(0) if match else ''}",
                )

    def test_the_sequential_decision_is_documented(self):
        text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(
            "sequentiell",
            text.lower(),
            "CLAUDE.md haelt die sequentielle Spezifikation (F-15, Ergebnis B) "
            "nicht fest",
        )

    def test_the_supported_sequential_workflow_is_spelled_out(self):
        """Ruling parallelism out is not enough -- the supported path for normal
        P1 work has to be written down, or the rule is only a prohibition."""
        text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Der unterstützte Ablauf für normale P1-Arbeit", text)
        self.assertIn("git switch --no-track -c fix/<ID> origin/<default-branch>", text)

    def test_parallelism_is_marked_as_a_later_v1_x_capability(self):
        """Deferred, not discarded -- and explicitly not by weakening the
        sandbox or the control-plane protection."""
        text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("v1.x", text)
        marker = text.find("v1.x")
        window = text[max(0, marker - 400) : marker + 800]
        self.assertIn("nicht", window.lower())
        for forbidden_route in ("permissions.deny", "denyWrite"):
            self.assertIn(
                forbidden_route,
                window,
                "Der Weg zu Parallelitaet muss ausdruecklich NICHT ueber eine "
                "Lockerung der Schutzmechanismen fuehren",
            )


class ControlPlaneStillDeniedTests(unittest.TestCase):
    """The protection whose side effect this finding documents must stay."""

    def test_settings_still_deny_writing_the_control_plane(self):
        text = SETTINGS.read_text(encoding="utf-8")
        for needle in (
            "factory/guards",
            "factory/scripts",
            ".claude/hooks",
            ".claude/agents",
            "factory/reviews",
        ):
            with self.subTest(path=needle):
                self.assertIn(needle, text)

    def test_reviews_directory_is_denied_for_edit_and_write_tools(self):
        text = SETTINGS.read_text(encoding="utf-8")
        self.assertIn("Edit(/factory/reviews/**)", text)
        self.assertIn("Write(/factory/reviews/**)", text)


class WorktreeScriptTests(unittest.TestCase):
    def test_script_explains_the_sandbox_incompatibility(self):
        """A raw `Operation not permitted` from git is not an explanation."""
        source = WORKTREE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "SANDBOX_WORKTREE_INCOMPATIBLE",
            source,
            "create-finding-worktree.sh meldet die beobachtete Inkompatibilitaet "
            "nicht als eigenen, erklaerten Zustand",
        )

    def test_script_blocks_before_attempting_the_worktree(self):
        """The block must come BEFORE `git worktree add`.

        Checking afterwards leaves a half-created worktree and a dangling
        branch behind, and makes a specified boundary look like a malfunction.
        """
        source = WORKTREE_SCRIPT.read_text(encoding="utf-8")
        probe_at = source.find("worktree-sandbox-probe")
        # The EXECUTABLE call, not the first mention: the docstring and the
        # explanatory comments name `git worktree add` long before it runs.
        # Matched with its leading indentation so a comment line cannot match.
        add_at = source.find("\n    git worktree add --no-track")
        self.assertNotEqual(probe_at, -1, "keine Schreibprobe im Skript gefunden")
        self.assertNotEqual(
            add_at, -1, "der ausfuehrbare 'git worktree add'-Aufruf wurde nicht gefunden"
        )
        self.assertLess(
            probe_at,
            add_at,
            "die Sandbox-Probe steht nicht vor 'git worktree add' -- die Blockade "
            "waere reaktiv statt vorbeugend",
        )

    def test_script_does_not_suggest_weakening_protection(self):
        source = WORKTREE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("nichts, was durch Lockern von Berechtigungen", source)

    def test_script_still_refuses_a_wrong_base(self):
        """F-16/F-17 invariants must not be weakened by this change."""
        source = WORKTREE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("AUTONOMY_BLOCKER", source)
        self.assertIn("--no-track", source)


class SandboxObservationTests(unittest.TestCase):
    """The part that only a real sandbox can answer.

    Modelled on F-19's SANDBOX_VERIFICATION: a skipped test here is reported as
    "not observed", never as "observed safe".

    An earlier version of this file tried to prove the point by actually running
    `git worktree add` into a temp directory. That was wrong twice over. It
    SUCCEEDED -- which is the finding, not a failure -- and it left a worktree
    registration in .git/worktrees/ that the sandbox then refused to let
    `git worktree prune` remove, so the repository kept a dangling entry a test
    run could not clean up. A test must not need write access the agent it
    tests does not have.
    """

    CONTROL_PLANE_PROBES = (
        Path("factory") / "guards",
        Path(".claude") / "agents",
    )

    def _probe(self, directory):
        """True if a byte can be written into `directory`."""
        marker = directory / ".f15-write-probe"
        try:
            marker.touch()
        except OSError:
            return False
        marker.unlink()
        return True

    def test_control_plane_is_not_writable_inside_the_repository(self):
        """The invariant the worktree incompatibility follows from."""
        writable = [
            str(rel) for rel in self.CONTROL_PLANE_PROBES
            if self._probe(REPO_ROOT / rel)
        ]
        if len(writable) == len(self.CONTROL_PLANE_PROBES):
            self.skipTest(
                "SANDBOX_WORKTREE_OBSERVATION: not_performed -- die "
                "Control-Plane-Pfade sind hier beschreibbar, es laeuft also keine "
                "aktive Claude-Code-Sandbox. Ein uebersprungener Test belegt "
                "NICHT, dass der Worktree-Modus sicher ist; er belegt, dass hier "
                "keine Sandbox aktiv ist."
            )
        self.assertEqual(
            writable,
            [],
            "Control-Plane-Pfade sind teilweise beschreibbar -- der Schutz aus "
            "F-05 greift nicht mehr vollstaendig.",
        )

    def test_protection_is_bound_to_the_running_sessions_project_root(self):
        """Why a running v1 session must not create an external worktree.

        `sandbox.filesystem.denyWrite` lists paths relative to the RUNNING
        SESSION's project root (`./factory/guards`, ...). For paths outside that
        root the rules do not apply -- observed here, not assumed. A worktree
        placed outside it therefore succeeds and is, FROM THIS SESSION, not
        covered by these path boundaries: this session could rewrite the guards
        that judge it.

        Deliberately NOT claimed, because it was not tested: that a freshly
        started Claude Code session whose own project root IS that worktree
        would lack protection. That question is irrelevant to v1, which is
        sequential by decision and does not support worktree parallelism.
        """
        if self._probe(REPO_ROOT / "factory" / "guards"):
            self.skipTest(
                "SANDBOX_WORKTREE_OBSERVATION: not_performed -- ohne aktive "
                "Sandbox ist der Vergleich innen/aussen bedeutungslos."
            )

        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "factory" / "guards"
            outside.mkdir(parents=True)
            self.assertTrue(
                self._probe(outside),
                "Ausserhalb der Projektwurzel dieser Session war factory/guards "
                "nicht beschreibbar -- die Begruendung fuer F-15/B hat sich "
                "geaendert und muss neu erhoben werden.",
            )

    def test_no_stale_worktree_registration_is_left_behind(self):
        """This repository must not accumulate worktrees a run cannot remove."""
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(
            "prunable",
            result.stdout,
            "Es existiert eine verwaiste Worktree-Registrierung. Sie kann unter "
            "aktiver Sandbox nicht entfernt werden ('.git/worktrees/' ist nicht "
            "schreibbar) und muss ausserhalb der Session mit "
            "'git worktree prune' beseitigt werden.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
