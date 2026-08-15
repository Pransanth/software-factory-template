# Review-Artefakte

Dieses Verzeichnis enthält die Ergebnisse unabhängiger Closure-Reviews für Findings — eine Datei
pro **Review-Runde**: `factory/reviews/<Finding-ID>.round-<N>.md`.

Ein Review-Artefakt wird vom `finding-closure-reviewer`-Subagenten erzeugt (siehe
[`.claude/agents/finding-closure-reviewer.md`](../../.claude/agents/finding-closure-reviewer.md))
und im Rahmen des [`verify-finding`-Skills](../../.claude/skills/verify-finding/SKILL.md)
angestoßen. Es wird strukturell geprüft von
[`factory/guards/validate-review.py`](../guards/validate-review.py) und ist Teil des kanonischen
Runners (`python3 factory/guards/run-factory-checks.py`). Diese README-Datei selbst ist **kein**
Review-Artefakt und wird vom Guard ausdrücklich übersprungen.

## Runden sind append-only

Eine neue Review-Runde überschreibt **nie** eine frühere. Der Hook vergibt immer die nächste
freie Nummer. Damit bleibt ein `FAIL` dauerhaft auf dem Papier, auch wenn eine spätere Runde
`PASS` ergibt.

Vorher überschrieb jede Runde die vorherige. Das hieß: Reviewer fragen, `FAIL` bekommen, ohne
jede Änderung erneut fragen — und irgendwann steht ein sauberes `PASS` da, ohne Spur davon, dass
es je anders war. Bei einem stochastischen Reviewer ist das kein theoretischer Fall, sondern
schlicht eine Frage der Wiederholungen. Deshalb gilt jetzt zusätzlich:

**Ein `PASS` ist ungültig, wenn eine frühere Runde denselben `Reviewed Scope Hash` mit einem
anderen Ergebnis trägt.** Der legitime Weg nach einem `FAIL` ist: reparieren (das ändert den
Scope-Hash), dann neu reviewen.

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

Drei Felder stammen **nie** aus dem Text des Reviewers und nie von Hand — nur der Hook setzt sie:

- `Reviewer Agent Type` und `Reviewer Agent ID` aus den echten Ereignisdaten des Laufs.
- `Reviewed Scope Hash` aus dem tatsächlichen Repository-Zustand in dem Moment, in dem der
  Reviewer fertig war (siehe [`factory/guards/scope_hash.py`](../guards/scope_hash.py)).

Kann der Scope-Hash nicht bestimmt werden, schreibt der Hook **kein** Artefakt. Ein Review, das
sich keinem Codezustand zuordnen lässt, wäre von einem gültigen nicht zu unterscheiden — das
wäre schlechter als gar keines.

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

Finding: <Finding-ID, identisch mit dem Dateinamen>
Reviewer: <wer/was den Review durchgeführt hat>
Reviewer Agent Type: <agent_type aus dem SubagentStop-Event, nur vom Hook gesetzt>
Reviewer Agent ID: <agent_id aus dem SubagentStop-Event, nur vom Hook gesetzt>
Reviewed Commit: <Commit-Hash / Branch, oder Beschreibung der geprüften Diff-Basis>
Reviewed Scope Hash: sha256:<64 Hex-Zeichen>, nur vom Hook gesetzt
Result: PASS | FAIL | EXPERT_REVIEW_REQUIRED
Root Cause Addressed: <ja/nein + Begründung>
Regression Evidence Checked: <was geprüft wurde, und wie>
Guard Evidence Checked: <was geprüft wurde, und wie>
Scope Checked: <wurde der genehmigte Bauauftrags-Scope eingehalten>
Remaining Risks: <verbleibende Risiken, oder "Keine">
Findings And Objections: <konkrete Einwände, oder "Keine">
```

Alle dreizehn Felder sind Pflichtfelder (nicht leer, kein Platzhalter wie `TBD`), und jedes Feld
darf **höchstens einmal** vorkommen — zwei `Result`-Zeilen würden die Bedeutung von der
Parser-Reihenfolge abhängig machen. `Result` muss exakt einer der drei genannten Werte sein;
`Reviewer Agent Type` muss exakt `finding-closure-reviewer` sein, der einzige gültige
Reviewer-Agent-Typ. `Finding` muss mit der Finding-ID im Dateinamen übereinstimmen **und** auf
eine tatsächlich existierende Datei unter `factory/findings/` verweisen.

## Was der Guard prüft — und was nicht

`validate-review.py` prüft ausschließlich Struktur: kanonischer Rundenname, alle Felder
ausgefüllt und eindeutig, `Result` ein gültiger Wert, `Reviewer Agent Type` der eine gültige
Typ, `Reviewed Scope Hash` wohlgeformt, Finding-ID konsistent und existent. Er bewertet **nicht**,
ob der Inhalt inhaltlich zutrifft — ob die Root Cause wirklich behoben ist, ob die
Regressionsbeweise überzeugen, ob es übersehene Umgehungswege gibt. Diese inhaltliche Bewertung
liefert ausschließlich der unabhängige Reviewer; ein einfacher Python-Validator kann und soll sie
nicht ersetzen. Er kann auch `Reviewer Agent ID` nicht gegen ein Register gültiger IDs prüfen
(ein solches Register existiert nicht) — er verlangt dort nur einen vorhandenen,
nicht-platzhalterhaften Wert.

Ob der Scope-Hash noch **passt**, prüft nicht dieser Guard, sondern
[`validate-finding.py`](../guards/validate-finding.py) beim Closure: ein Review-Artefakt ist als
Momentaufnahme auch dann strukturell gültig, wenn der Code inzwischen weitergelaufen ist — es
taugt dann nur nicht mehr zum Schließen.

Ein Finding kann `READY_FOR_CLOSURE` oder `CLOSED` deshalb nur erreichen, wenn sein
`Review Artifact`-Feld auf die **eigene, neueste** Runde mit `Result: PASS` und passendem
Scope-Hash verweist. Die vollständige Liste der acht Bedingungen steht in
[`.claude/rules/factory-workflow.md`](../../.claude/rules/factory-workflow.md), Abschnitt "Die
Bindung des Reviews an Finding und Codezustand".
