# Factory – kurze technische Einführung

Diese Datei erklärt in einfachen Worten, was die Bausteine in diesem Verzeichnis tun und wie sie
zusammenhängen. Für die genauen Zustandsregeln siehe
[`.claude/rules/factory-workflow.md`](../.claude/rules/factory-workflow.md), für die einmalige
Einrichtung eines neuen Projekts [`factory/ONBOARDING.md`](ONBOARDING.md).

## Was ist ein Finding?

Ein Finding ist eine einzelne Markdown-Datei unter `factory/findings/`. Sie beschreibt einen
Befund (aktuell nur Sicherheitsbefunde) und trägt einen Status (`OPEN`, `ANALYZED`, ... siehe
Workflow-Regeln). Je nach Status müssen bestimmte Analysefelder ausgefüllt sein.

Den Aufbau zeigt [`factory/findings/EXAMPLE-FINDING.md`](findings/EXAMPLE-FINDING.md) — eine
ausdrücklich als Formatbeispiel gekennzeichnete Datei ohne Produktbezug. In einem echten Projekt
wird sie durch die tatsächlichen Findings ersetzt oder gelöscht.

## Was ist ein Validator?

Ein Validator ist ein kleines, deterministisches Skript, das eine einzelne Datei gegen die Regeln
für ihren Status prüft — ohne KI, ohne Netzwerk, rein regelbasiert:

- [`factory/guards/validate-finding.py`](guards/validate-finding.py) prüft ein Finding:
  ```
  python3 factory/guards/validate-finding.py factory/findings/<ID>.md
  ```
- [`factory/guards/validate-review.py`](guards/validate-review.py) prüft ein Review-Artefakt:
  ```
  python3 factory/guards/validate-review.py factory/reviews/<ID>.md
  ```

Exit 0 = gültig, Exit 1 = ungültig (mit Fehlerliste). Jeder Validator prüft genau eine Datei und
weiß nichts davon, wer ihn aufruft.

## Was ist der gemeinsame Factory-Runner?

[`factory/guards/run-factory-checks.py`](guards/run-factory-checks.py) ist der **eine
kanonische Einstiegspunkt** für "sind alle Factory-Prüfungen aktuell grün?":

```
python3 factory/guards/run-factory-checks.py
```

Exit 0 = alle Checks bestanden, Exit 1 = mindestens einer fehlgeschlagen — mit einer klaren
Auflistung, welcher Check bei welcher Datei fehlgeschlagen ist. Er führt vier Arten von Check
aus, alle ohne KI, ohne Netzwerk, rein regelbasiert:

