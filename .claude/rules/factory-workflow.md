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

## Freigabe durch Menschen

Ein normaler technischer Befund benötigt **keine** manuelle menschliche Freigabe — Claude trifft
die technische Entscheidung selbst und dokumentiert sie in den Analysefeldern. Menschliche
Beteiligung ist ausschließlich für den Eskalationsfall `EXPERT_REVIEW_REQUIRED` vorgesehen, wenn
Claude selbst feststellt, dass eine autonome Entscheidung an dieser Stelle nicht verantwortbar
ist.

## Platzhalter, die nicht als "ausgefüllt" zählen

Der Guard erkennt u. a. folgende Werte als ungültige Platzhalter (unabhängig von Groß-/
Kleinschreibung und Leerzeichen): leerer Wert, `TBD`, `TODO`, `Not yet analyzed`, `N/A`.
