# Bauaufträge

Ein Bauauftrag ist der schriftliche Plan für die Reparatur genau eines Findings:
`factory/build-orders/<Finding-ID>.md`. Er entsteht nach `ANALYZED` und vor `IMPLEMENTING`, und
er ist die Grundlage, gegen die der unabhängige
[`finding-closure-reviewer`](../../.claude/agents/finding-closure-reviewer.md) später prüft — der
Reviewer erfindet kein eigenes Sicherheitsmodell, sondern hält den Bauauftrag gegen den
tatsächlichen Code.

Diese README-Datei ist selbst kein Bauauftrag.

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
