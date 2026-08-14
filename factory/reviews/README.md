# Review-Artefakte

Dieses Verzeichnis enthält die Ergebnisse unabhängiger Closure-Reviews für Findings, jeweils
eine Datei pro Finding: `factory/reviews/<Finding-ID>.md`.

Ein Review-Artefakt wird vom `finding-closure-reviewer`-Subagenten erzeugt (siehe
[`.claude/agents/finding-closure-reviewer.md`](../../.claude/agents/finding-closure-reviewer.md))
und im Rahmen des [`verify-finding`-Skills](../../.claude/skills/verify-finding/SKILL.md)
angestoßen. Es wird strukturell geprüft von
[`factory/guards/validate-review.py`](../guards/validate-review.py) und ist Teil des kanonischen
Runners (`python3 factory/guards/run-factory-checks.py`). Diese README-Datei selbst ist **kein**
Review-Artefakt und wird vom Guard ausdrücklich übersprungen.

## Wie diese Datei tatsächlich entsteht

Die Datei wird **ausschließlich** von einem `SubagentStop`-Hook geschrieben:
[`.claude/hooks/subagentstop-write-review.py`](../../.claude/hooks/subagentstop-write-review.py).
Dieser Hook reagiert gezielt auf das `SubagentStop`-Ereignis für den `finding-closure-reviewer`
(per `matcher` in [`.claude/settings.json`](../../.claude/settings.json), plus einer eigenen,
redundanten Prüfung des `agent_type` im Hook selbst) und liest dabei die von Claude Code
tatsächlich bereitgestellten Ereignisdaten — `agent_type`, `agent_id`, `last_assistant_message` —
direkt aus. Der **implementierende Haupt-Agent transkribiert das Reviewer-Ergebnis nicht selbst**:
Er stößt den Reviewer über das Agent-Tool an und liest anschließend nur noch das vom Hook
erzeugte Artefakt.

Zusätzlich ist `factory/reviews/` in `.claude/settings.json` per `permissions.deny` für die
Werkzeuge `Edit` und `Write` gesperrt und per `sandbox.filesystem.denyWrite` auch für
Bash-Kindprozesse — der Haupt-Agent kann hier also auch dann kein Artefakt anlegen, wenn er es
versuchen wollte. Der Hook selbst ist davon nicht betroffen, da diese Regeln Claudes eigene
Tool-Aufrufe bzw. den Bash-Sandbox betreffen, nicht die Dateizugriffe des separaten
Hook-Prozesses.

**Ehrliche Grenze:** Das ist Schutz gegen einen normalen bzw. versehentlichen agentischen
Bypass — **keine** kryptographische Attestation gegen einen lokalen Benutzer mit
Dateisystemzugriff oder gegen einen beliebigen externen Prozess, der die Datei direkt beschreibt.
Ein Nutzer mit Schreibzugriff auf `.claude/settings.json` kann diesen Schutz jederzeit
abschalten. Malformed Reviewer-Ausgabe (fehlende Felder, mehrdeutiger oder falscher
`Result`-Wert, mehr als ein bzw. kein Fenced-Block) wird vom Hook niemals als `PASS`
interpretiert — in diesem Fall entsteht schlicht **kein** Artefakt.

## Format

Plain-Text-Felder, ein Feld pro Zeile — dieselbe Konvention wie bei den Findings unter
[`factory/findings/`](../findings/):

```
# <Finding-ID>

Finding: <Finding-ID>
Reviewer: <wer/was den Review durchgeführt hat>
Reviewer Agent Type: <agent_type aus dem SubagentStop-Event, nur vom Hook gesetzt>
Reviewer Agent ID: <agent_id aus dem SubagentStop-Event, nur vom Hook gesetzt>
Reviewed Commit: <Commit-Hash / Branch, oder Beschreibung der geprüften Diff-Basis>
Result: PASS | FAIL | EXPERT_REVIEW_REQUIRED
Root Cause Addressed: <ja/nein + Begründung>
Regression Evidence Checked: <was geprüft wurde, und wie>
Guard Evidence Checked: <was geprüft wurde, und wie>
Scope Checked: <wurde der genehmigte Bauauftrags-Scope eingehalten>
Remaining Risks: <verbleibende Risiken, oder "Keine">
Findings And Objections: <konkrete Einwände, oder "Keine">
```

Alle zwölf Felder sind Pflichtfelder (nicht leer, kein Platzhalter wie `TBD`); `Result` muss
exakt einer der drei genannten Werte sein; `Reviewer Agent Type` muss exakt
`finding-closure-reviewer` sein, der einzige gültige Reviewer-Agent-Typ. `Finding` muss
auf eine tatsächlich existierende Datei unter `factory/findings/` verweisen. `Reviewer Agent
Type` und `Reviewer Agent ID` stammen nie aus dem Text des Reviewer-Subagenten selbst und nie von
Hand — nur der Hook setzt sie, aus den echten Ereignisdaten.

## Was der Guard prüft — und was nicht

`validate-review.py` prüft ausschließlich Struktur: sind alle Felder ausgefüllt, ist `Result`
ein gültiger Wert, ist `Reviewer Agent Type` der eine gültige Reviewer-Agent-Typ, existiert das
referenzierte Finding. Er bewertet **nicht**, ob der Inhalt inhaltlich zutrifft — ob die Root
Cause wirklich behoben ist, ob die Regressionsbeweise überzeugend sind, ob es übersehene
Umgehungswege gibt. Diese inhaltliche Bewertung liefert ausschließlich der unabhängige Reviewer;
ein einfacher Python-Validator kann und soll sie nicht ersetzen. Er kann auch `Reviewer Agent ID`
nicht gegen ein Register gültiger IDs prüfen (ein solches Register existiert nicht) — er verlangt
dort nur einen vorhandenen, nicht-platzhalterhaften Wert.

Ein Finding kann `READY_FOR_CLOSURE` oder `CLOSED` nur erreichen, wenn sein `Review Artifact`-Feld
auf eine hier gültige Datei mit `Result: PASS` verweist — geprüft von
[`factory/guards/validate-finding.py`](../guards/validate-finding.py). `Result: FAIL` oder
`Result: EXPERT_REVIEW_REQUIRED` blockieren das technisch.
