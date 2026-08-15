# Software Factory – Leitplanken für Claude

Dieses Repository ist die übertragbare Vorlage einer "Software Factory": ein wiederholbarer
Prozess, mit dem Sicherheitsbefunde (und später andere technische Arbeit) kontrolliert von der
Meldung bis zum Abschluss durchlaufen — mit klaren Zuständen und Guards, die die Regeln
unabhängig von jeder einzelnen Claude-Anweisung durchsetzen.

Der Anspruch der Vorlage ist nicht "Claude darf alles", sondern: **normale Finding-Arbeit läuft
unbeaufsichtigt und ohne Routine-Rückfragen durch, und genau die wenigen echten
Entscheidungspunkte stoppen.**

## Aktueller Stand dieser Vorlage

Die Vorlage enthält ausschließlich Factory-Infrastruktur: Workflow-Definition, Guards, Hooks,
den unabhängigen Reviewer, die GitHub-/CI-Helfer, den Onboarding-Preflight und ein
Beispiel-Finding als Formatvorlage. Es gibt **keinen** Produktcode und **keinen** echten Fix.
Solange nichts anderes vereinbart ist:

- Baue keine Anwendung "auf Verdacht".
- Analysiere oder repariere das Beispiel-Finding nicht technisch — es ist bewusst nur eine
  Formatvorlage.

Sobald die Vorlage für ein echtes Projekt kopiert wird, kommt der Produktcode dazu (per
Konvention unter `app/`, siehe `factory/guards/run-project-tests.py`).

## Zuerst: einmaliges Onboarding

Bevor in einem **neuen** Projekt der erste Finding-Lauf startet, einmalig:

```
factory/scripts/factory-preflight.sh
```

Der Preflight prüft deterministisch alle Voraussetzungen (eigenes Repo, `origin`, Default-Branch,
repo-spezifisches GitHub-Credential, GitHub-API, `gh-api.sh`, `gh-query.sh`, PR-Rechte,
CI-Lesbarkeit, Branch-Schutz, Required Status Check, lokale Allows, geschützte Dateien) und endet
mit `FACTORY_PREFLIGHT: PASS` oder `FACTORY_PREFLIGHT: BLOCKED` samt der exakt fehlenden
einmaligen Schritte. Er ändert **nichts** und automatisiert bewusst nichts, was aus
Sicherheitsgründen menschlich bleiben muss (Token-Erstellung, GitHub-Admin/Ruleset, Vergabe
lokaler Berechtigungen). Details: [`factory/ONBOARDING.md`](factory/ONBOARDING.md).

Ist der Preflight `BLOCKED`: die genannten Schritte melden, **nicht** umgehen, **nicht** durch
breitere Berechtigungen ersetzen — und danach den Preflight erneut ausführen.

## Grundregel: Sicherheitsbefunde nicht direkt reparieren

Sicherheitsbefunde werden **nicht direkt repariert**. Sie durchlaufen stattdessen den
Factory-Workflow und werden erst nach abgeschlossener Analyse und Verifikation umgesetzt.
Direktes "schnell mal fixen" umgeht die Analyse-, Test- und Nachvollziehbarkeitsschritte, die der
Workflow erzwingt, und ist deshalb nicht erlaubt.

## Workflow-Zustände

```
OPEN → ANALYZED → IMPLEMENTING → VERIFYING → READY_FOR_CLOSURE → CLOSED
```

Zusätzlich existiert der Eskalationszustand `EXPERT_REVIEW_REQUIRED` (siehe unten). Die genauen
Anforderungen an jeden Zustand stehen in [`.claude/rules/factory-workflow.md`](.claude/rules/factory-workflow.md).
Der standardisierte Weg von `IMPLEMENTING` bis `CLOSED` inklusive Push, PR, echter CI und Merge
ist der [`verify-finding`-Skill](.claude/skills/verify-finding/SKILL.md).

## Technische Entscheidungen trifft Claude selbst

Claude trifft normale technische Entscheidungen (Ursachenanalyse, Reparaturansatz, Testplan,
Guard-Design) eigenständig und begründet sie schriftlich im jeweiligen Finding. Ein
nicht-technischer Projektinhaber soll **nicht** pro forma technische Sicherheitsrisiken
freigeben müssen — das wäre keine echte Kontrolle, sondern nur ein Ritual.

