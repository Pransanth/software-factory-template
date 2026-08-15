#!/usr/bin/env bash
# Factory onboarding / preflight for a NEW project.
#
# Purpose: a human sets this repository up ONCE, and after that a normal
# finding runs unattended -- no repeated approval/GitHub/permission odyssey.
# This script is the check half of that: it verifies, deterministically and
# without changing anything, that every prerequisite the proven factory run
# actually needs is in place. What it cannot safely automate (creating a
# GitHub token, granting repository admin rights, configuring branch
# protection, granting Claude Code local permissions) it does NOT fake and
# does NOT half-automate: it names the exact missing step, and you run the
# preflight again afterwards.
#
# It never writes anything, never creates a PR, never merges, never prints a
# token, and never installs software. `gh` is NOT required -- all GitHub
# access goes through factory/scripts/gh-api.sh, which uses the git
# credential helper plus curl.
#
# Nothing is hardcoded to one machine, one owner or one repository: the
# repository root, the origin slug, the default branch and the absolute
# paths in the suggested local permission snippet are all derived from the
# repository this script is run in. The documented convention is
# origin/<default-branch>, where <default-branch> is resolved live from the
# remote (never from the stale local remote-HEAD symref).
#
# ## What the operational-robustness package changed here
#
# F-11 -- `--local-only` used to print `FACTORY_PREFLIGHT: PASS` and "normale
# Finding-Arbeit laeuft ohne Routine-Approvals" while every GitHub gate was
# skipped. That is a verdict about a layer this run never entered. There is
# now a third outcome, PARTIAL, with its own exit code, and PASS is
# unreachable without the remote checks.
#
# F-12 -- the pull-request permission probe classified by exclusion: anything
# not recognisably a 403 was reported as PERMITTED, so a 401 from a wrong
# token and a 404 from an invisible repository both read as "the token may
# open pull requests". The probe now lives in gh-query.sh/gh_evidence.py, is
# regression-tested without a network, and recognises permission only
# positively.
#
# F-13 -- branch protection was COUNTED, not read. A ruleset that only blocks
# force-pushes satisfied "Branch-Schutz aktiv". The preflight now reads what
# the rules actually guarantee, from rulesets AND classic branch protection,
# and reports required approvals as an explicit governance question rather
# than pretending an unattended merge is possible.
#
# F-14 -- factory functionality was a file-existence check, so a repository
# whose required files all contained the word "placeholder" passed. The
# preflight now rejects placeholder content and, more importantly, RUNS the
# control-plane guard, the canonical runner and the discovered test suite.
#
# F-19/F-20 -- the test run reports CI tests and real sandbox verification
# separately (a skipped sandbox test is never evidence of a sandbox), and the
# credential probe is explicitly non-interactive so a missing credential
# blocks instead of hanging.
#
# Usage:
#   factory/scripts/factory-preflight.sh              # all checks
#   factory/scripts/factory-preflight.sh --local-only # skip network/GitHub checks
#
# Exit code 0: FACTORY_PREFLIGHT: PASS -- every layer was checked and
#              unattended finding runs are ready.
# Exit code 1: FACTORY_PREFLIGHT: BLOCKED -- at least one prerequisite is
#              missing; each one is printed with the exact step needed.
# Exit code 2: usage error.
# Exit code 3: FACTORY_PREFLIGHT: PARTIAL -- the local layer passed and the
#              GitHub/remote layer was not checked at all. Deliberately NOT 0:
#              nothing may treat an unchecked layer as a passed one.
set -uo pipefail

MODE="all"
case "${1:-}" in
  "") ;;
  --local-only) MODE="local" ;;
  *)
    echo "usage: factory-preflight.sh [--local-only]" >&2
    exit 2
    ;;
esac

# -P: compare physical paths, the same form `git rev-parse --show-toplevel`
# reports, so a symlinked parent (e.g. /var -> /private/var) does not look
# like a mismatch.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"

# Project code directory (the product this factory is used on). Overridable
# because not every project calls it app/.
PROJECT_DIR="${FACTORY_PROJECT_DIR:-app}"
# Name of the CI check that must be the Required Status Check on the
# protected default branch. Matches the job id in
# .github/workflows/factory-ci.yml.
REQUIRED_CHECK="${FACTORY_REQUIRED_CHECK:-factory-checks}"

BLOCKERS=0
STEPS=()

ok()   { printf '[OK]      %s\n' "$1"; }
info() { printf '[INFO]    %s\n' "$1"; }
skip() { printf '[SKIP]    %s\n' "$1"; }
missing() {
  printf '[FEHLT]   %s\n' "$1"
  STEPS+=("$2")
  BLOCKERS=$((BLOCKERS + 1))
}
# A prerequisite that no technical change inside this repository can satisfy,
# because it is somebody's deliberate policy. Reported under its own label so
# it is never mistaken for a bug to be worked around.
governance() {
  printf '[GOVERNANCE] %s\n' "$1"
  STEPS+=("$2")
  BLOCKERS=$((BLOCKERS + 1))
}

# --- 1. Standalone git repository -------------------------------------------

TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$TOPLEVEL" ]; then
  missing "Kein Git-Repository." \
    "In $ROOT ein eigenes Repository anlegen: 'git init' und einen ersten Commit erstellen."
