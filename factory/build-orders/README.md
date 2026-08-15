# Bauaufträge

Ein Bauauftrag ist der schriftliche Plan für die Reparatur genau eines Findings:
`factory/build-orders/<Finding-ID>.md`. Er entsteht nach `ANALYZED` und vor `IMPLEMENTING`, und
er ist die Grundlage, gegen die der unabhängige
[`finding-closure-reviewer`](../../.claude/agents/finding-closure-reviewer.md) später prüft — der
Reviewer erfindet kein eigenes Sicherheitsmodell, sondern hält den Bauauftrag gegen den
tatsächlichen Code.

Diese README-Datei ist selbst kein Bauauftrag.

## Das ist erzwungen, nicht empfohlen (Audit-Befund F-10)

Bis zur Operational-Robustness-Reparatur stand diese Gliederung nur hier, als Prosa. Ein Finding
konnte `IMPLEMENTING`, `VERIFYING`, `READY_FOR_CLOSURE` und `CLOSED` ohne **jeden** Bauauftrag
erreichen, und alle Prüfschichten meldeten Erfolg. Der Reviewer bekam damit die Anweisung, etwas
gegen den Code zu halten, das gar nicht existierte.

Jetzt prüft [`factory/guards/validate-build-order.py`](../guards/validate-build-order.py)
deterministisch, und der kanonische Runner führt ihn in jedem CI-Lauf aus:

1. **Kanonischer Ort.** Der aufgelöste reale Pfad liegt in `factory/build-orders/`, der Dateiname
   ist `<Finding-ID>.md`. Ein Symlink kann nicht hinausführen. `README.md` ist Dokumentation und
   wird nie als Bauauftrag geprüft.
2. **Gegenseitige Bindung.** `factory/findings/<Finding-ID>.md` muss existieren, und die
   Titelzeile muss `# Bauauftrag: <Finding-ID>` für genau dieses Finding lauten. Ein verwaister
   Bauauftrag und einer, der auf ein anderes Finding titelt, werden abgelehnt.
3. **Pflichtabschnitte.** Alle sechs unten. Zusätzliche Abschnitte sind erlaubt.
4. **Keine Platzhalter.** Jeder Pflichtabschnitt muss echten Inhalt tragen — nicht leer, kein
   `TBD`/`TODO`/`N/A`, nicht nur ein paar Zeichen.
5. **Evidence folgt dem Lebenszyklus**, gelesen aus dem `Status:` des Findings:
   - ab `IMPLEMENTING`: **Red Regression Evidence** muss einen tatsächlich zitierten Lauf
     enthalten (einen nicht-leeren ```-Block). „Der Test war rot" ohne den Lauf ist eine
     Behauptung, keine Evidence.
   - ab `VERIFYING`: **Green Runtime Fix Evidence** ebenso.

   Bei `IMPLEMENTING` darf der grüne Abschnitt noch ankündigen, was laufen wird — ihn dort schon
   zu verlangen hieße, den Beleg vor der Tatsache zu schreiben.

`OPEN`, `ANALYZED` und `EXPERT_REVIEW_REQUIRED` verlangen keinen Bauauftrag: er entsteht nach
`ANALYZED`, und die Eskalation muss auch aus einem Zustand heraus erreichbar bleiben, in dem noch
keiner existieren kann.

Die Abschnittsüberschriften werden umlaut- und schreibungstolerant erkannt, `## Primäre
Sicherheitsgrenze` und `## Primaere Sicherheitsgrenze` gelten also beide.

## Bewährte Gliederung

```
# Bauauftrag: <Finding-ID>

## Primäre Sicherheitsgrenze
Welche Laufzeitgrenze die eigentliche Reparatur ist -- nicht der Guard, sondern die
Architektur, die den unsicheren Zustand unerreichbar macht.

## Verbindliche Reihenfolge
1. Regressionstest schreiben und ROT beobachten (mit zitierter Fehlermeldung).
2. Laufzeitgrenze umsetzen, bis derselbe Test GRÜN ist.
3. Zentralen Guard ergänzen, der ein erneutes Auftreten automatisiert erkennt.
4. Kanonischen Runner und Projekttests laufen lassen.

## Acceptance Criteria
Woran objektiv erkennbar ist, dass der Auftrag erfüllt ist.

## Scope
Welche Pfade geändert werden dürfen -- abschließend. Alles andere ist out of scope; die
geschützten Factory-Pfade (factory/reviews/, .claude/hooks/, .claude/skills/, .claude/agents/,
.claude/settings*.json) sind es immer.

## Red Regression Evidence
Der zitierte, tatsächliche Fehlschlag des Regressionstests VOR dem Fix.

## Green Runtime Fix Evidence
Die zitierten, tatsächlichen Testläufe NACH dem Fix (Regressionstest, betroffene Testgruppen,
Guard, kanonischer Runner).
```

Die beiden Evidence-Abschnitte werden mit echten Ausgaben gefüllt, nicht mit Behauptungen: der
Reviewer vergleicht das Zitierte mit dem *aktuellen* Inhalt der Testdatei und meldet es als
Befund, wenn eine Assertion zwischenzeitlich abgeschwächt wurde.
