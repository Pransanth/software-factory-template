# Software Factory – Leitplanken für Claude

Dieses Repository ist die Grundlage einer "Software Factory": ein wiederholbarer Prozess, mit
dem Sicherheitsbefunde (und später andere technische Arbeit) kontrolliert von der Meldung bis
zum Abschluss durchlaufen — mit klaren Zuständen und einem Guard, der die Regeln unabhängig von
jeder einzelnen Claude-Anweisung durchsetzt.

## Aktueller Stand

Aktuell existiert nur die Grundlage: Workflow-Definition, ein Dummy-Befund (`P1-DEMO-1`) und ein
deterministischer Guard. Es gibt noch **keine** Procurement-Anwendung und **keinen** echten Fix
für `P1-DEMO-1`. Solange nichts anderes vereinbart ist:

- Baue keine Procurement-App.
- Analysiere oder repariere `P1-DEMO-1` nicht technisch — er ist bewusst nur ein Übungsbefund.

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

## Technische Entscheidungen trifft Claude selbst

Claude trifft normale technische Entscheidungen (Ursachenanalyse, Reparaturansatz, Testplan,
Guard-Design) eigenständig und begründet sie schriftlich im jeweiligen Finding. Ein
nicht-technischer Projektinhaber soll **nicht** pro forma technische Sicherheitsrisiken
freigeben müssen — das wäre keine echte Kontrolle, sondern nur ein Ritual.

## Eskalation: `EXPERT_REVIEW_REQUIRED`

Wenn Claude feststellt, dass eine autonome Entscheidung nicht verantwortbar ist (ungewöhnlich
hohes technisches Risiko, große Unsicherheit über die Auswirkungen, potenziell irreversible
Konsequenzen o. Ä.), wird der Status `EXPERT_REVIEW_REQUIRED` gesetzt. Die Factory stoppt dann an
dieser Stelle, bis ein Mensch mit der nötigen Fachkenntnis entscheidet.

## Tests und Sicherheitskontrollen dürfen nicht abgeschwächt werden

Tests oder Sicherheitskontrollen dürfen niemals abgeschwächt, übersprungen oder entfernt werden,
nur damit etwas grün wird oder ein Status schneller erreicht wird. Wenn ein Test oder eine
Kontrolle einem Fix im Weg steht, ist das ein Signal, den Fix oder die Analyse zu überdenken —
nicht die Kontrolle zu schwächen.
