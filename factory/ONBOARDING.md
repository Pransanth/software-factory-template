# Factory-Onboarding: einmalig einrichten, danach unbeaufsichtigt arbeiten

Diese Datei beschreibt, was ein Mensch **ein einziges Mal** pro Projekt tun muss, damit ein
normaler Finding-Lauf danach ohne Approval-, GitHub- und Berechtigungs-Odyssee durchläuft.

Der Prüfteil ist ein Skript:

```
factory/scripts/factory-preflight.sh
factory/scripts/factory-preflight.sh --local-only   # ohne Netz/GitHub
```

Es endet mit genau einem von drei Ergebnissen:

| Ergebnis | Exit | Bedeutung |
|---|---|---|
| `FACTORY_PREFLIGHT: PASS` | 0 | Lokale **und** GitHub-/Remote-Ebene geprüft; unbeaufsichtigte Läufe sind bereit. |
| `FACTORY_PREFLIGHT: BLOCKED` | 1 | Mindestens eine Voraussetzung fehlt, jede mit dem exakten einmaligen Schritt. |
| `FACTORY_PREFLIGHT: PARTIAL` | 3 | Nur bei `--local-only`: lokal in Ordnung, GitHub-Ebene **nicht geprüft**. Kein PASS. |

`PARTIAL` ist die Korrektur eines Audit-Befunds (F-11): `--local-only` meldete früher `PASS` und
„unbeaufsichtigte Läufe sind bereit", obwohl sämtliche GitHub-Prüfungen übersprungen wurden. Eine
nicht geprüfte Ebene ist keine bestandene Ebene.

Meldet der Preflight einen `[GOVERNANCE]`-Punkt — praktisch: erforderliche Approvals auf dem
Default-Branch —, ist das keine technische Aufgabe, sondern eine Entscheidung des Projektinhabers.
Sie wird **nicht** technisch umgangen; siehe die Erklärung im Skript.

Das Skript **verändert nichts**: es legt kein Repository an, erzeugt kein Token, konfiguriert kein
Ruleset, schreibt keine Berechtigungen und erstellt keinen PR. Es prüft, erklärt — und wird danach
erneut ausgeführt. Es **führt** allerdings die installierte Factory aus (Control-Plane-Guard,
kanonischer Runner, entdeckte Testsuite), damit „vorhanden" nicht mit „funktionsfähig" verwechselt
wird; dieser Teil dauert je nach Projektgröße etwas.

## Was der Preflight prüft

| # | Prüfung | Warum |
|---|---|---|
| 1 | Eigenständiges Git-Repository | Die Factory arbeitet auf ihrem eigenen Repo, nicht als Unterverzeichnis eines fremden. |
| 2 | `origin` vorhanden und auf github.com | PR, CI und Merge laufen über die GitHub-REST-API. |
| 3 | Factory-Kerndateien vollständig | Guards, Hooks, Reviewer, Skill, CI, Regeln. |
| 4 | Geschützte Kontrollebene in `.claude/settings.json` | `factory/reviews/`, `factory/guards/`, `factory/scripts/`, `.claude/hooks/`, `.claude/skills/`, `.claude/agents/`, `.claude/rules/`, `.github/workflows/` und die Settings-Dateien sind gegen Selbstveränderung gesperrt (`permissions.deny` **und** `sandbox.filesystem.denyWrite`); Stop- und SubagentStop-Hook sind registriert; die Routine ist **nicht** pauschal verboten. |
| 5 | Lokale Allows in `.claude/settings.local.json` | Genau die Befehlsformen der Factory-Routine — eng gefasst, keine breiten `Bash(*)`/`curl`/`python3`-Freigaben und **kein** Schreibzugriff auf die Kontrollebene; dazu der read-only `Read(<repo>/**)`-Zugriff für den unabhängigen Reviewer. |
| 6 | `.gitignore` schließt `settings.local.json` aus | Maschinenspezifische Pfade gehören nie in die Vorlage. |
| 6b | Control-Plane-Manifest aktuell | `factory/control-plane.sha256` muss zum tatsächlichen Stand der Guards, Skripte, Hooks, Regeln und CI passen. Weicht etwas ab, ist entweder die Kopie unvollständig oder jemand hat die Kontrollebene verändert. |
| 7 | Default-Branch live vom Remote ermittelbar | Kein geratener Branchname; Konvention ist `origin/<default-branch>`. |
| 8 | Repo-spezifisches GitHub-Credential | `gh-api.sh` nutzt den git-credential-Helper; der Wert wird nie ausgegeben. |
| 9 | GitHub-API erreichbar, `gh-api.sh` funktioniert | Ohne `gh`-CLI. |
| 10 | Schreibrechte des Tokens (Contents) | Ohne sie schlägt schon `git push origin <branch>` fehl. |
| 10b | PR-Erstellung erlaubt | Eigene Prüfung, weil `Contents: write` **nicht** `Pull requests: write` einschließt: der Push kann gelingen und `POST /pulls` trotzdem mit 403 abgelehnt werden (real beobachtet, und zwar erst in dem Moment, in dem die Factory ihren PR eröffnen wollte). Geprüft wird gegen den echten Endpunkt mit `head == base` — daraus kann GitHub niemals einen PR machen. |
| 11 | `gh-query.sh` funktioniert | Die feste, approval-freie Abfrageschicht. |
| 12 | CI-Läufe lesbar | Ohne CI-Lesbarkeit gibt es keine echte `CI Evidence`. |
| 13 | Branch-Schutz/Ruleset auf dem Default-Branch | Sonst ist der Merge-Gate nur Behauptung. |
| 14 | Required Status Check `factory-checks` konfiguriert | Erst dadurch blockiert ein roter CI-Lauf den Merge wirklich. |

