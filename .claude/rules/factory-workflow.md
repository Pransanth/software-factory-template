# Factory-Workflow: Zustände und Anforderungen

Diese Datei definiert die erlaubten Zustände eines Findings und was für jeden Zustand
mindestens vorliegen muss. Der Guard (`factory/guards/validate-finding.py`) setzt diese Regeln
technisch durch — diese Datei ist die dazugehörige Erklärung für Menschen.

## Erlaubte Zustände

| Status | Bedeutung |
|---|---|
| `OPEN` | Befund gemeldet, noch nicht analysiert. |
| `ANALYZED` | Ursache, Auswirkungen und Reparaturansatz sind dokumentiert. |
| `IMPLEMENTING` | Die Reparatur wird umgesetzt. |
| `VERIFYING` | Die Reparatur wird getestet/verifiziert. |
| `READY_FOR_CLOSURE` | Verifiziert, bereit zum Abschließen. |
| `CLOSED` | Abgeschlossen. |
| `EXPERT_REVIEW_REQUIRED` | Eskalation: eine autonome Entscheidung ist an dieser Stelle nicht verantwortbar. Die Factory stoppt, bis ein Mensch mit Fachkenntnis entscheidet. |

Jeder andere Statuswert ist ungültig und wird vom Guard abgelehnt.

## Anforderungen je Zustand

### `OPEN`

Die Analysefelder dürfen fehlen oder als "noch nicht analysiert" markiert sein (z. B. `Not yet
analyzed`, `TBD`). Es reicht, dass der Befund selbst beschrieben ist.

## Severity und der P0-Stopp

Jedes Finding trägt ab `ANALYZED` ein Pflichtfeld `Severity:` mit genau einem der Werte `P0`,
`P1`, `P2`, `P3`.

| Severity | Bedeutung |
|---|---|
| `P0` | Akute, laufende Ausnutzung bzw. unmittelbarer Produktionsschaden. |
| `P1` | Ernstes Sicherheitsproblem ohne Hinweis auf laufende Ausnutzung. |
| `P2` | Wichtig, aber kein unmittelbarer Blocker. |
| `P3` | Kleineres Robustheits-/Wartbarkeitsproblem. |

**Ein `P0` durchläuft die normale autonome Pipeline nicht.** Erlaubt sind für ein `P0`
ausschließlich die Zustände `OPEN`, `ANALYZED` und `EXPERT_REVIEW_REQUIRED`. Der Versuch, ein
`P0` auf `IMPLEMENTING`, `VERIFYING`, `READY_FOR_CLOSURE` oder `CLOSED` zu setzen, ist ein harter
Guard-Fehler. Befund festhalten, Sofortlage beschreiben, stoppen, Menschen einbeziehen.

Das ist bewusst eine technische Regel und keine Formulierung in `CLAUDE.md`: eine Regel, die nur
im Fließtext steht, ist keine Kontrolle.

### `ANALYZED` und alle nachfolgenden Zustände (`IMPLEMENTING`, `VERIFYING`, `READY_FOR_CLOSURE`, `CLOSED`)

Ab `ANALYZED` müssen mindestens diese acht Felder sinnvoll (nicht leer, kein Platzhalter)
ausgefüllt sein:

1. **Root Cause** – die eigentliche technische Ursache.
2. **Affected Components** – welche Systemteile betroffen sind.
3. **Relevant Architecture** – relevanter architektonischer Kontext.
4. **Recommended Repair** – der vorgeschlagene Reparaturansatz.
5. **Regression Test Plan** – wie sichergestellt wird, dass nichts anderes kaputtgeht.
6. **Central Guard Plan** – wie zukünftig automatisiert verhindert wird, dass das gleiche
   Problem erneut auftritt.
7. **Expected Blast Radius** – erwarteter Umfang der Auswirkungen der Reparatur.
8. **Risk Assessment** – Risikoeinschätzung der Reparatur bzw. des Nichtstuns.

Diese Felder bleiben in allen späteren Zuständen (`IMPLEMENTING` usw.) weiterhin Pflicht, da die
Analyse dort weiter gültig sein muss.

### `EXPERT_REVIEW_REQUIRED`

Dieser Zustand ist von den acht `ANALYZED`-Pflichtfeldern befreit — die Eskalation kann jederzeit
ausgelöst werden, auch bevor eine vollständige Analyse vorliegt, wenn die Unsicherheit oder das
Risiko selbst der Grund für die Eskalation ist.

`EXPERT_REVIEW_REQUIRED` ist aber **kein** einfacher Ausweg aus einer unvollständigen Analyse.
Damit die Eskalation selbst nachvollziehbar ist, müssen stattdessen diese fünf Felder sinnvoll
(nicht leer, kein Platzhalter) ausgefüllt sein:

