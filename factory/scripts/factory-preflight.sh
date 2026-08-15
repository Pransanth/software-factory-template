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
# remote (never from the stale local refs/remotes/origin/HEAD symref).
#
# Usage:
#   factory/scripts/factory-preflight.sh              # all checks
#   factory/scripts/factory-preflight.sh --local-only # skip network/GitHub checks
#
# Exit code 0: FACTORY_PREFLIGHT: PASS -- unattended finding runs are ready.
# Exit code 1: FACTORY_PREFLIGHT: BLOCKED -- at least one one-time
#              prerequisite is missing; each one is printed with the exact
#              step needed.
# Exit code 2: usage error.
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
    https://github.com/*|git@github.com:*)
      REPO_SLUG="$(printf '%s' "$ORIGIN_URL" | sed -E 's#^(https://github\.com/|git@github\.com:)##; s#\.git$##')"
      ok "origin zeigt auf GitHub: $REPO_SLUG"
      ;;
    *)
      missing "origin ist kein github.com-Remote ($ORIGIN_URL)." \
        "Die Factory-GitHub-Helfer (gh-api.sh/gh-query.sh) sprechen die GitHub-REST-API an. origin auf ein github.com-Repository umstellen."
      ;;
  esac
fi

# --- 3. Factory files present ------------------------------------------------

REQUIRED_FILES=(
  "factory/guards/run-factory-checks.py"
  "factory/guards/validate-finding.py"
  "factory/guards/validate-review.py"
  "factory/guards/validate-control-plane.py"
  "factory/guards/scope_hash.py"
  "factory/guards/gh_evidence.py"
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
for rel in "${REQUIRED_FILES[@]}"; do
  if [ ! -f "$ROOT/$rel" ]; then
    MISSING_FILES="$MISSING_FILES $rel"
  fi
done
if [ -n "$MISSING_FILES" ]; then
  missing "Factory-Dateien fehlen:$MISSING_FILES" \
    "Fehlende Dateien aus der Factory-Vorlage uebernehmen:$MISSING_FILES"
else
  ok "Alle Factory-Kerndateien vorhanden."
fi

# --- 4. Protected factory/review/hook files (settings.json) ------------------

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
        ".claude/settings.json aus der Factory-Vorlage uebernehmen. Gesperrt sein muss die gesamte Kontrollebene -- factory/reviews, factory/guards, factory/scripts, .claude/hooks, .claude/skills, .claude/agents, .claude/rules, .github/workflows und die Settings-Dateien selbst -- jeweils per permissions.deny UND sandbox.filesystem.denyWrite; dazu Stop- und SubagentStop-Hook."
      ;;
  esac
fi

# --- 5. Local, machine-specific permissions (settings.local.json) ------------

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
    "Bash(python3 factory/guards/run-project-tests.py*)",
    "Bash(python3 factory/guards/validate-finding.py *)",
    "Bash(python3 factory/guards/validate-review.py *)",
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

# Grants that would be far broader than the factory needs. The proven setup
# does not require any of these: every helper runs as one narrow, statically
# recognizable command.
too_broad = [
    "Bash(*)",
    "Bash(curl *)",
    "Bash(python3 *)",
    "Bash(python3 -)",
    "Bash(python *)",
    "Bash(git *)",
    "Bash(git -C *)",
    "Bash(bash *)",
    "Bash(sh *)",
    "Bash(zsh *)",
    "Bash(gh *)",
    # Write access to the control plane is never part of routine work
    # (audit finding F-05). A FACTORY_CHANGE is a separate, deliberate
    # workflow -- not something a normal finding run should be able to do.
    "Edit(/factory/guards/**)",
    "Write(/factory/guards/**)",
    "Edit(/factory/scripts/**)",
    "Write(/factory/scripts/**)",
    "Edit(/.claude/**)",
    "Write(/.claude/**)",
    "Edit(/.github/**)",
    "Write(/.github/**)",
]

if not os.path.isfile(path):
    print("SNIPPET " + json.dumps(required))
    raise SystemExit(0)

try:
    data = json.loads(open(path, encoding="utf-8").read())
except Exception as exc:  # noqa: BLE001
    print("ERROR nicht lesbar: %s" % exc)
    raise SystemExit(0)

allow = data.get("permissions", {}).get("allow", [])
missing_entries = [entry for entry in required if entry not in allow]
broad_entries = [entry for entry in allow if entry in too_broad]

if broad_entries:
    print("BROAD " + " | ".join(broad_entries))
elif missing_entries:
    print("SNIPPET " + json.dumps(required))
else:
    print("OK")
PY
)"
case "$LOCAL_REPORT" in
  OK)
    ok "Lokale Allows (.claude/settings.local.json) decken die Factory-Routine ab -- keine breiten Freigaben."
    ;;
  BROAD*)
    missing "Zu breite lokale Freigaben: ${LOCAL_REPORT#BROAD }" \
      "Breite Muster aus .claude/settings.local.json entfernen. Die Factory braucht sie nicht: jeder Helfer laeuft als ein einzelner, eng gefasster Befehl."
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