## Die einmaligen menschlichen Schritte

Diese Schritte automatisiert die Factory **bewusst nicht**. Sie vergeben Rechte oder erzeugen
Geheimnisse; sie unsicher zu automatisieren wäre schlimmer als sie einmal von Hand zu tun. Der
Preflight nennt jeweils exakt den fehlenden Schritt — es ist keine technische Scheinentscheidung
zu treffen, sondern eine konkrete Einrichtung durchzuführen.

1. **GitHub-Repository + `origin`.**
   `git init`, erster Commit, Repository auf GitHub anlegen,
   `git remote add origin https://github.com/<OWNER>/<REPO>.git`, einmal pushen.

2. **Repo-spezifisches Token.** Ein Fine-grained Personal Access Token, das **nur** auf dieses
   Repository Zugriff hat, mit: `Contents: read/write`, `Pull requests: read/write`,
   `Actions: read`, `Administration: read`. Alle vier werden gebraucht — insbesondere ist
   `Pull requests: read/write` **zusätzlich** zu `Contents: read/write` nötig: ohne sie
   funktioniert `git push`, aber die PR-Erstellung wird mit 403 abgelehnt. Es wird im git-credential-Helper hinterlegt (z. B.
   beim ersten `git push` über HTTPS). Empfehlenswert, damit mehrere Projekte auf derselben
   Maschine getrennte Tokens verwenden können:
   `git config --global credential.https://github.com.useHttpPath true` — `gh-api.sh` fragt das
   Credential passend dazu mit `path` an. Die Factory braucht darüber hinaus **keine** globale
   Git- oder Claude-Konfiguration.

3. **Branch-Schutz + Required Status Check.** In GitHub ein Ruleset für den Default-Branch:
   *Require a pull request before merging* und *Require status checks to pass* mit dem Check
   **`factory-checks`** (Job-Name aus `.github/workflows/factory-ci.yml`). Ohne diesen Eintrag
   prüft CI zwar, blockiert aber keinen Merge.

4. **Lokale Berechtigungen.** `.claude/settings.local.json` einmalig mit dem Block anlegen, den
   der Preflight ausgibt. Diese Datei ist bewusst per `.gitignore` **nicht** Teil der Vorlage
   (sie enthält den absoluten Pfad dieser Maschine), und die Factory schreibt sie sich
   ausdrücklich **nicht** selbst — eine Instanz, die sich ihre eigenen Rechte erteilt, ist keine
   Kontrolle. Der Vorschlag ist bewusst eng: jede Zeile entspricht genau einer Befehlsform, die
   die Factory-Routine tatsächlich verwendet.

Nach jedem dieser Schritte: **Preflight erneut ausführen**, bis `FACTORY_PREFLIGHT: PASS`.

## Was danach ohne Rückfrage läuft (ZERO_ROUTINE_APPROVALS)

Ist der Preflight grün, läuft die normale Finding-Arbeit unbeaufsichtigt durch:

- Finding anlegen/aktualisieren, Bauauftrag schreiben
- Finding-Branch (`git switch --no-track -c … origin/<default-branch>`) bzw. Finding-Worktree
  über `create-finding-worktree.sh`
- Regressionstest zuerst rot, dann Fix, dann grün
- Guards und kanonischer Runner (`run-factory-checks.py`), Projekttests
  (`run-project-tests.py`)
- `git add` / `git commit` / `git fetch origin` / `git push origin <branch>`
- PR erstellen (`gh-query.sh pr-create`), Status abfragen (`pr-summary`,
  `check-runs-summary`, `actions-run-summary`, `actions-jobs-summary`)
- Required Check für genau einen SHA prüfen (`gh-query.sh required-check <SHA>`)
- unabhängiges Review (`finding-closure-reviewer`) mit Review-Artefakt aus dem SubagentStop-Hook
- `READY_FOR_CLOSURE` → `CLOSED`
- Merge bei grünem Required Status Check und passendem Head-SHA
  (`gh-query.sh merge <PR> <METHOD> <SHA>`) und Verifikation des Remote-Stands

Was ebenfalls **nicht** ohne Weiteres läuft: jede Änderung an der Kontrollebene (Guards, Skripte,
Hooks, Agent, Skills, Regeln, CI-Workflow, `CLAUDE.md`). Das ist ein `FACTORY_CHANGE` mit eigenem,
strengerem Ablauf — siehe [`.claude/rules/factory-workflow.md`](../.claude/rules/factory-workflow.md).

Was **nicht** ohne Weiteres läuft und auch nicht laufen soll: P0, `EXPERT_REVIEW_REQUIRED`, echte
Produkt-/Scope-Entscheidungen und `AUTONOMY_BLOCKER` — siehe `CLAUDE.md`, "Wann die Factory
wirklich stoppt".

## Umzug auf ein neues Projekt

1. Inhalt dieser Vorlage in das neue Repository kopieren (ohne `.claude/settings.local.json` —
   die ist maschinenspezifisch).
2. `factory/scripts/factory-preflight.sh` ausführen und den vier Schritten oben folgen.
3. Produktcode ergänzen (per Konvention `app/`, sonst
   `python3 factory/guards/run-project-tests.py --project-dir <dir>` bzw.
   `FACTORY_PROJECT_DIR=<dir>` für den Preflight).
4. Projektspezifische Guards ergänzen: eigene `factory/guards/validate-*.py` plus ein Aufruf in
   `run-factory-checks.py`. Die Vorlage enthält bewusst keine produktspezifischen Guards.