Daraus folgt für den laufenden Betrieb: **keine technischen Routinefragen an den Benutzer.** Ob
ein Branch angelegt, ein Commit gemacht, gepusht, ein PR eröffnet, CI abgefragt, ein Review
angestoßen oder ein grüner PR gemerged wird, ist keine Frage — das ist die Routine, die diese
Factory autorisiert. Wenn eine Antwort aus den Regeln in diesem Repository ableitbar ist, wird sie
abgeleitet und nicht erfragt.

## Wann die Factory wirklich stoppt

Genau vier Situationen beenden den unbeaufsichtigten Lauf. Alles andere ist Routine.

1. **P0** — ein Befund mit akuter, laufender Ausnutzung bzw. unmittelbarem Produktionsschaden.
   Ein P0 wird nicht autonom durchgearbeitet: Befund festhalten, Sofortlage beschreiben, stoppen,
   Menschen einbeziehen. Das ist **technisch erzwungen**, nicht nur hier beschrieben: jedes
   Finding trägt ab `ANALYZED` ein Pflichtfeld `Severity:` (`P0`–`P3`), und der Guard lässt für
   `Severity: P0` ausschließlich die Zustände `OPEN`, `ANALYZED` und `EXPERT_REVIEW_REQUIRED` zu.
2. **`EXPERT_REVIEW_REQUIRED`** — Claude selbst oder der unabhängige Reviewer stellt fest, dass
   eine autonome Entscheidung nicht verantwortbar ist (ungewöhnlich hohes technisches Risiko,
   große Unsicherheit über die Auswirkungen, potenziell irreversible Konsequenzen). Status setzen,
   die fünf Pflichtfelder ausfüllen, stoppen.
3. **Echte Produkt- oder Scope-Entscheidung** — eine Frage, die nicht technisch, sondern
   inhaltlich ist: Was soll das Produkt können? Ist dieses Verhalten gewollt? Soll ein Feature
   fallen? Solche Fragen entscheidet der Projektinhaber, nicht die Factory.
4. **`AUTONOMY_BLOCKER`** — eine technische Voraussetzung der Factory selbst fehlt oder ist
   inkonsistent (z. B. Worktree-HEAD ≠ erwarteter Basis-SHA, Preflight `BLOCKED`, Required Status
   Check nicht konfiguriert). Konkret melden, nicht umgehen.

## Tests und Sicherheitskontrollen dürfen nicht abgeschwächt werden

Tests oder Sicherheitskontrollen dürfen niemals abgeschwächt, übersprungen oder entfernt werden,
nur damit etwas grün wird oder ein Status schneller erreicht wird. Wenn ein Test oder eine
Kontrolle einem Fix im Weg steht, ist das ein Signal, den Fix oder die Analyse zu überdenken —
nicht die Kontrolle zu schwächen.

Das gilt ausdrücklich auch für die Grenzen der Factory selbst: **Während eines Findings werden
keine Sicherheitsgrenzen gelockert.** Die gesamte Kontrollebene ist gegen Selbstveränderung
geschützt:

```
factory/reviews/**       factory/guards/**        factory/scripts/**
.claude/hooks/**         .claude/agents/**        .claude/skills/**
.claude/rules/**         .claude/settings*.json   .github/workflows/**
CLAUDE.md
```

Der Schutz ist zweischichtig: lokal über `permissions.deny` und `sandbox.filesystem.denyWrite`
in `.claude/settings.json`, und — verbindlich, weil serverseitig — über
[`factory/guards/validate-control-plane.py`](factory/guards/validate-control-plane.py), das
diese Pfade in jedem CI-Lauf gegen das gestempelte Manifest `factory/control-plane.sha256`
prüft. Ein Finding, das diese Pfade anfassen will, ist per Definition außerhalb seines Scopes;
eine beabsichtigte Änderung daran ist ein **`FACTORY_CHANGE`** mit eigenem, strengerem Ablauf
(siehe [`.claude/rules/factory-workflow.md`](.claude/rules/factory-workflow.md)).