if [ -f "$ROOT/.gitignore" ] && grep -q "settings.local.json" "$ROOT/.gitignore"; then
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

# --- 7. GitHub / network checks ---------------------------------------------

DEFAULT_BRANCH=""
if [ "$MODE" = "local" ]; then
  skip "Netzwerk-/GitHub-Pruefungen uebersprungen (--local-only)."
elif [ -z "$REPO_SLUG" ]; then
  skip "Netzwerk-/GitHub-Pruefungen nicht moeglich, solange origin kein github.com-Remote ist."
else
  # 7a. Default branch, live from the remote (never the stale local symref).
  DEFAULT_BRANCH="$(git ls-remote --symref origin HEAD 2>/dev/null | awk '$1 == "ref:" { print $2 }' | sed 's#^refs/heads/##')"
  if [ -z "$DEFAULT_BRANCH" ]; then
    missing "Default-Branch von origin nicht ermittelbar (kein Zugriff oder leeres Repository)." \
      "Sicherstellen, dass das GitHub-Repository existiert, erreichbar ist und mindestens einen Commit auf seinem Default-Branch hat."
  else
    ok "Default-Branch von origin: $DEFAULT_BRANCH (live ermittelt, nicht geraten)."
  fi

  # 7b. Repo-specific credential -- presence only, never the value.
  CRED_PATH="$(printf '%s' "$ORIGIN_URL" | sed -E 's#^(https://github\.com/|git@github\.com:)##')"
  if printf 'protocol=https\nhost=github.com\npath=%s\n\n' "$CRED_PATH" | git credential fill 2>/dev/null | grep -q '^password='; then
    ok "GitHub-Credential fuer $CRED_PATH ueber den git-credential-Helper verfuegbar (Wert wird nicht ausgegeben)."
  else
    missing "Kein GitHub-Credential fuer $CRED_PATH im git-credential-Helper." \
      "Einmalig ein repo-spezifisches GitHub-Token anlegen (Fine-grained PAT mit Zugriff auf $REPO_SLUG, Rechten: Contents read/write, Pull requests read/write, Actions read, Administration read) und im git-credential-Helper hinterlegen. Diesen Schritt automatisiert die Factory bewusst NICHT -- Tokenerstellung bleibt menschlich."
  fi

  # 7c. GitHub API reachable and gh-api.sh functional.
  API_REPORT="$("$ROOT/factory/scripts/gh-api.sh" GET "" 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("UNREADABLE")
    raise SystemExit(0)
if not isinstance(data, dict) or "full_name" not in data:
    print("ERROR " + str(data.get("message", "unerwartete Antwort") if isinstance(data, dict) else "unerwartete Antwort"))
    raise SystemExit(0)
