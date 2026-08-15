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

# --- The documentation check (final re-audit, finding B) --------------------
#
# The first version of this check listed three literal phrases:
#
#     parallel\s+sicher | sicher\s+parallel |
#     parallele\s+Claude-Worktree-Sessions\s+(sind|werden)\s+unterstuetzt
#
# The independent review of FACTORY-REAL-PROJECT-READINESS-1 pointed out that
# this matched neither the FORMER wording it was supposed to prevent ("Fuer echt
# gleichzeitige Arbeit ... einen eigenen Worktree pro Finding-Branch verwenden")
# nor the umlaut spelling this repository actually writes ("unterstuetzt" with
# "ue" only, never "unterstützt"). Observed against the unmodified regex, all
# nine of the formulations in POSITIVE_CORPUS below went undetected.
#
# The check is now built the other way round, which is the only way to get
# usable coverage without pretending to understand German:
#
#   * A sentence that mentions parallel or simultaneous work MUST also rule it
#     out. Documentation has to be able to discuss parallelism -- every current
#     paragraph does exactly that -- so the term alone cannot be the signal.
#   * The signal is a sentence with a parallelism term and no ruling-out marker.
#     That is a formulation check, not language understanding: it is minimally
#     robust against the spellings actually used here, and it does not claim to
#     catch every conceivable paraphrase.
#
# Deliberately NOT scanned: factory/findings/**, the individual build orders and
# factory/reviews/**. Those quote the historical claim as evidence of what was
# repaired; rewriting history to satisfy a text check would be the opposite of
# what this factory is for.

PARALLELISM_TERM_RE = re.compile(
    r"(parallel|gleichzeitig|nebenl(?:ä|ae)ufig)",
    re.IGNORECASE,
)

# Markers that turn a mention into a rejection. Kept small and concrete: each
# one occurs in a real sentence of this repository's documentation.
RULED_OUT_RE = re.compile(
    r"(nicht|kein|niemals|nirgend|ausschlie(?:ß|ss)|ausgeschlossen|unbewiesen|"
    r"zur(?:ü|ue)ckgestellt|vorgemerkt|v1\.x|fr(?:ü|ue)her|nacheinander)",
    re.IGNORECASE,
)

FENCE_LINE_RE = re.compile(r"^\s*(```|~~~)")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s|\d+\.\s)")


def _sentences(text):
    """Split markdown prose into sentence-sized units.

    Line wrapping is undone inside a paragraph -- otherwise a hard wrap could
    separate a claim from the `nicht` that rules it out, and the check would
    fire on a correct document. Headings and list items start their own unit so
    a negation cannot leak across an unrelated bullet. Fenced blocks are dropped
    entirely: a quoted command output is not a claim.
    """
    lines = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)

    blocks = []
    current = []
    for line in lines:
        starts_block = (
            not line.strip()
            or line.lstrip().startswith("#")
            or LIST_ITEM_RE.match(line)
        )
        if starts_block:
            if current:
                blocks.append(" ".join(current))
                current = []
            if line.strip():
                current = [line.strip()]
            continue
        current.append(line.strip())
    if current:
        blocks.append(" ".join(current))

    sentences = []
    for block in blocks:
        sentences.extend(s for s in re.split(r"(?<=[.!?])\s+", block) if s.strip())
    return sentences


def unruled_parallelism_claims(text):
    """Sentences that mention parallelism without ruling it out."""
    return [
        sentence
        for sentence in _sentences(text)
        if PARALLELISM_TERM_RE.search(sentence)
        and not RULED_OUT_RE.search(sentence)
    ]


# Formulations that MUST be detected. The first is the wording an earlier
# revision of CLAUDE.md actually carried; the rest are the spellings named in
# the re-audit brief (parallel, Parallelitaet, parallele Findings,
# Worktree-Parallelitaet) in both umlaut and ae/ue spelling.
POSITIVE_CORPUS = (
    "Für echt gleichzeitige Arbeit sollte man einen eigenen Worktree pro "
    "Finding-Branch verwenden.",
    "Parallele Claude-Worktree-Sessions sind unterstützt.",
    "Parallele Claude-Worktree-Sessions werden unterstuetzt.",
    "Worktree-Parallelität ist verfügbar und erprobt.",
    "Worktree-Parallelitaet ist verfuegbar und erprobt.",
    "Parallele Findings sind möglich.",
    "Mehrere Findings können parallel bearbeitet werden.",
    "Parallelitaet ist sicher.",
    "Die Factory unterstützt parallel laufende Worktrees.",
    "Nebenläufige Finding-Sessions werden empfohlen.",
)