1. **Finding-Validierung**: jede Datei unter `factory/findings/` gegen
   [`validate-finding.py`](guards/validate-finding.py). Für ein Finding, das `READY_FOR_CLOSURE`
   oder `CLOSED` erreichen will, prüft dieser Schritt die vollständige Closure-Bindung: das
   referenzierte Review-Artefakt muss die **eigene, neueste** Review-Runde dieses Findings sein,
   den Review-Guard bestehen, `Result: PASS` tragen und einen `Reviewed Scope Hash`, der noch dem
   aktuellen Repository-Stand entspricht (siehe
   [`.claude/rules/factory-workflow.md`](../.claude/rules/factory-workflow.md), "Die Bindung des
   Reviews an Finding und Codezustand"). Zusätzlich gilt hier der P0-Stopp.
2. **Bauauftrags-Guard**: jede Datei unter `factory/build-orders/` (außer `README.md`) gegen
   [`validate-build-order.py`](guards/validate-build-order.py) — kanonischer Ort, gegenseitige
   Bindung an genau ein existierendes Finding, alle Pflichtabschnitte, keine Platzhalter, und
   lebenszyklusabhängig ein tatsächlich zitierter roter bzw. grüner Lauf. Ab `IMPLEMENTING`
   verlangt zusätzlich der Finding-Validator diesen Bauauftrag (Audit-Befund F-10): ohne ihn hat
   der unabhängige Reviewer nichts, wogegen er den Code halten könnte.
3. **Review-Guard**: jede Datei unter `factory/reviews/` (außer `README.md`) gegen
   [`validate-review.py`](guards/validate-review.py) — prüft nur die Struktur eines
   Review-Artefakts (kanonischer Rundenname, alle Felder ausgefüllt, `Result` ein gültiger Wert,
   Reviewer-Provenienz korrekt, Scope-Hash wohlgeformt), nicht dessen inhaltliche Richtigkeit.
3. **Control-Plane-Guard**: [`validate-control-plane.py`](guards/validate-control-plane.py)
   vergleicht die Kontrollebene der Factory (Guards, Skripte, Hooks, Agent, Skills, Regeln,
   CI-Workflow, `CLAUDE.md`) gegen das gestempelte Manifest `factory/control-plane.sha256`. Das
   ist der Schritt, der verhindert, dass ein normales Finding still den Guard verändert, der es
   gleich prüfen soll — CI checkt den PR-Head aus und würde sonst mit genau dieser veränderten
   Datei prüfen.

**Projektspezifische Guards** (z. B. ein AST-Guard, der eine bestimmte Laufzeit-Sicherheitsgrenze
der Anwendung erzwingt) gehören ausdrücklich **nicht** in diese Vorlage, sondern in das jeweilige
Projekt. Der vorgesehene Erweiterungspunkt ist eine weitere `run_*_checks()`-Funktion im Runner
plus ein eigener `validate-*.py`-Guard — so bleibt es bei **einem** Befehl für alle Aufrufer und
niemand dupliziert Prüflogik.

## Was ist der Projekt-Test-Runner?

[`factory/guards/run-project-tests.py`](guards/run-project-tests.py) ist der kanonische
Einstiegspunkt für die Tests des **Produktcodes** (per Konvention `app/**/test_*.py`,
umstellbar mit `--project-dir`). Er ist **bewusst nicht** in `run-factory-checks.py` eingehängt
und läuft deshalb **nicht** über den lokalen Stop-Hook, sondern ausschließlich in GitHub CI:
Während `IMPLEMENTING` ist ein rotes Regressionstest-Ergebnis vor dem Fix ein normaler,
gewollter Zwischenzustand — würde der Stop-Hook bei jedem Sitzungsende alle Projekttests
verlangen, würde er genau diesen gewollten Zwischenzustand blockieren. CI dagegen läuft bei
Push/PR, also wenn eine Änderung als fertig gilt.

In einer frischen Kopie der Vorlage gibt es noch keinen Produktcode; der Runner meldet das und
endet mit Exit 0.

## Verification Skill und unabhängiger Reviewer

Der Weg von `IMPLEMENTING` über `VERIFYING`, externe CI, ein unabhängiges Review,
`READY_FOR_CLOSURE`, `CLOSED` bis zum Merge ist standardisiert und wiederverwendbar, nicht an
einen einmaligen Chat-Prompt gebunden:

- **[`.claude/skills/verify-finding/SKILL.md`](../.claude/skills/verify-finding/SKILL.md)**
  beschreibt den Ablauf: lokale Evidence einsammeln (Regressionstest, relevante Tests, Guard,
  kanonischer Runner, Projekttests), pushen, PR erstellen, echten CI-Lauf abwarten, unabhängiges
  Review anstoßen, Artefakt prüfen, je nach Ergebnis weiter zu `READY_FOR_CLOSURE`/`CLOSED` und
  Merge, zu `EXPERT_REVIEW_REQUIRED`, oder stoppen. Der Skill trifft selbst keine
  Sicherheitsentscheidung — er prüft vorhandene Evidence systematisch und delegiert die
  eigentliche Bewertung an den Reviewer.
- **[`.claude/agents/finding-closure-reviewer.md`](../.claude/agents/finding-closure-reviewer.md)**
  ist ein eigenständiger, **rein lesender** Subagent (Tools: nur `Read`, `Grep`, `Glob` — kein
  `Edit`, `Write`, `Bash`). Er läuft in einem getrennten Kontext ohne Erinnerung an die
  implementierende Session und liefert genau eines: `PASS`, `FAIL` oder
  `EXPERT_REVIEW_REQUIRED`, mit Begründung und Fundstellen. Der implementierende Agent darf
  dieses Ergebnis nicht nachträglich überschreiben.
- **[`factory/reviews/`](reviews/README.md)** ist der Ort für Review-Artefakte
  (`factory/reviews/<Finding-ID>.round-<N>.md`). Sie entstehen **ausschließlich** über den
  `SubagentStop`-Hook aus den echten Ereignisdaten des Reviewer-Laufs (Provenienz-Felder
  `Reviewer Agent Type` / `Reviewer Agent ID`) und werden strukturell von `validate-review.py`
  geprüft. Runden werden **nie überschrieben**: jede neue Review-Runde bekommt die nächste freie
  Nummer, und der Hook stempelt zusätzlich den `Reviewed Scope Hash` des Moments ein, in dem der
  Reviewer fertig war. Dadurch verliert ein `PASS` seine Gültigkeit, sobald sich der geprüfte
  Code ändert, und ein `FAIL` lässt sich nicht durch erneutes Fragen gegen denselben Codestand
  wegsampeln.

**Implementierender Agent vs. unabhängiger Reviewer:** Der implementierende Agent (der die
Reparatur baut und den `verify-finding`-Skill ausführt) hat vollen Werkzeugzugriff, kennt die
gesamte Implementierungshistorie und hat naturgemäß ein Interesse daran, dass sein eigener Fix
funktioniert. Der Reviewer ist bewusst das Gegenteil: werkzeugbeschränkt (rein lesend), ohne
Gedächtnis der Implementierung, ausschließlich mit dem beauftragt, kritisch zu prüfen, ob die
Behauptungen tatsächlich stimmen. Diese Trennung ist der Grund, warum Closure-Gates ein
`Result: PASS` aus einem echten, separaten Review verlangen, statt sich auf die Selbstauskunft des
implementierenden Agenten zu verlassen.

## Skripte: Worktrees, GitHub, Onboarding

- [`factory/project-tests.conf`](project-tests.conf) — die Produkttests dieses Repositories. Die
  Factory kennt das Testframework des Projekts nicht; sie führt genau die hier deklarierten
  Kommandos aus, ohne Shell (Audit-Befund F-21). Control Plane: eine Änderung ist ein
  `FACTORY_CHANGE`.
- [`factory/scripts/create-finding-worktree.sh`](scripts/create-finding-worktree.sh) — legt einen
  Finding-Worktree deterministisch auf dem aktuellen Stand von `origin/<default-branch>` an.
  **Hinweis:** Bei aktiver Factory-Sandbox lässt sich kein Worktree anlegen (Audit-Befund F-15);
  Factory v1 ist bewusst sequentiell. Das Skript meldet diesen Fall als
  `SANDBOX_WORKTREE_INCOMPATIBLE` mit Exit 4
  (`--no-track`, HEAD-Verifikation gegen den erwarteten SHA, sonst `AUTONOMY_BLOCKER`).
- [`factory/scripts/gh-api.sh`](scripts/gh-api.sh) — minimaler GitHub-REST-Zugriff über den
  git-credential-Helper. **`gh` wird nicht vorausgesetzt.** Der Repository-Slug wird aus allen
  unterstützten origin-Schreibweisen normalisiert und gegen `OWNER/REPO` validiert; der
  HTTP-Status wird ausgewertet, sodass ein 401/403/404/422/429/5xx als `api_error` mit
  Exit ≠ 0 sichtbar wird statt als leere Normalantwort.
- [`factory/scripts/gh-query.sh`](scripts/gh-query.sh) — feste, eng gefasste Unterbefehle für
  PR-, Check-, Actions-, Ruleset- und Merge-Routine, jeweils mit `key: value`-Ausgabe. Die
  Auswertung der Antworten liegt in [`factory/guards/gh_evidence.py`](guards/gh_evidence.py) und
  ist damit ohne Netz testbar. `required-check <SHA> [NAME]` liefert genau ein Urteil plus
  Exit-Code; `merge <PR> <METHOD> <SHA>` verlangt den erwarteten Head-SHA und übergibt ihn an die
  GitHub-API.
- [`factory/scripts/factory-preflight.sh`](scripts/factory-preflight.sh) — der Onboarding-Check
  für ein neues Projekt, siehe [`factory/ONBOARDING.md`](ONBOARDING.md).

## Was macht der Stop-Hook?

[`.claude/hooks/stop-validate-findings.py`](../.claude/hooks/stop-validate-findings.py) ist ein
Claude-Code-Stop-Hook: Er wird automatisch aufgerufen, wenn Claude versucht, eine Aufgabe in
diesem Repository zu beenden. Er enthält **keine eigene Prüflogik** — er ruft ausschließlich den
gemeinsamen Runner (`run-factory-checks.py`) auf und übersetzt dessen Ergebnis in das, was
Claude Code von einem Stop-Hook erwartet: bei Erfolg darf Claude stoppen, bei einem
fehlgeschlagenen Check wird der Stopp blockiert und Claude bekommt die Fehlermeldung als Grund
mitgeteilt.

## Was kann der Stop-Hook ausdrücklich NICHT garantieren?

Der Stop-Hook ist ein **lokaler Workflow-Guard**, **kein finales Security- oder Merge-Gate**.
Insbesondere:

- Er läuft nur, wenn Claude Code selbst versucht zu stoppen — er prüft nichts, wenn Dateien auf
  anderem Weg geändert werden (manuell, durch ein anderes Tool, durch ein Skript).
- Ein erster, ungültiger Stop-Versuch wird blockiert, mit der konkreten Ursache. Ein
  **wiederholter** Versuch (`stop_hook_active: true`) wird dagegen bewusst **nicht** erneut
  geprüft und **nicht** erneut blockiert — er lässt Claude sofort weiterlaufen, unabhängig davon,
  ob der Zustand inzwischen tatsächlich gültig ist. Das ist eine bewusste Verhaltensänderung:
  Eine frühere Version dieses Hooks prüfte bei jedem Versuch erneut und verließ sich auf Claude
  Codes eigenen, dokumentierten Block-Cap (nominell 8 aufeinanderfolgende Blockierungen ohne
  Fortschritt, konfigurierbar über `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`), um eine echte
  Endlosschleife zu verhindern. In der Praxis griff dieser Cap nicht zuverlässig — eine Sitzung
  blieb über viele Wiederholungen hinweg blockiert hängen, ohne lokale Möglichkeit, das anders als
  durch manuelles Eingreifen außerhalb der Session zu beheben. Sich auf einen Plattform-Cap zu
  verlassen, der nicht zuverlässig greift, ist keine echte Schleifensicherheit. Dieser Hook
  liefert deshalb seine eigene, einfache Garantie: höchstens eine Blockierung pro Aufgabe.

  Das bedeutet auch: Ein zweiter Stop-Versuch kommt immer durch, selbst wenn der Zustand
  tatsächlich weiterhin ungültig ist. Das schwächt **keine** der eigentlichen Prüfregeln —
  `validate-finding.py`, `validate-review.py` und `run-factory-checks.py` selbst bleiben
  unverändert scharf. Es ändert nur, ob *dieser lokale Hook* einen zweiten Versuch aufhält. Ob ein
  Finding wirklich abschließbar ist, entscheiden weiterhin ausschließlich die deterministischen
  Guards und, verbindlich, GitHub CI.
- Er läuft mit den Rechten des lokalen Nutzers und lässt sich durch Konfiguration umgehen oder
  deaktivieren. Ein Nutzer mit Schreibzugriff auf `.claude/settings.json` kann ihn jederzeit
  abschalten.
- Er prüft nur formale Vollständigkeit der Felder, nicht deren inhaltliche Richtigkeit.

Ein wirklich verlässliches Gate — bevor Code in den geschützten Default-Branch gelangt — braucht
eine serverseitige Prüfung (CI), die nicht vom lokalen Rechner, von Claude Code oder von diesem
Hook abhängt. Genau das ist GitHub CI (`.github/workflows/factory-ci.yml`) **zusammen mit einem
Required Status Check auf dem geschützten Default-Branch** — siehe
[`factory/ONBOARDING.md`](ONBOARDING.md), Schritt 3. Ohne diesen Required Status Check prüft CI
zwar, blockiert aber keinen Merge.

## Shared vs. local Claude settings

Dieses Repo hat zwei getrennte Claude-Code-Einstellungsdateien mit bewusst unterschiedlichem
Zweck:

- **`.claude/settings.json`** ist die **übertragbare, versionierte Factory-Konfiguration**. Sie
  gehört zur Vorlage selbst: Stop- und SubagentStop-Hook, der OS-Sandbox-Schutz sowie explizite
  `Edit`/`Write`-Sperren auf `factory/reviews/`, `.claude/hooks/`, `.claude/skills/`,
  `.claude/agents/` und die Settings-Dateien selbst (Verteidigung in der Tiefe) — Regeln, die für
  jede Kopie dieses Repos gleichermaßen sinnvoll sind. `git push` und GitHub-Zugriff sind hier
  bewusst **nicht** pauschal verboten: ein normaler, bereits durch die Factory-Regeln
  autorisierter Finding-Workflow (Fix → Verifikation → CI → Review → Closure → PR/Merge) muss
  unbeaufsichtigt laufen können. Diese Datei wird committet.
- **`.claude/settings.local.json`** ist **persönlich/maschinenspezifisch** und **niemals Teil der
  Factory-Vorlage**. Hier stehen die konkreten Allows dieser Maschine, inklusive absoluter Pfade
  (z. B. der read-only `Read(<repo>/**)`-Zugriff des Reviewers). Diese Datei wird **nicht**
  committet (siehe `.gitignore`) und wird von der Factory auch nicht selbst geschrieben — den
  passenden Block gibt `factory/scripts/factory-preflight.sh` aus, einsetzen muss ihn ein Mensch.

Faustregel: **Absolute Pfade zu irgendetwas außerhalb dieses Repos gehören ausschließlich in
`settings.local.json`.**

## Die Prüfkette: lokal bis CI

Es gibt vier Schichten, aber nur **eine** Prüflogik pro Check-Art — jede Schicht ruft nur die
davor auf, niemand implementiert die Regeln ein zweites Mal:

```
lokale Validatoren           factory/guards/validate-finding.py, validate-review.py
                                                                    (pruefen je 1 Datei)
        ↓
gemeinsamer Factory-Runner   factory/guards/run-factory-checks.py   (ruft beide fuer alle
                                                                      betroffenen Dateien auf)
        ↓
Claude Stop-Hook             .claude/hooks/stop-validate-findings.py (ruft den Runner beim
                                                                      Stop-Versuch auf)
        ↓
GitHub CI                    .github/workflows/factory-ci.yml        (ruft denselben Runner-Befehl
                              PLUS zusaetzlich, nur hier, den Projekt-Test-Runner auf:
                              factory/guards/run-project-tests.py -- siehe "Was ist der
                              Projekt-Test-Runner?" oben fuer den Grund, warum dieser Schritt
                              bewusst nicht ueber den Stop-Hook laeuft)
```

**Die GitHub-CI (`factory-ci.yml`) ist davon komplett unabhängig.** Sie kennt keine Claude-Session,
keinen Stop-Hook und kein `stop_hook_active` — sie checkt bei jedem Push und bei jedem Pull
Request den Repository-Zustand frisch aus und lässt exakt denselben Befehl laufen, den auch der
Stop-Hook und jeder Entwickler lokal ausführen können:

```
python3 factory/guards/run-factory-checks.py
```

Damit prüft CI **denselben Zustand ein zweites Mal, unabhängig davon, ob oder wie der Stop-Hook
lokal reagiert hat** — auf einem frischen GitHub-Actions-Runner, ohne Secrets, ohne Schreibrechte,
ohne Docker, ohne Claude-/Anthropic-API. Das ist die Absicherung dafür, dass "lokal grün" (oder
"vom Stop-Hook durchgelassen") tatsächlich auch "in CI grün" bedeutet — unabhängig davon, ob der
lokale Rechner, die Claude-Session oder der Stop-Hook selbst kompromittiert, deaktiviert oder
falsch konfiguriert wäre.