Auch die richtige Reaktion auf eine Approval-Abfrage ist **nie**, die Berechtigungen zu
erweitern, sondern den Befehl in die unten beschriebene einfache Form zu bringen.

## Git-Routine: einfache Befehle aus dem Repo-Verzeichnis, nie `git -C <pfad>`

Alle Routine-Git-Befehle der Factory laufen als **einfache** Befehle aus dem bereits richtigen
Arbeitsverzeichnis — der Repo-Wurzel bzw. dem Worktree des jeweiligen Findings:

```
git add <pfade>
git commit -m "..."
git fetch origin
git push origin <branch>
```

Genau diese einfache Form ist allowlistet und läuft ohne Approval-Abfrage. Die Allowlist-Einträge
sind **Präfix-Muster** (`git add *`, `git commit *`, `git fetch origin`, `git push origin *`, …).
Ein vorangestelltes `-C` verschiebt den Befehlsanfang und trifft deshalb kein einziges Muster
mehr: `git -C <pfad> commit …` erzeugt eine Approval-Abfrage und bricht damit einen
unbeaufsichtigten Factory-Lauf ab. Daraus folgt:

- **Kein** `git -C <pfad> commit …`, `git -C <pfad> push …` o. Ä. für normale Finding-Arbeit.
  Stattdessen zuerst in das richtige Verzeichnis wechseln (bei paralleler Arbeit: den Worktree
  über `EnterWorktree` betreten) und dann den einfachen Befehl absetzen.
- Auch keine Ersatzkonstruktionen wie `cd <pfad> && git commit …`: zusammengesetzte Befehle,
  Subshells, Command-Substitution (`$(...)`), Pipelines und inline `python3 -c "..."` treffen die
  Präfix-Muster ebenso wenig und sind für Routinearbeit generell zu vermeiden.
- Die richtige Reaktion auf eine Routine-Approval-Abfrage ist **nie**, Berechtigungen zu
  erweitern (insbesondere keine breiten Muster wie `git *` oder `git -C *`), sondern den Befehl
  in die einfache Form aus dem korrekten Arbeitsverzeichnis zu bringen.

Einzige Ausnahme: *innerhalb* eines Factory-Skripts, das ohnehin als ein einziger allowlisteter
Aufruf läuft, darf `git -C <worktree>` verwendet werden, um gezielt einen **anderen** Worktree
lesend zu prüfen — so verifiziert `create-finding-worktree.sh` den HEAD des gerade erzeugten
Worktrees. Für Befehle, die die Session selbst absetzt, gilt die Regel ausnahmslos.

## Der Default-Branch wird ermittelt, nie geraten

Die Vorlage ist übertragbar: der Default-Branch kann `main`, `master`, `trunk` oder anders heißen.
Die dokumentierte Konvention ist **`origin/<default-branch>`**, wobei `<default-branch>` vorher
deterministisch bestimmt wird — live vom Remote, nicht aus dem lokal gecachten (und
notorisch veraltenden) `refs/remotes/origin/HEAD`:

```
factory/scripts/create-finding-worktree.sh resolve
```

gibt genau dafür `DEFAULT_BRANCH <name>` und `BASE_SHA <sha>` aus. Alternativ liefert
`factory/scripts/gh-query.sh default-branch` die GitHub-Sicht derselben Information.

## Finding-Branches: immer `--no-track`, Basis vor dem ersten Schreiben prüfen

`.git/config` ist für die Sandbox nicht schreibbar. Das ist eine gewollte Grenze und wird **nicht**
gelockert. Ein Branch, dessen Startpunkt ein Remote-Tracking-Ref ist, richtet aber per Default
Upstream-Tracking ein (`branch.autoSetupMerge`) und schreibt dafür `branch.<name>.remote` und
`branch.<name>.merge` nach `.git/config`. Das scheitert an der Sandbox mit `could not lock config
file .git/config: Operation not permitted` und lässt die Branch-Erzeugung fehlschlagen.

Ein Finding-Branch braucht dieses Tracking nicht — gepusht wird ohnehin explizit mit
`git push origin <branch>`. Kanonisch sind deshalb vier einzelne, einfache Befehle aus dem
Repo-Verzeichnis:

```
git fetch origin
git switch --no-track -c <finding-branch> origin/<default-branch>
git rev-parse HEAD
git rev-parse origin/<default-branch>
```

Die beiden SHAs müssen **identisch** sein, bevor irgendetwas geschrieben wird. Bei Abweichung:
`AUTONOMY_BLOCKER: ...` melden und nicht weiterarbeiten.

Für Worktrees gilt dasselbe; dort setzt `factory/scripts/create-finding-worktree.sh` (siehe
unten) `--no-track` selbst und verifiziert die Basis, bevor es den Worktree freigibt. Beides ist
durch [`factory/guards/test_create_finding_worktree.py`](factory/guards/test_create_finding_worktree.py)
deterministisch abgesichert — inklusive des Falls, dass ein stale lokaler Branch bzw. ein
verwaister Remote-HEAD existiert und `.git/config` nicht schreibbar ist.

### Erwartete Sandbox-Meldungen, die **kein** `AUTONOMY_BLOCKER` sind

Zwei Meldungen erscheinen im Normalbetrieb, obwohl der Befehl erfolgreich ist. Beide sind Folge
derselben gewollten Sandbox-Grenzen und **kein** Grund, einen Lauf abzubrechen — maßgeblich ist
der Exit-Code und die tatsächliche Wirkung, nicht die Textausgabe:

- `fatal: failed to store: ...` bei `git fetch origin` und `git push origin <branch>`: der
  Credential-Helper darf den System-Schlüsselbund nicht beschreiben. Fetch und Push selbst laufen
  durch (Exit 0, Refs werden korrekt aktualisiert) — nachprüfbar mit
  `git rev-parse origin/<default-branch>`.
- `error: could not lock config file .git/config` zusammen mit `warning: update of config-file
  failed` beim **Löschen** eines Branches (`git branch -d` / `-D`): Git will den zugehörigen
  Config-Abschnitt mit entfernen und darf nicht. Der Branch wird trotzdem gelöscht
  (`Deleted branch ...`).

Der Unterschied zur Branch-**Erzeugung** oben ist wesentlich und der Grund, warum `--no-track`
dort zwingend ist: derselbe verweigerte Schreibzugriff lässt die Erzeugung **hart fehlschlagen**,
während er beim Löschen nur eine Warnung ist.

## Mehrere Findings gleichzeitig: Worktree statt Branch-Wechsel im selben Verzeichnis

Für **echt gleichzeitige** Arbeit an mehreren Findings (z. B. zwei P1 im selben Lauf) einen
eigenen Worktree pro Finding-Branch verwenden, statt im Hauptverzeichnis zwischen Branches zu
wechseln — das hält die Findings sauber getrennt.

**Worktree-Basis: immer explizit `origin/<default-branch>`, nie EnterWorktrees impliziten
"fresh"-Default.** EnterWorktrees `fresh`-Basis-Modus (harness-seitiger Default) löst "den
Default-Branch" über den lokal gecachten Symref `refs/remotes/origin/HEAD` auf. `git fetch origin`
aktualisiert diesen Symref **nicht** — nur ein expliziter `git remote set-head` tut das. Ist er
verwaist (real beobachtet: er zeigte auf einen alten, bereits gemergten Feature-Branch), entsteht
ein neuer Finding-Worktree still von einem veralteten Commit. EnterWorktree selbst bietet keinen
Parameter für einen expliziten Basis-Ref/SHA.

Deshalb für jeden Finding-Worktree zwingend zweistufig über
[`factory/scripts/create-finding-worktree.sh`](factory/scripts/create-finding-worktree.sh) gehen,
statt `EnterWorktree` direkt einen neuen Worktree anlegen zu lassen:

```
factory/scripts/create-finding-worktree.sh resolve
factory/scripts/create-finding-worktree.sh create <BASE_SHA-aus-resolve> .claude/worktrees/<ID> fix/<ID>
```

Das sind zwei getrennte, einfache Befehle: den von `resolve` ausgegebenen `BASE_SHA` ablesen und
im zweiten Aufruf wörtlich einsetzen — keine Command-Substitution, keine Subshell (siehe
"Git-Routine" oben).