# Formulations that must NOT be flagged -- the documentation has to stay able to
# rule parallelism out in the wordings it really uses.
NEGATIVE_CORPUS = (
    "Parallele Claude-Worktree-Sessions sind nicht Teil von v1.",
    "Kommen mehrere Findings gleichzeitig herein, werden sie nacheinander "
    "abgearbeitet, nicht gleichzeitig.",
    "Parallelität ist als v1.x-Fähigkeit vorgemerkt.",
    "Frühere Fassungen dieses Abschnitts beschrieben Worktrees als verfügbaren "
    "Modus für echt gleichzeitige Arbeit.",
    "v1 ist bewusst sequentiell und unterstützt Worktree-Parallelität nicht.",
    "Sollte eine spätere Version parallele Findings unterstützen wollen, ist der "
    "Weg nicht, den Schutz zu lockern.",
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
                claims = unruled_parallelism_claims(
                    path.read_text(encoding="utf-8")
                )
                self.assertEqual(
                    claims,
                    [],
                    f"{relative} erwaehnt Parallelitaet, ohne sie im selben Satz "
                    f"auszuschliessen: {claims}",
                )

    def test_the_check_detects_the_formulations_actually_used(self):
        """The gap the final re-audit closed: the old regex found none of these."""
        for sentence in POSITIVE_CORPUS:
            with self.subTest(sentence=sentence):
                self.assertNotEqual(
                    unruled_parallelism_claims(sentence),
                    [],
                    "Diese Parallelitaetsbehauptung wird nicht erkannt",
                )

    def test_the_check_leaves_rejecting_sentences_alone(self):
        """Ruling parallelism out must stay sayable in the wordings used here."""
        for sentence in NEGATIVE_CORPUS:
            with self.subTest(sentence=sentence):
                self.assertEqual(
                    unruled_parallelism_claims(sentence),
                    [],
                    "Ein Satz, der Parallelitaet ausschliesst, wurde als "
                    "Behauptung gemeldet",
                )

    def test_a_quoted_claim_in_a_fenced_block_is_not_a_claim(self):
        """Evidence quotes the old wording; quoting is not asserting."""
        text = (
            "Die frühere Fassung lautete:\n\n"
            "```\nParallele Claude-Worktree-Sessions sind unterstützt.\n```\n"
        )
        self.assertEqual(unruled_parallelism_claims(text), [])

    def test_a_hard_wrapped_rejection_is_not_flagged(self):
        """A negation split across a wrapped line still belongs to the sentence."""
        text = (
            "Parallele Claude-Worktree-Sessions sind **nicht**\n"
            "Teil von v1.\n"
        )
        self.assertEqual(unruled_parallelism_claims(text), [])

    def test_claude_md_does_not_promise_more_than_the_check_delivers(self):
        """The review objection this closes: CLAUDE.md said the test fails if
        ANY document re-introduces the claim -- more than a formulation check
        can deliver."""
        text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("wenn irgendein Dokument die Parallelitätsbehauptung", text)
        self.assertIn("Formulierungsprüfung", text)

    def test_a_finding_worktree_is_not_advertised_as_routine(self):
        """ONBOARDING.md listed creating a finding worktree among the steps that
        run without an approval prompt. Under F-15/B that call cannot succeed in
        a sandboxed session, so listing it described a mode v1 does not have."""
        text = (REPO_ROOT / "factory" / "ONBOARDING.md").read_text(encoding="utf-8")
        marker = text.find("ZERO_ROUTINE_APPROVALS")
        self.assertNotEqual(marker, -1, "ZERO_ROUTINE_APPROVALS-Abschnitt fehlt")
        rest = text[marker:]
        end = rest.find("\n## ", 1)
        section = rest if end == -1 else rest[:end]
        for advertised in ("Finding-Worktree", "create-finding-worktree.sh"):
            with self.subTest(entry=advertised):
                self.assertNotIn(
                    advertised,
                    section,
                    "Die ZERO_ROUTINE_APPROVALS-Liste fuehrt den Worktree-Pfad "
                    "als Routine auf, obwohl Factory v1 ihn nicht unterstuetzt",
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

    def test_raw_git_worktree_is_not_a_required_routine_grant(self):
        """v1 must not require permission for the mode it excludes.

        The preflight's `required` list defines what a zero-approval finding run
        legitimately needs. `Bash(git worktree *)` was in it from the time when
        worktree parallelism was documented as available. After F-15/B it is
        inconsistent: the supported routine never issues `git worktree` itself,
        and create-finding-worktree.sh runs as one allowlisted call whose
        internals need no separate grant. Because `known` is derived from
        `required`, dropping it also turns such a grant into an UNKNOWN shell
        allow, which the preflight reports rather than ignores.
        """
        preflight = (
            REPO_ROOT / "factory" / "scripts" / "factory-preflight.sh"
        ).read_text(encoding="utf-8")
        # Only executable lines count. The comment that explains WHY the entry
        # is absent necessarily contains the string itself, and matching it
        # would make this test permanently red for the very change it guards.
        code_lines = [
            line
            for line in preflight.splitlines()
            if not line.lstrip().startswith("#")
        ]
        offending = [line for line in code_lines if '"Bash(git worktree *)"' in line]
        self.assertEqual(
            offending,
            [],
            "Der Preflight verlangt weiterhin eine Routine-Freigabe fuer "
            f"'git worktree' -- genau den Modus, den Factory v1 ausschliesst: {offending}",
        )

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