perms = data.get("permissions") or {}
print("OK %s %s %s" % (data.get("full_name"), data.get("default_branch"), "push" if perms.get("push") else "nopush"))
' 2>/dev/null)"
  case "$API_REPORT" in
    OK*)
      set -- $API_REPORT
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
      missing "GitHub-API ueber gh-api.sh nicht nutzbar (${API_REPORT:-keine Antwort})." \
        "Netzwerkzugang und Token pruefen. gh ist NICHT erforderlich -- gh-api.sh nutzt nur git-credential und curl."
      ;;
  esac

  # 7d. PR creation permission, probed WITHOUT creating anything.
  #
  # Contents:write (checked above) is NOT the same permission as
  # "Pull requests: write" on a fine-grained token: pushing a finding branch
  # can succeed while POST /pulls is refused -- observed in practice, and
  # only at the moment the factory wanted to open its PR. Onboarding has to
  # catch that earlier, so this probes the real endpoint with head == base:
  # such a request can never create a pull request, and GitHub checks token
  # permission before it validates the payload. A refusal therefore means
  # "permission missing", any other answer (a validation error) means the
  # permission is there.
  if [ -n "$DEFAULT_BRANCH" ]; then
    PR_PROBE="$("$ROOT/factory/scripts/gh-api.sh" POST /pulls "{\"title\":\"factory-preflight permission probe (cannot create a PR: head == base)\",\"head\":\"$DEFAULT_BRANCH\",\"base\":\"$DEFAULT_BRANCH\"}" 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("UNREADABLE")
    raise SystemExit(0)
if not isinstance(data, dict):
    print("UNREADABLE")
    raise SystemExit(0)
if data.get("number"):
    print("CREATED")
elif "not accessible" in str(data.get("message", "")) or str(data.get("status")) == "403":
    print("FORBIDDEN")
else:
    print("PERMITTED")
' 2>/dev/null)"
    case "$PR_PROBE" in
      PERMITTED)
        ok "Token darf Pull Requests erstellen (geprueft ohne einen PR anzulegen)."
        ;;
      FORBIDDEN)
        missing "Token darf keine Pull Requests auf $REPO_SLUG erstellen." \
          "Dem GitHub-Token die Berechtigung 'Pull requests: read/write' fuer $REPO_SLUG geben (Fine-grained PAT: Repository permissions -> Pull requests). 'Contents: read/write' allein genuegt nicht -- damit gelingt der Push, aber nicht der PR."
        ;;
      CREATED)
        missing "Unerwartet: die PR-Probe hat einen Pull Request erzeugt." \
          "Diesen unerwartet erzeugten Pull Request auf $REPO_SLUG pruefen und schliessen."
        ;;
      *)
        missing "PR-Berechtigung nicht pruefbar (keine verwertbare API-Antwort)." \
          "Netzwerkzugang und Token pruefen und den Preflight erneut ausfuehren."
        ;;
    esac
  fi

  # 7e. gh-query.sh functional (the fixed, approval-free summary layer).
  QUERY_BRANCH="$("$ROOT/factory/scripts/gh-query.sh" default-branch 2>/dev/null | awk '/^default_branch:/ { print $2 }')"
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

    # 7g. Branch protection / ruleset on the default branch.
    RULES_REPORT="$("$ROOT/factory/scripts/gh-query.sh" branch-rules "$DEFAULT_BRANCH" 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("UNREADABLE")
    raise SystemExit(0)
if isinstance(data, list):
    print("COUNT %d" % len(data))
else:
    print("ERROR")
' 2>/dev/null)"
    case "$RULES_REPORT" in
      "COUNT 0")
        missing "Kein Schutz (Ruleset/Branch-Protection) auf $DEFAULT_BRANCH aktiv." \
          "Einmalig in GitHub ein Ruleset fuer $DEFAULT_BRANCH anlegen (Ziel: Default-Branch; Regeln: 'Require a pull request before merging' und 'Require status checks to pass'). Dieser Admin-Schritt bleibt bewusst menschlich."
        ;;
      COUNT*)
        ok "Branch-Schutz auf $DEFAULT_BRANCH aktiv (${RULES_REPORT#COUNT } Regel(n))."
        ;;
      *)
        missing "Branch-Regeln fuer $DEFAULT_BRANCH nicht lesbar." \
          "Dem Token 'Administration: read' fuer $REPO_SLUG geben, damit die Factory den Schutz verifizieren kann."
        ;;
    esac

    # 7h. Required status check must name the factory CI job.
    REQUIRED_OUT="$("$ROOT/factory/scripts/gh-query.sh" required-checks "$DEFAULT_BRANCH" 2>/dev/null)"
    if printf '%s' "$REQUIRED_OUT" | grep -q "required_status_check: $REQUIRED_CHECK"; then
      ok "Required Status Check '$REQUIRED_CHECK' ist auf $DEFAULT_BRANCH konfiguriert."
    else
      missing "Required Status Check '$REQUIRED_CHECK' fehlt auf $DEFAULT_BRANCH." \
        "Im Ruleset fuer $DEFAULT_BRANCH unter 'Require status checks to pass' den Check '$REQUIRED_CHECK' (Job-Name aus .github/workflows/factory-ci.yml) eintragen. Erst dadurch blockiert ein roter CI-Lauf den Merge wirklich."
    fi
  fi
fi

# --- Result ------------------------------------------------------------------

echo
if [ "$BLOCKERS" -eq 0 ]; then
  echo "FACTORY_PREFLIGHT: PASS"
  echo "Normale Finding-Arbeit (Branch, Commit, Push, PR, CI-Abfrage, Merge, Review) laeuft ohne Routine-Approvals."
  exit 0
fi

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