1. **Risk Assessment** – dasselbe Feld wie bei `ANALYZED` (Risikoeinschätzung).
2. **Expert Review Reason** – warum eine autonome Entscheidung hier nicht verantwortbar ist.
3. **What Is Known** – was bereits verlässlich über den Befund bekannt ist.
4. **What Remains Uncertain** – was gerade nicht sicher geklärt werden kann.
5. **What An Expert Would Need To Review** – konkret, was ein Mensch mit Fachkenntnis prüfen
   oder entscheiden müsste.

Alle anderen sieben `ANALYZED`-Felder (Root Cause, Affected Components, Relevant Architecture,
Recommended Repair, Regression Test Plan, Central Guard Plan, Expected Blast Radius) dürfen bei
`EXPERT_REVIEW_REQUIRED` weiterhin unvollständig sein.

### `READY_FOR_CLOSURE` und `CLOSED`

Zusätzlich zu den acht `ANALYZED`-Pflichtfeldern verlangen diese beiden Zustände drei weitere,
ebenso sinnvoll (nicht leer, kein Platzhalter) ausgefüllte Felder:

1. **Verification Evidence** – welche Regressions- und relevanten Tests grün liefen (konkret
   benannt, nicht pauschal).
2. **CI Evidence** – ein konkreter, echter Verweis auf einen grünen CI-Lauf (z. B. Actions-Run-
   ID/URL), keine Behauptung ohne Beleg.
3. **Review Artifact** – der Pfad zu einem Review-Artefakt unter `factory/reviews/` (siehe
   [`factory/reviews/README.md`](../../factory/reviews/README.md)).

### Die Bindung des Reviews an Finding und Codezustand

`Review Artifact` ist kein freier Pfad. Der Guard verlangt **alle** folgenden Bedingungen —
jede einzelne davon schließt eine Lücke, die der Factory-Audit tatsächlich reproduziert hat:

1. Der Wert ist exakt `factory/reviews/<Finding-ID>.round-<N>.md`, wobei `<Finding-ID>` der
   Dateiname dieses Findings ist. Absolute Pfade, `../`-Traversal und jedes andere Verzeichnis
   werden abgelehnt.
2. Der aufgelöste reale Pfad liegt innerhalb von `factory/reviews/` — ein Symlink kann nicht
   hinausführen.
3. Die Datei besteht `validate-review.py` vollständig. Es genügt **nicht**, dass sie irgendwo
   eine Zeile `Result: PASS` enthält.
4. Das Feld `Finding:` im Artefakt nennt genau dieses Finding. Ein `PASS` für Finding A kann
   Finding B nicht schließen.
5. Es ist die **höchste** vorhandene Runde dieses Findings, und die Runden `1..N` sind
   lückenlos vorhanden. Eine ältere Runde schließt nicht, und eine FAIL-Runde kann nicht
   verschwinden.
6. `Result:` ist `PASS`. `FAIL` oder `EXPERT_REVIEW_REQUIRED` blockieren genauso wie ein
   fehlendes Review.
7. `Reviewed Scope Hash` entspricht dem aktuellen Scope-Hash des Repositories. **Ein `PASS`
   verliert seine Gültigkeit, sobald sich der geprüfte Code ändert.**
8. Keine frühere Runde trägt denselben Scope-Hash mit einem Ergebnis ungleich `PASS`.

`CLOSED` erfüllt automatisch dieselben Anforderungen wie `READY_FOR_CLOSURE` (kein separates,
schwächeres Regelwerk).

### Review-Runden sind append-only

Ein Review-Artefakt heißt `factory/reviews/<Finding-ID>.round-<N>.md` und wird **nie**
überschrieben. Jede neue Review-Runde bekommt die nächste freie Nummer. Geschrieben werden sie
ausschließlich vom `SubagentStop`-Hook, der dabei auch `Reviewer Agent Type`,
`Reviewer Agent ID` und `Reviewed Scope Hash` setzt — keines dieser drei Felder stammt aus dem
Text des Reviewers oder aus der Hand des implementierenden Agenten.

Daraus folgt die Regel für den Umgang mit einem `FAIL`: **reparieren, dann neu reviewen.** Den
Reviewer einfach erneut gegen denselben Codezustand zu befragen, bis er zustimmt, ergibt kein
gültiges Closure — Punkt 8 oben lehnt genau das ab. `FAIL` → Änderung → neue Runde → `PASS` ist
der legitime Weg und ausdrücklich vorgesehen.

### Der Scope-Hash