elif [ "$TOPLEVEL" != "$ROOT" ]; then
  missing "Git-Wurzel ($TOPLEVEL) ist nicht die Factory-Wurzel ($ROOT)." \
    "Die Factory muss ein eigenstaendiges Repository sein. $ROOT als eigenes Repository initialisieren, nicht als Unterverzeichnis eines anderen Repos."
else
  ok "Eigenstaendiges Git-Repository: $ROOT"
fi

# --- 2. origin remote --------------------------------------------------------

ORIGIN_URL="$(git config --get remote.origin.url 2>/dev/null || true)"
REPO_SLUG=""
if [ -z "$ORIGIN_URL" ]; then
  missing "Kein 'origin'-Remote konfiguriert." \
    "GitHub-Repository anlegen und verbinden: 'git remote add origin https://github.com/<OWNER>/<REPO>.git'"
else
  case "$ORIGIN_URL" in
    *github.com/*|*github.com:*)
      # It points at GitHub. The exact OWNER/REPO is derived by gh-api.sh,
      # which owns slug normalisation and validation (audit finding F-17), so
      # there is exactly one implementation of "what does origin point at".
      # If that script is not there yet, section 3 reports it as a missing
      # file -- this section must still be able to say whether origin itself
      # is usable, which is a separate question.
      if [ -f "$ROOT/factory/scripts/gh-api.sh" ]; then
        SLUG_LINE="$(bash "$ROOT/factory/scripts/gh-api.sh" slug 2>/dev/null | /usr/bin/grep '^slug:' || true)"
      else
        SLUG_LINE=""
      fi
      if [ -n "$SLUG_LINE" ]; then
        REPO_SLUG="${SLUG_LINE#slug: }"
        ok "origin zeigt auf GitHub: $REPO_SLUG"
      elif [ -f "$ROOT/factory/scripts/gh-api.sh" ]; then
        missing "origin ist kein unterstuetzter github.com-Remote ($ORIGIN_URL)." \
          "Die Factory-GitHub-Helfer (gh-api.sh/gh-query.sh) sprechen die GitHub-REST-API an. origin auf eine unterstuetzte Schreibweise umstellen: https://github.com/OWNER/REPO(.git), ssh://git@github.com/OWNER/REPO(.git) oder git@github.com:OWNER/REPO(.git)."
      else
        info "origin zeigt auf GitHub ($ORIGIN_URL); der genaue Slug ist erst bestimmbar, wenn factory/scripts/gh-api.sh vorhanden ist."
      fi
      ;;
    *)
      missing "origin ist kein github.com-Remote ($ORIGIN_URL)." \
        "Die Factory-GitHub-Helfer (gh-api.sh/gh-query.sh) sprechen die GitHub-REST-API an. origin auf ein github.com-Repository umstellen."
      ;;
  esac
fi

# --- 3. Factory files present, and not placeholders --------------------------
#
# F-14: this used to be `[ -f "$path" ]` and nothing else, so a repository in
# which every required file contained the word "placeholder" was reported as
# fully equipped. Existence is necessary and nowhere near sufficient.

REQUIRED_FILES=(
  "factory/guards/run-factory-checks.py"
  "factory/guards/run-factory-tests.py"
  "factory/guards/validate-finding.py"
  "factory/guards/validate-review.py"
  "factory/guards/validate-build-order.py"
  "factory/guards/validate-control-plane.py"
  "factory/guards/scope_hash.py"
  "factory/guards/gh_evidence.py"
  "factory/guards/finding_state.py"
  "factory/guards/run-project-tests.py"
  "factory/control-plane.sha256"
  "factory/scripts/gh-api.sh"
  "factory/scripts/gh-query.sh"
  "factory/scripts/create-finding-worktree.sh"
  ".claude/hooks/stop-validate-findings.py"
  ".claude/hooks/subagentstop-write-review.py"
  ".claude/agents/finding-closure-reviewer.md"
  ".claude/skills/verify-finding/SKILL.md"
  ".claude/rules/factory-workflow.md"
  ".claude/settings.json"
  ".github/workflows/factory-ci.yml"
)
MISSING_FILES=""
PLACEHOLDER_FILES=""
for rel in "${REQUIRED_FILES[@]}"; do
  if [ ! -f "$ROOT/$rel" ]; then
    MISSING_FILES="$MISSING_FILES $rel"
    continue
  fi
  # A stub, a leftover scaffold or a truncated copy. 200 bytes is far below
  # the smallest real file in the template and far above any placeholder.
  BYTES="$(/usr/bin/wc -c < "$ROOT/$rel" | /usr/bin/tr -d ' ')"
  if [ "$BYTES" -lt 200 ]; then
    PLACEHOLDER_FILES="$PLACEHOLDER_FILES $rel(${BYTES}B)"
  fi
done
if [ -n "$MISSING_FILES" ]; then
  missing "Factory-Dateien fehlen:$MISSING_FILES" \
    "Fehlende Dateien aus der Factory-Vorlage uebernehmen:$MISSING_FILES"
elif [ -n "$PLACEHOLDER_FILES" ]; then
  missing "Factory-Dateien sind Platzhalter, keine echten Dateien:$PLACEHOLDER_FILES" \
    "Diese Dateien vollstaendig aus der Factory-Vorlage uebernehmen. Eine Datei mit dem richtigen Namen ist kein Guard -- der Preflight prueft Inhalt und Funktion, nicht nur Existenz."
else
  ok "Alle Factory-Kerndateien vorhanden und keine Platzhalter."
fi

# --- 4. Protected control-plane files (settings.json) ------------------------

SETTINGS_JSON="$ROOT/.claude/settings.json"
if [ -f "$SETTINGS_JSON" ]; then
  SETTINGS_REPORT="$(python3 - "$SETTINGS_JSON" <<'PY'
import json, sys

path = sys.argv[1]
try:
    data = json.loads(open(path, encoding="utf-8").read())
except Exception as exc:  # noqa: BLE001 - reported to the user as-is
    print("ERROR nicht lesbar: %s" % exc)
    raise SystemExit(0)

problems = []

sandbox = data.get("sandbox", {})
if sandbox.get("enabled") is not True:
    problems.append("sandbox.enabled ist nicht true")
if sandbox.get("allowUnsandboxedCommands") is not False:
    problems.append("sandbox.allowUnsandboxedCommands ist nicht false")

# The control plane: everything that decides whether work may proceed, or
# that produces the evidence such a decision rests on. Normal finding work
# must not be able to change any of it (audit finding F-05).
#
# CLAUDE.md and factory/control-plane.sha256 are in these lists because the
# trust-core review found the documentation claiming two-layer protection for
# the whole control plane while those two files had only the server-side
# manifest layer. Either the second layer is real or the claim comes out.
# It is real now.
deny_write = sandbox.get("filesystem", {}).get("denyWrite", [])
for required in [
    "./factory/reviews",
    "./factory/guards",
    "./factory/scripts",
    "./.claude/hooks",
    "./.claude/skills",
    "./.claude/agents",
    "./.claude/rules",
    "./.github/workflows",
    "./.claude/settings.json",
    "./.claude/settings.local.json",
    "./CLAUDE.md",
    "./factory/control-plane.sha256",
]:
    if required not in deny_write:
        problems.append("sandbox.filesystem.denyWrite fehlt: %s" % required)

deny = data.get("permissions", {}).get("deny", [])
for required in [
    "Edit(/factory/reviews/**)",
    "Write(/factory/reviews/**)",
    "Edit(/factory/guards/**)",
    "Write(/factory/guards/**)",
    "Edit(/factory/scripts/**)",
    "Write(/factory/scripts/**)",
    "Edit(/.claude/hooks/**)",
    "Write(/.claude/hooks/**)",
    "Edit(/.claude/skills/**)",
    "Write(/.claude/skills/**)",
    "Edit(/.claude/agents/**)",
    "Write(/.claude/agents/**)",
    "Edit(/.claude/rules/**)",
    "Write(/.claude/rules/**)",
    "Edit(/.github/workflows/**)",
    "Write(/.github/workflows/**)",
    "Edit(/.claude/settings.json)",
    "Write(/.claude/settings.json)",
    "Edit(/CLAUDE.md)",
    "Write(/CLAUDE.md)",
    "Edit(/factory/control-plane.sha256)",
    "Write(/factory/control-plane.sha256)",
]:
    if required not in deny:
        problems.append("permissions.deny fehlt: %s" % required)

# A blanket deny on the routine git/GitHub commands would make every normal
# finding run stop for an approval -- the opposite of ZERO_ROUTINE_APPROVALS.
for forbidden in ["Bash(git push *)", "Bash(gh *)"]:
    if forbidden in deny:
        problems.append(
            "permissions.deny enthaelt %s -- das blockiert die normale, bereits "
            "durch die Factory-Regeln autorisierte Routine" % forbidden
        )

hooks = data.get("hooks", {})
stop_commands = [
    h.get("command", "")
    for entry in hooks.get("Stop", [])
    for h in entry.get("hooks", [])
]
if not any("stop-validate-findings.py" in c for c in stop_commands):
    problems.append("Stop-Hook stop-validate-findings.py ist nicht registriert")

subagent_entries = hooks.get("SubagentStop", [])
matchers = [e.get("matcher") for e in subagent_entries]
if "finding-closure-reviewer" not in matchers:
    problems.append("SubagentStop-Hook ohne matcher 'finding-closure-reviewer'")
else:
    entry = next(e for e in subagent_entries if e.get("matcher") == "finding-closure-reviewer")
    cmds = [h.get("command", "") for h in entry.get("hooks", [])]
    if not any("subagentstop-write-review.py" in c for c in cmds):
        problems.append("SubagentStop-Hook ruft subagentstop-write-review.py nicht auf")

if problems:
    print("PROBLEMS " + " | ".join(problems))
else:
    print("OK")
PY
)"
  case "$SETTINGS_REPORT" in
    OK)
      ok "Geschuetzte Factory-/Review-/Hook-Dateien und Hooks korrekt in .claude/settings.json."
      ;;
    *)
      missing ".claude/settings.json unvollstaendig: ${SETTINGS_REPORT#PROBLEMS }" \
        ".claude/settings.json aus der Factory-Vorlage uebernehmen. Gesperrt sein muss die gesamte Kontrollebene -- factory/reviews, factory/guards, factory/scripts, .claude/hooks, .claude/skills, .claude/agents, .claude/rules, .github/workflows, CLAUDE.md, factory/control-plane.sha256 und die Settings-Dateien selbst -- jeweils per permissions.deny UND sandbox.filesystem.denyWrite; dazu Stop- und SubagentStop-Hook."
      ;;
  esac
fi

# --- 5. Local, machine-specific permissions (settings.local.json) ------------
#
# F-14/E: this used to be a blacklist -- a fixed list of known-broad patterns
# that were rejected, and silence for everything else. A grant the list had
# never heard of therefore passed, which is the wrong default for a file whose
# whole purpose is to widen what an unattended agent may run. The check is now
# positive: every shell grant must be one of the narrow, statically
# recognisable factory routines below, and anything else is reported.

SETTINGS_LOCAL="$ROOT/.claude/settings.local.json"
LOCAL_REPORT="$(python3 - "$SETTINGS_LOCAL" "$ROOT" "$PROJECT_DIR" <<'PY'
import json, os, sys

path, root, project_dir = sys.argv[1], sys.argv[2], sys.argv[3]

required = [
    "Bash(git status*)",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show *)",
    "Bash(git rev-parse *)",
    "Bash(git ls-remote *)",
    "Bash(git branch*)",
    "Bash(git add *)",
    "Bash(git commit *)",
    "Bash(git fetch origin)",
    "Bash(git fetch origin *)",
    "Bash(git push origin *)",
    "Bash(git switch *)",
    "Bash(git worktree *)",
    "Bash(factory/scripts/gh-api.sh *)",
    "Bash(factory/scripts/gh-query.sh *)",
    "Bash(factory/scripts/create-finding-worktree.sh *)",
    "Bash(factory/scripts/factory-preflight.sh*)",
    "Bash(python3 factory/guards/run-factory-checks.py*)",
    "Bash(python3 factory/guards/run-factory-tests.py*)",
    "Bash(python3 factory/guards/run-project-tests.py*)",
    "Bash(python3 factory/guards/validate-finding.py *)",
    "Bash(python3 factory/guards/validate-review.py *)",
    "Bash(python3 factory/guards/validate-build-order.py *)",
    "Bash(python3 factory/guards/finding_state.py *)",
    "Bash(python3 -m unittest factory.guards.*)",
    "Bash(python3 .claude/hooks/test_stop_validate_findings.py*)",
    "Bash(python3 .claude/hooks/test_subagentstop_write_review.py*)",
    "Bash(python3 .claude/hooks/test_sandbox_protects_reviews.py*)",
    "Edit(/factory/findings/**)",
    "Write(/factory/findings/**)",
    "Edit(/factory/build-orders/**)",
    "Write(/factory/build-orders/**)",
    # Deliberately NOT here: write access to factory/guards/ and
    # factory/scripts/. The proven routine never writes there -- it only
    # runs those files. Granting it was audit finding F-05: it let a normal
    # finding change the guards and the CI/merge helper that judge it,
    # without a single approval prompt.
    # Read-only access for the independent finding-closure-reviewer subagent.
    "Read(%s/**)" % root,
]
if os.path.isdir(os.path.join(root, project_dir)):
    required += ["Edit(/%s/**)" % project_dir, "Write(/%s/**)" % project_dir]

# Write access to the control plane is never part of routine work (audit
# finding F-05). A FACTORY_CHANGE is a separate, deliberate workflow -- not
# something a normal finding run should be able to do.
control_plane_write_prefixes = (
    "Edit(/factory/guards/",
    "Write(/factory/guards/",
    "Edit(/factory/scripts/",
    "Write(/factory/scripts/",
    "Edit(/factory/reviews/",
    "Write(/factory/reviews/",
    "Edit(/.claude/",
    "Write(/.claude/",
    "Edit(/.github/",
    "Write(/.github/",
    "Edit(/CLAUDE.md",
    "Write(/CLAUDE.md",
    "Edit(/factory/control-plane.sha256",
    "Write(/factory/control-plane.sha256",
)

if not os.path.isfile(path):
    print("SNIPPET " + json.dumps(required))
    raise SystemExit(0)

try:
    data = json.loads(open(path, encoding="utf-8").read())
except Exception as exc:  # noqa: BLE001
    print("ERROR nicht lesbar: %s" % exc)
    raise SystemExit(0)

allow = data.get("permissions", {}).get("allow", [])
known = set(required)

missing_entries = [entry for entry in required if entry not in allow]

# Positive validation: every shell grant must be one of the narrow factory
# routines. An unrecognised Bash(...) entry is reported rather than ignored --
# "the blacklist had never heard of it" must not mean "it is fine".
control_plane_writes = sorted(
    {entry for entry in allow if entry.startswith(control_plane_write_prefixes)}
)
unknown_bash = sorted(
    {entry for entry in allow if entry.startswith("Bash(") and entry not in known}
)
other_unknown = sorted(
    {
        entry
        for entry in allow
        if entry not in known
        and not entry.startswith("Bash(")
        and entry not in control_plane_writes
    }
)

if control_plane_writes:
    print("BROAD " + " | ".join(control_plane_writes))
elif unknown_bash:
    print("UNKNOWN " + " | ".join(unknown_bash))
elif missing_entries:
    print("SNIPPET " + json.dumps(required))
elif other_unknown:
    print("EXTRA " + " | ".join(other_unknown))
else:
    print("OK")
PY
)"
case "$LOCAL_REPORT" in
  OK)
    ok "Lokale Allows (.claude/settings.local.json) decken die Factory-Routine ab -- keine unbekannten oder breiten Freigaben."
    ;;
  EXTRA*)
    ok "Lokale Allows decken die Factory-Routine ab."
    info "Zusaetzliche, nicht die Shell betreffende Freigaben vorhanden (von der Factory nicht benoetigt): ${LOCAL_REPORT#EXTRA }"
    ;;
  BROAD*)
    missing "Schreibrechte auf die Kontrollebene in .claude/settings.local.json: ${LOCAL_REPORT#BROAD }" \
      "Diese Eintraege aus .claude/settings.local.json entfernen. Normale Finding-Arbeit veraendert die Kontrollebene nie; eine beabsichtigte Aenderung ist ein FACTORY_CHANGE mit eigenem, strengerem Ablauf."
    ;;
  UNKNOWN*)
    missing "Unbekannte Shell-Freigaben in .claude/settings.local.json: ${LOCAL_REPORT#UNKNOWN }" \
      "Diese Eintraege entfernen. Die Factory kommt mit einer festen, engen Liste statisch erkennbarer Befehle aus; jede zusaetzliche Shell-Freigabe erweitert, was ein unbeaufsichtigter Lauf ausfuehren darf, und wird deshalb nicht stillschweigend akzeptiert."
    ;;
  ERROR*)
    missing ".claude/settings.local.json ${LOCAL_REPORT#ERROR }" \
      ".claude/settings.local.json als gueltiges JSON neu schreiben."
    ;;
  SNIPPET*)
    missing ".claude/settings.local.json fehlt oder ist unvollstaendig." \
      "Einmalig .claude/settings.local.json mit dem unten ausgegebenen 'permissions.allow'-Block anlegen (die Datei ist per .gitignore bewusst nicht Teil der Vorlage und wird nur lokal vergeben -- sie kann und darf die Factory sich nicht selbst schreiben)."
    SNIPPET_JSON="${LOCAL_REPORT#SNIPPET }"
    ;;
esac

# --- 6. .gitignore -----------------------------------------------------------

if [ -f "$ROOT/.gitignore" ] && /usr/bin/grep -q "settings.local.json" "$ROOT/.gitignore"; then
  ok ".gitignore haelt .claude/settings.local.json aus der Vorlage heraus."
else
  missing ".claude/settings.local.json ist nicht in .gitignore." \
    "'.claude/settings.local.json' in .gitignore eintragen -- maschinenspezifische Pfade/Rechte gehoeren nie in die Vorlage."
fi

# --- 6b. Control-plane manifest ---------------------------------------------
#
# The server-side half of the F-05 protection: the guards, scripts, hooks,
# rules and CI workflow must match their stamped manifest. Checked here too
# so a fresh copy of the template is verified before the first finding run,
# not only once CI rejects one.

CONTROL_PLANE_GUARD="$ROOT/factory/guards/validate-control-plane.py"
if [ -f "$CONTROL_PLANE_GUARD" ]; then
  if CONTROL_PLANE_OUT="$(python3 "$CONTROL_PLANE_GUARD" --repo-root "$ROOT" 2>&1)"; then
    ok "Control-Plane unveraendert gegenueber factory/control-plane.sha256."
  else
    missing "Control-Plane weicht vom Manifest ab: $(printf '%s' "$CONTROL_PLANE_OUT" | /usr/bin/tr '\n' ' ')" \
      "Pruefen, warum eine Guard-/Skript-/Hook-/Regel-/CI-Datei vom gestempelten Stand abweicht. Ist die Aenderung beabsichtigt, ist sie ein FACTORY_CHANGE (eigener Branch, unabhaengiger Review des Control-Plane-Diffs, menschliche Entscheidung) und wird danach mit 'python3 factory/guards/validate-control-plane.py --update' neu gestempelt."
  fi
else
  missing "Control-Plane-Guard fehlt: factory/guards/validate-control-plane.py" \
    "Datei aus der Factory-Vorlage uebernehmen."
fi

# --- 6c. Does the installed factory actually WORK? (F-14) --------------------
#
# Existence and hashes say a file is the expected one. They do not say the
# factory runs. These two actually execute it. This is the slowest part of the
# preflight by design -- it is a one-time onboarding step, and "the guards run
# and the tests pass here, on this machine, with this Python" is exactly the
# statement a fresh copy needs and that nothing else in this script makes.

CANONICAL_RUNNER="$ROOT/factory/guards/run-factory-checks.py"
if [ -f "$CANONICAL_RUNNER" ]; then
  if RUNNER_OUT="$(python3 "$CANONICAL_RUNNER" 2>&1)"; then
    ok "Kanonischer Runner laeuft und besteht (run-factory-checks.py)."
  else
    missing "Kanonischer Runner schlaegt fehl: $(printf '%s' "$RUNNER_OUT" | /usr/bin/tail -n 3 | /usr/bin/tr '\n' ' ')" \
      "Die gemeldeten Checks reparieren. Solange der kanonische Runner lokal rot ist, ist die Factory nicht einsatzbereit -- CI fuehrt exakt denselben Befehl aus."
  fi
else
  missing "Kanonischer Runner fehlt: factory/guards/run-factory-checks.py" \
    "Datei aus der Factory-Vorlage uebernehmen."
fi

TEST_RUNNER="$ROOT/factory/guards/run-factory-tests.py"
if [ -f "$TEST_RUNNER" ]; then
  TEST_OUT="$(python3 "$TEST_RUNNER" --quiet 2>&1)"
  TEST_RC=$?
  TEST_COUNT="$(printf '%s' "$TEST_OUT" | /usr/bin/awk -F': ' '/^ci_tests_run:/ {print $2}')"
  SANDBOX_STATE="$(printf '%s' "$TEST_OUT" | /usr/bin/awk '/^SANDBOX_VERIFICATION:/ {print $2}')"
  if [ "$TEST_RC" -eq 0 ]; then
    ok "Factory-Testsuite laeuft und besteht (${TEST_COUNT:-?} CI-Tests, automatisch entdeckt)."
  else
    missing "Factory-Testsuite schlaegt fehl: $(printf '%s' "$TEST_OUT" | /usr/bin/tail -n 3 | /usr/bin/tr '\n' ' ')" \
      "Die fehlgeschlagenen Tests reparieren. Eine Factory, deren eigene Guard-Tests rot sind, darf keine Findings schliessen."
  fi
  # F-19, second half: a skipped sandbox test is NOT evidence of a sandbox.
  case "${SANDBOX_STATE:-unbekannt}" in
    performed)
      ok "Sandbox-Verifikation tatsaechlich durchgefuehrt: die OS-Sandbox blockiert Schreibzugriffe auf factory/reviews/."
      ;;
    *)
      info "Sandbox-Verifikation NICHT durchgefuehrt (Zustand: ${SANDBOX_STATE:-unbekannt}). Das ist kein Fehler -- ausserhalb einer aktiven Claude-Code-Sandbox kann sie nicht laufen -- aber dieser Lauf belegt den Sandbox-Schutz damit ausdruecklich NICHT. Zum Nachweis den Preflight aus einer Claude-Code-Session mit aktiver Sandbox ausfuehren."
      ;;
  esac
else
  missing "Test-Runner fehlt: factory/guards/run-factory-tests.py" \
    "Datei aus der Factory-Vorlage uebernehmen."
fi

# --- 7. GitHub / network checks ---------------------------------------------

DEFAULT_BRANCH=""
if [ "$MODE" = "local" ]; then
  skip "Netzwerk-/GitHub-Pruefungen uebersprungen (--local-only)."
elif [ -z "$REPO_SLUG" ]; then
  skip "Netzwerk-/GitHub-Pruefungen nicht moeglich, solange origin kein github.com-Remote ist."
else
  # 7a. Default branch, live from the remote (never the stale local symref).
  DEFAULT_BRANCH="$(git ls-remote --symref origin HEAD 2>/dev/null | /usr/bin/awk '$1 == "ref:" { print $2 }' | /usr/bin/sed 's#^refs/heads/##')"
  if [ -z "$DEFAULT_BRANCH" ]; then
    missing "Default-Branch von origin nicht ermittelbar (kein Zugriff oder leeres Repository)." \
      "Sicherstellen, dass das GitHub-Repository existiert, erreichbar ist und mindestens einen Commit auf seinem Default-Branch hat."
  else
    ok "Default-Branch von origin: $DEFAULT_BRANCH (live ermittelt, nicht geraten)."
  fi

  # 7b. Repo-specific credential -- presence only, never the value, and
  #     explicitly non-interactive (F-20): a missing credential must block,
  #     not open a prompt nobody is there to answer.
  if printf 'protocol=https\nhost=github.com\npath=%s\n\n' "$REPO_SLUG" | GIT_TERMINAL_PROMPT=0 GIT_ASKPASS= SSH_ASKPASS= git -c credential.interactive=false credential fill 2>/dev/null | /usr/bin/grep -q '^password='; then
    ok "GitHub-Credential fuer $REPO_SLUG ueber den git-credential-Helper verfuegbar (Wert wird nicht ausgegeben)."
  else
    missing "Kein GitHub-Credential fuer $REPO_SLUG im git-credential-Helper (nicht-interaktiv geprueft)." \
      "Einmalig ein repo-spezifisches GitHub-Token anlegen (Fine-grained PAT mit Zugriff auf $REPO_SLUG, Rechten: Contents read/write, Pull requests read/write, Actions read, Administration read) und im git-credential-Helper hinterlegen. Diesen Schritt automatisiert die Factory bewusst NICHT -- Tokenerstellung bleibt menschlich."
  fi

  # 7c. GitHub API reachable and the helper layer functional.
  REPO_REPORT="$("$ROOT/factory/scripts/gh-query.sh" repo 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("UNREADABLE")
    raise SystemExit(0)
if not isinstance(data, dict) or "full_name" not in data:
    print("ERROR")
    raise SystemExit(0)
perms = data.get("permissions") or {}
print("OK %s %s %s" % (data.get("full_name"), data.get("default_branch"), "push" if perms.get("push") else "nopush"))
' 2>/dev/null)"
  case "$REPO_REPORT" in
    OK*)
      set -- $REPO_REPORT
      API_FULL_NAME="$2"
      API_DEFAULT_BRANCH="$3"
      API_PUSH="$4"
      ok "GitHub-API erreichbar, gh-api.sh funktioniert: $API_FULL_NAME"
      if [ "$API_PUSH" = "push" ]; then
        ok "Token darf auf $API_FULL_NAME schreiben (Contents) -- Branch-Push moeglich."
      else
        missing "Token hat keine Schreibrechte (Contents) auf $API_FULL_NAME." \
          "Dem Token 'Contents: read/write' fuer $REPO_SLUG geben."
      fi
      if [ -n "$DEFAULT_BRANCH" ] && [ "$API_DEFAULT_BRANCH" != "$DEFAULT_BRANCH" ]; then
        missing "Default-Branch laut GitHub ($API_DEFAULT_BRANCH) weicht vom Remote-HEAD ($DEFAULT_BRANCH) ab." \
          "Default-Branch in den GitHub-Repository-Einstellungen und den Remote-HEAD in Einklang bringen."
      fi
      ;;
    *)
      missing "GitHub-API ueber gh-api.sh nicht nutzbar (${REPO_REPORT:-keine Antwort})." \
        "Netzwerkzugang und Token pruefen. gh ist NICHT erforderlich -- gh-api.sh nutzt nur git-credential und curl."
      ;;
  esac

  # 7d. Pull-request permission, probed WITHOUT creating anything (F-12).
  #
  # Contents:write is NOT the same token permission as "Pull requests: write":
  # pushing a finding branch can succeed while POST /pulls is refused --
  # observed in practice, and only at the moment the factory wanted to open
  # its pull request. The probe itself lives in gh-query.sh/gh_evidence.py so
  # it can be regression-tested without a network, and it recognises the
  # permission only from GitHub's own validation error. Every other answer --
  # 401, 404, a rate limit, an empty body, something new -- is blocked.
  if [ -n "$DEFAULT_BRANCH" ]; then
    PROBE_OUT="$("$ROOT/factory/scripts/gh-query.sh" pr-permission-probe "$DEFAULT_BRANCH" 2>/dev/null)"
    PROBE_RC=$?
    PROBE_VERDICT="$(printf '%s' "$PROBE_OUT" | /usr/bin/awk -F': ' '/^probe:/ {print $2}')"
    if [ "$PROBE_RC" -eq 0 ] && [ "$PROBE_VERDICT" = "permitted" ]; then
      ok "Token darf Pull Requests erstellen (geprueft ohne einen PR anzulegen)."
    elif [ "$PROBE_VERDICT" = "created" ]; then
      missing "Unerwartet: die PR-Probe hat einen Pull Request erzeugt." \
        "Diesen unerwartet erzeugten Pull Request auf $REPO_SLUG pruefen und schliessen. Danach klaeren, warum head == base einen PR erzeugen konnte -- das darf nicht passieren."
    else
      missing "PR-Berechtigung nicht bestaetigt (Urteil: ${PROBE_VERDICT:-unbekannt}, Exit $PROBE_RC): $(printf '%s' "$PROBE_OUT" | /usr/bin/tr '\n' ' ')" \
        "Dem GitHub-Token die Berechtigung 'Pull requests: read/write' fuer $REPO_SLUG geben (Fine-grained PAT: Repository permissions -> Pull requests). 'Contents: read/write' allein genuegt nicht -- damit gelingt der Push, aber nicht der PR. Bei 401/404 Token und Repository-Zugriff pruefen. Eine nicht eindeutig bestaetigte Berechtigung gilt als fehlend."
    fi
  fi

  # 7e. gh-query.sh functional (the fixed, approval-free summary layer).
  QUERY_BRANCH="$("$ROOT/factory/scripts/gh-query.sh" default-branch 2>/dev/null | /usr/bin/awk '/^default_branch:/ { print $2 }')"
  if [ -n "$QUERY_BRANCH" ]; then
    ok "gh-query.sh funktioniert (default-branch: $QUERY_BRANCH)."
  else
    missing "gh-query.sh liefert keine verwertbare Antwort." \
      "gh-query.sh manuell pruefen: 'factory/scripts/gh-query.sh repo'."
  fi

  if [ -n "$DEFAULT_BRANCH" ]; then
    # 7f. CI readable.
    if "$ROOT/factory/scripts/gh-query.sh" actions-run-summary "$DEFAULT_BRANCH" >/dev/null 2>&1; then
      ok "CI-Laeufe sind lesbar (Actions-API ueber gh-query.sh)."
    else
      missing "Actions-Laeufe nicht lesbar." \
        "Dem Token 'Actions: read' fuer $REPO_SLUG geben."
    fi

    # 7g. Branch protection, read SEMANTICALLY from both sources (F-13).
    #
    # A branch may be protected by a ruleset, by classic branch protection, or
    # by both. Counting rules -- what this used to do -- cannot tell a full
    # protection from a lone force-push rule, and reading only one source
    # reports "kein Schutz" for a branch that is in fact protected.
    RULESET_OUT="$("$ROOT/factory/scripts/gh-query.sh" ruleset-guarantees "$DEFAULT_BRANCH" "$REQUIRED_CHECK" 2>/dev/null)"
    RULESET_RC=$?
    CLASSIC_OUT="$("$ROOT/factory/scripts/gh-query.sh" classic-protection "$DEFAULT_BRANCH" "$REQUIRED_CHECK" 2>/dev/null)"
    CLASSIC_RC=$?

    if [ "$RULESET_RC" -ne 0 ] && [ "$CLASSIC_RC" -ne 0 ]; then
      missing "Branch-Schutz fuer $DEFAULT_BRANCH nicht lesbar (Ruleset-Exit $RULESET_RC, Classic-Exit $CLASSIC_RC)." \
        "Dem Token 'Administration: read' fuer $REPO_SLUG geben, damit die Factory den Schutz verifizieren kann. Ein nicht lesbarer Schutz gilt als nicht vorhanden -- nicht als vorhanden."
    else
      PROTECTION_TEXT="$RULESET_OUT
$CLASSIC_OUT"
      PR_REQUIRED="$(printf '%s' "$PROTECTION_TEXT" | /usr/bin/grep -c '^pull_request_required: true' || true)"
      CHECK_PRESENT="$(printf '%s' "$PROTECTION_TEXT" | /usr/bin/grep -c '^required_check_present: true' || true)"
      APPROVALS="$(printf '%s' "$PROTECTION_TEXT" | /usr/bin/awk -F': ' '/^required_approving_review_count:/ {if ($2+0 > max) max=$2+0} END {print max+0}')"

      if [ "${PR_REQUIRED:-0}" -gt 0 ]; then
        ok "Pull Request vor Merge ist auf $DEFAULT_BRANCH erforderlich."
      else
        missing "Auf $DEFAULT_BRANCH ist kein Pull Request vor dem Merge erforderlich." \
          "Einmalig in GitHub ein Ruleset (oder klassische Branch Protection) fuer $DEFAULT_BRANCH anlegen mit 'Require a pull request before merging'. Ohne diese Regel kann direkt auf den Default-Branch gepusht werden und der gesamte Review-/CI-Pfad ist umgehbar. Dieser Admin-Schritt bleibt bewusst menschlich."
      fi

      if [ "${CHECK_PRESENT:-0}" -gt 0 ]; then
        ok "Required Status Check '$REQUIRED_CHECK' ist auf $DEFAULT_BRANCH konfiguriert."
      else
        missing "Required Status Check '$REQUIRED_CHECK' fehlt auf $DEFAULT_BRANCH." \
          "Im Ruleset fuer $DEFAULT_BRANCH unter 'Require status checks to pass' den Check '$REQUIRED_CHECK' (Job-Name aus .github/workflows/factory-ci.yml) eintragen. Erst dadurch blockiert ein roter CI-Lauf den Merge wirklich."
      fi

      if [ "${APPROVALS:-0}" -gt 0 ]; then
        governance "Auf $DEFAULT_BRANCH sind $APPROVALS Approval(s) erforderlich -- ein unbeaufsichtigter Merge durch die Factory ist damit nicht moeglich." \
          "Das ist eine Governance-Entscheidung, kein technisches Problem, und wird ausdruecklich NICHT umgangen. Zwei zulaessige Wege: (a) die Approval-Pflicht fuer den Automatisierungspfad bewusst aufheben, wenn der unabhaengige Reviewer plus Required Status Check als ausreichend gelten; oder (b) sie beibehalten und akzeptieren, dass die Factory vor dem Merge stoppt und der letzte Schritt menschlich bleibt. In Fall (b) ist dieser Preflight nie PASS -- und das ist die richtige Aussage, nicht ein Mangel."
      else
        ok "Keine erforderlichen Approvals -- ein autonomer Merge des gruenen Pull Requests ist moeglich."
      fi
    fi
  fi
fi

# --- Result ------------------------------------------------------------------

echo
if [ "$BLOCKERS" -gt 0 ]; then
  echo "FACTORY_PREFLIGHT: BLOCKED ($BLOCKERS offene Voraussetzung(en))"
  echo
  echo "Einmalige Schritte, die ein Mensch ausfuehren muss -- danach diesen Preflight erneut laufen lassen:"
  i=1
  for step in "${STEPS[@]}"; do
    printf '  %d. %s\n' "$i" "$step"
    i=$((i + 1))
  done

  if [ -n "${SNIPPET_JSON:-}" ]; then
    echo
    echo "Vorschlag fuer .claude/settings.local.json (maschinenspezifisch, nicht committen):"
    python3 -c '
import json, sys
print(json.dumps({"permissions": {"allow": json.loads(sys.argv[1])}}, indent=2, ensure_ascii=False))
' "$SNIPPET_JSON"
  fi

  exit 1
fi

# F-11: an unchecked layer is not a passed layer. --local-only deliberately
# never reaches PASS, and its exit code is not 0, so neither a caller nor a
# script can read "the local checks passed" as "the factory is ready".
if [ "$MODE" = "local" ]; then
  echo "FACTORY_PREFLIGHT: PARTIAL"
  echo "Geprueft wurde ausschliesslich die LOKALE Ebene: Repository, Factory-Dateien,"
  echo "Berechtigungen, Control-Plane-Manifest, kanonischer Runner und Testsuite."
  echo "NICHT geprueft wurde die GitHub-/Remote-Ebene: Credential, API-Zugriff,"
  echo "PR-Berechtigung, Lesbarkeit der CI, Branch-Schutz und Required Status Check."
  echo "Ueber die Bereitschaft fuer unbeaufsichtigte Laeufe sagt dieses Ergebnis daher"
  echo "nichts aus. Fuer ein vollstaendiges Urteil ohne --local-only ausfuehren."
  exit 3
fi

echo "FACTORY_PREFLIGHT: PASS"
echo "Lokale UND GitHub-/Remote-Ebene geprueft. Normale Finding-Arbeit (Branch, Commit,"
echo "Push, PR, CI-Abfrage, Merge, Review) laeuft ohne Routine-Approvals."
exit 0