Das Skript fragt den Remote nach seinem Default-Branch, fetcht `origin`, bestimmt den erwarteten
Basis-SHA explizit, legt den Worktree direkt von diesem Ref an (mit `--no-track`) und vergleicht
unmittelbar danach — vor jeder weiteren Schreiboperation — den tatsächlichen Worktree-HEAD gegen
den erwarteten SHA. Bei Abweichung wird der Worktree sofort verworfen, `AUTONOMY_BLOCKER: ...`
ausgegeben und nicht weitergearbeitet. Erst nach einem erfolgreichen `create` (Exit 0,
`WORKTREE_READY ...`) den Worktree über `EnterWorktree` mit `path: .claude/worktrees/<ID>`
betreten — niemals über `EnterWorktree`s `name`-Parameter, der wieder den impliziten,
symref-abhängigen `fresh`-Default verwenden würde.

## GitHub, PR, CI und Merge: feste Helfer statt ad-hoc-Konstruktionen

`gh` wird **nicht** vorausgesetzt und muss nicht installiert werden. Der gesamte GitHub-Zugriff
läuft über zwei Skripte, die je als ein einziger, statisch erkennbarer Befehl laufen:

- [`factory/scripts/gh-api.sh`](factory/scripts/gh-api.sh) — minimaler REST-Zugriff. Er nimmt das
  Credential aus dem git-credential-Helper (repo-spezifisch, inklusive `path` aus der
  origin-URL) und zielt immer auf das Repository, auf das `origin` zeigt. Kein Token in einer
  Datei, kein Token in der Ausgabe.
- [`factory/scripts/gh-query.sh`](factory/scripts/gh-query.sh) — feste Unterbefehle für die
  Routine: `repo`, `default-branch`, `pr`, `pr-summary`, `pr-create`, `check-runs`,
  `check-runs-summary`, `required-check`, `actions-run`, `actions-run-summary`, `actions-jobs`,
  `actions-jobs-summary`, `branch-rules`, `required-checks`, `merge`.

Die `-summary`-Unterbefehle existieren genau deshalb, damit für eine Routineabfrage **kein**
inline `python3 -c`, keine Pipeline und keine Zwischen-JSON-Datei nötig ist: Jeder liefert direkt
`key: value`-Zeilen auf stdout. Wer eine Routineabfrage per Pipeline oder Temp-Datei nachbaut,
erzeugt genau die Approval-Abfrage, die diese Skripte vermeiden.

**Die Merge-Entscheidung wird nicht aus Prosa gelesen.** Dafür gibt es zwei feste Regeln:

- `factory/scripts/gh-query.sh required-check <SHA> [NAME]` liefert **genau ein** Urteil
  (`success`, `failed`, `pending`, `absent`, `api_error`) und einen eindeutigen Exit-Code
  (`0/1/2/3/4`). Nur Exit 0 darf zu einem Merge führen. `absent` ist kein Erfolg: "der Check ist
  nicht da" ist nicht "der Check ist grün".
- `factory/scripts/gh-query.sh merge <PR> <METHOD> <ERWARTETER-HEAD-SHA>` verlangt den Head-SHA,
  für den CI-Evidence und Review tatsächlich vorliegen. Er wird lokal geprüft und zusätzlich an
  die GitHub-Merge-API übergeben, sodass ein zwischenzeitlich eingetroffener Push den Merge
  serverseitig scheitern lässt statt mitzureisen.

Ein API-Fehler (401, 403, 404, 422, 429, 5xx, Netzwerk) ist **niemals** ein leerer Normalzustand:
alle Helfer melden `api_error:` und enden mit einem Exit-Code ungleich 0.

Verbindlich ist der **Required Status Check** auf dem geschützten Default-Branch (Job `factory-checks`
aus [`.github/workflows/factory-ci.yml`](.github/workflows/factory-ci.yml)). Ein roter CI-Lauf
wird repariert, nicht umgangen; ein abgelehnter Merge wird gemeldet, nicht erzwungen. Nach dem
Merge wird der tatsächliche Remote-Stand verifiziert (`git fetch origin` +
`git rev-parse origin/<default-branch>`), nicht angenommen.