Der Scope-Hash ist ein SHA-256 über alle **getrackten** Dateien des Repositories mit Ausnahme von
`factory/findings/` und `factory/reviews/` (siehe
[`factory/guards/scope_hash.py`](../../factory/guards/scope_hash.py)). Die beiden Ausnahmen sind
notwendig, damit der Workflow selbst funktioniert: nach dem Review werden `Review Artifact` und
`Status` in das Finding geschrieben, und das Review-Artefakt selbst entsteht ja gerade. Alles,
was ein Reviewer inhaltlich beurteilt — Produktcode, Tests, Guards, Skripte, Hooks, CI-Workflow,
Bauaufträge — liegt **innerhalb** des Hashes.

Der standardisierte Ablauf dorthin ist der [`verify-finding`-Skill](../skills/verify-finding/SKILL.md);
das Review selbst führt der unabhängige, rein lesende
[`finding-closure-reviewer`-Subagent](../agents/finding-closure-reviewer.md) in einem
getrennten Kontext durch — nicht der implementierende Agent selbst, und dessen Ergebnis darf
nicht nachträglich überschrieben werden.

## Freigabe durch Menschen

Ein normaler technischer Befund benötigt **keine** manuelle menschliche Freigabe — Claude trifft
die technische Entscheidung selbst und dokumentiert sie in den Analysefeldern. Menschliche
Beteiligung ist ausschließlich für den Eskalationsfall `EXPERT_REVIEW_REQUIRED` vorgesehen, wenn
Claude selbst feststellt, dass eine autonome Entscheidung an dieser Stelle nicht verantwortbar
ist.

Die verpflichtende unabhängige Review vor `READY_FOR_CLOSURE` (siehe oben) ist **keine**
menschliche Freigabe — sie wird von einem separaten, rein lesenden Subagenten durchgeführt, nicht
von einem Menschen. Sie stellt aber sicher, dass die Closure-Entscheidung nicht ausschließlich
vom selben Agenten getroffen wird, der die Reparatur implementiert hat.

## `FACTORY_CHANGE`: Änderungen an der Kontrollebene selbst

Zur **Kontrollebene** gehört alles, was entscheidet, ob Arbeit weitergehen darf, oder das die
Evidence für so eine Entscheidung erzeugt:

```
factory/guards/**        factory/scripts/**       .claude/hooks/**
.claude/agents/**        .claude/skills/**        .claude/rules/**
.claude/settings*.json   .github/workflows/**     CLAUDE.md
```

**Normale Finding-Arbeit verändert diese Pfade nicht.** Sie sind lokal per `permissions.deny`
und `sandbox.filesystem.denyWrite` gesperrt, und — wichtiger, weil serverseitig — sie werden vom
Guard [`validate-control-plane.py`](../../factory/guards/validate-control-plane.py) gegen das
gestempelte Manifest `factory/control-plane.sha256` geprüft. Dieser Guard läuft im kanonischen
Runner und damit in jedem CI-Lauf. Ein Branch, der einen Guard abschwächt, fällt dadurch auf,
statt vom abgeschwächten Guard selbst geprüft zu werden.

Ist eine Änderung an der Kontrollebene beabsichtigt, ist sie ein **`FACTORY_CHANGE`** und läuft
strenger als ein normales Finding:

1. Eigener Branch, ausschließlich für diese Änderung.
2. Negativtests zuerst — die Lücke muss reproduzierbar rot sein, bevor sie geschlossen wird.
3. Vollständige Testsuite und echte externe CI.
4. Unabhängiger Review des **gesamten** Control-Plane-Diffs, nicht nur des Anlasses.
5. Menschliche Entscheidung. Eine Kontrollebene, die ihre eigene Reparatur allein freigibt, ist
   keine Kontrolle.
6. Erst danach `python3 factory/guards/validate-control-plane.py --update` und erneut CI.

**Ehrliche Grenze:** Wer eine Control-Plane-Datei *und* das Manifest im selben Commit ändert,
besteht diesen Guard. Das ist unvermeidbar — ein Repository kann Vertrauen in sich selbst nicht
aus sich selbst heraus herstellen. Was der Guard ändert, ist die Sichtbarkeit: aus einer stillen
Nebenwirkung wird ein Manifest-Diff, den ein Review nicht übersehen kann, plus die ausdrückliche
Erklärung, dass die Kontrollebene geändert werden sollte.

## Platzhalter, die nicht als "ausgefüllt" zählen

Der Guard erkennt u. a. folgende Werte als ungültige Platzhalter (unabhängig von Groß-/
Kleinschreibung und Leerzeichen): leerer Wert, `TBD`, `TODO`, `Not yet analyzed`, `N/A`.
