# Bauauftrag: FACTORY-TRUST-CORE-1

**Typ: `FACTORY_CHANGE`.** Dieser Auftrag verändert die Kontrollebene, die ihn normalerweise
kontrollieren würde. Er darf deshalb nicht so behandelt werden, als sei seine eigene bestehende
Factory-Kontrolle bereits hinreichend unabhängig — siehe "Bootstrap-Situation" unten.

## Primäre Sicherheitsgrenze

Die eigentliche Reparatur ist **nicht** ein weiterer Guard, sondern eine Datenstruktur-Grenze:
Ein Review-Artefakt existiert nur noch als kanonische, append-only Runde
`factory/reviews/<Finding-ID>.round-<N>.md`, geschrieben ausschließlich vom SubagentStop-Hook,
und trägt einen vom Hook gestempelten `Reviewed Scope Hash` über den tatsächlich geprüften
Repository-Zustand. Damit ist "dieses Review gehört zu diesem Finding und zu diesem Code" keine
Behauptung mehr, die geprüft werden müsste, sondern eine Eigenschaft, die entweder vorliegt oder
nicht.

Die zweite Grenze derselben Art: die Kontrollebene der Factory ist aus den Schreibrechten der
normalen Finding-Arbeit entfernt und wird serverseitig gegen ein Manifest geprüft, statt sich
darauf zu verlassen, dass niemand sie anfasst.

## Verbindliche Reihenfolge

1. Negativtests schreiben und ROT beobachten (mit zitierter Fehlermeldung).
2. Bindungen umsetzen, bis dieselben Tests GRÜN sind.
3. Zentrale Guards ergänzen (Closure-Bindung, Control-Plane-Manifest, GitHub-Evidence).
4. Kanonischen Runner, Projekttests und die vollständige Testsuite laufen lassen.
5. Externe CI, unabhängiger Review des **gesamten** Control-Plane-Diffs, danach Closure.

## Acceptance Criteria

- Ein Finding kann `CLOSED` nur mit seinem eigenen, neuesten, bestandenen Review erreichen,
  dessen Scope-Hash dem aktuellen Repository-Stand entspricht.
- Kein Pfad außerhalb `factory/reviews/` und keine ältere Runde wird akzeptiert.
- Ein `FAIL` gegen denselben Codezustand kann nicht durch erneutes Fragen zu einem `PASS` werden.
- Eine Änderung an Guards, Skripten, Hooks, Agent, Skills, Regeln, CI-Workflow oder `CLAUDE.md`
  lässt den kanonischen Runner und damit CI fehlschlagen, solange das Manifest nicht bewusst neu
  gestempelt wurde.
- `required-check` liefert genau ein Urteil und einen eindeutigen Exit-Code; jeder GitHub-Fehler
  ist als `api_error` mit Exit ≠ 0 sichtbar.
- `merge` ohne erwarteten Head-SHA ist nicht möglich; ein abweichender Head führt zu
  `MERGE BLOCKED`.
- `Severity: P0` kann `IMPLEMENTING`, `VERIFYING`, `READY_FOR_CLOSURE` und `CLOSED` nicht
  erreichen.
- Ein nicht unterstützter `origin`-URL führt zu einem klaren Stopp, nie zu einer kaputten
  API-URL.

## Scope

Erlaubt und abschließend:

```
factory/guards/**                 (neu: scope_hash.py, validate-control-plane.py,
                                   gh_evidence.py, test_trust_core.py,
                                   test_control_plane.py, test_gh_evidence.py)
factory/scripts/gh-api.sh
factory/scripts/gh-query.sh
factory/scripts/factory-preflight.sh
factory/control-plane.sha256      (neu)
factory/findings/FACTORY-TRUST-CORE-1.md
factory/findings/EXAMPLE-FINDING.md
factory/build-orders/FACTORY-TRUST-CORE-1.md
factory/README.md
factory/ONBOARDING.md
factory/reviews/README.md         (Formatbeschreibung)
.claude/rules/factory-workflow.md
.claude/hooks/subagentstop-write-review.py
.claude/hooks/test_subagentstop_write_review.py
.claude/agents/finding-closure-reviewer.md
.claude/skills/verify-finding/SKILL.md
.claude/settings.json
.github/workflows/factory-ci.yml
CLAUDE.md
```

> **Korrektur, nachgetragen im Operational-Robustness-Paket.** Der Block oben nennt sich
> „abschließend", war es aber nicht. Zwei tatsächlich geänderte Dateien fehlten:
>
> ```
> .gitignore                                   (Defense-in-Depth-Haelfte des
>                                               Scope-Hash-Reinheitsfixes, im Abschnitt
>                                               "Nachtrag" unten beschrieben)
> .claude/hooks/test_stop_validate_findings.py (Fixture auf ein echtes Repository mit
>                                               gestempeltem Manifest umgestellt, zwei
>                                               Tests ergaenzt)
> ```
>
> Der unabhängige Review von Runde 1 hat das als Scope-Abweichung festgehalten. Beide gehören
> sachlich zu diesem Auftrag und verschärfen, statt zu schwächen — aber der Scope-Block hätte
> nachgezogen werden müssen. Er wird hier ausdrücklich **ergänzt und als Korrektur markiert**,
> nicht rückwirkend so dargestellt, als sei er immer vollständig gewesen. Das Review-Artefakt
> `factory/reviews/FACTORY-TRUST-CORE-1.round-1.md` bleibt unverändert; es ist append-only und
> hält den Einwand dauerhaft fest.

Weil dies ein `FACTORY_CHANGE` ist, liegen die geschützten Factory-Pfade hier ausnahmsweise
**im** Scope. Genau deshalb muss der unabhängige Review den vollständigen Control-Plane-Diff
prüfen und nicht nur den Anlass.

Ausdrücklich **nicht** im Scope (Paket 2/3 des Audits): F-10 bis F-16 und F-18 bis F-21 — kein
Bauauftrags-Guard, kein Resume-System, keine Parallelitätsarchitektur, kein generischer
Multi-Language-Testadapter, keine Änderung an der Branch-Protection-Prüfung.

## Red Regression Evidence

`python3 -m unittest factory.guards.test_trust_core` gegen die unveränderten Guards, vor jeder
Reparatur:

```
Ran 29 tests in 2.721s
FAILED (failures=17)
```

17 von 29 Tests schlugen fehl, jeweils mit derselben Meldung „guard accepted what it must
reject". Die fehlgeschlagenen Tests, nach Invariante gruppiert:

```
ReviewArtifactPathTests   test_arbitrary_file_containing_result_pass_is_rejected      (F-01)
                          test_absolute_path_outside_reviews_is_rejected              (F-01)
                          test_parent_traversal_is_rejected                           (F-01)
                          test_symlink_escape_out_of_reviews_dir_is_rejected          (F-01)
                          test_review_artifact_that_fails_the_review_guard_blocks…    (F-01)
ReviewIdentityTests       test_finding_cannot_close_on_another_findings_review        (F-02)
                          test_review_whose_finding_field_mismatches_its_filename…    (F-02)
ScopeBindingTests         test_pass_is_invalid_after_the_reviewed_code_changed        (F-03)
                          test_wrong_scope_hash_is_rejected                           (F-03)
ReviewRoundTests          test_fail_then_pass_against_the_same_code_state_is_rejected (F-04)
                          test_an_older_pass_round_cannot_be_used_when_a_newer…       (F-04)
SeverityGateTests         test_severity_is_required_from_analyzed_onwards             (F-09)
                          test_unknown_severity_is_rejected                           (F-09)
                          test_p0_cannot_reach_implementing                           (F-09)
                          test_p0_cannot_reach_verifying                              (F-09)
                          test_p0_cannot_reach_closed_even_with_a_valid_review        (F-09)
CanonicalRunnerTests      test_runner_rejects_the_arbitrary_file_bypass               (F-01)
```

Beispielhafte Originalausgabe für den zentralen Bypass:

```
AssertionError: 0 != 1 : guard accepted what it must reject.
stdout:
GÜLTIG: …/factory/findings/F-1.md (Status: VERIFYING)
```

Und derselbe Bypass durch den kanonischen Runner, in einer isolierten Kopie mit **leerem**
`factory/reviews/`:

```
[OK]     finding-validator: F-100.md
Keine Review-Artefakte unter …/factory/reviews -- nichts zu pruefen.
Factory-Checks: ALLE BESTANDEN
EXIT:0
```

## Nachtrag: von der externen CI gefundene Lücke (Scope-Hash-Reinheit)

Der erste CI-Lauf (Run 31884177584, Python 3.11) war **rot**, während lokal alles grün war. Der
Log zeigte genau einen Fehlschlag:
`ScopeHashPurityTests`-Vorläufer `test_writing_a_finding_does_not_change_the_hash` —
`'sha256:e2b96d…' != 'sha256:3e39e7…'`.

**Ursache, reproduziert statt vermutet:** Der SubagentStop-Hook und `validate-finding.py`
*importieren* `scope_hash`. CPython legt dabei standardmäßig
`factory/guards/__pycache__/scope_hash.cpython-311.pyc` **neben die Quelle**. Ein anschließendes
`git add -A` trackt diese generierte Datei — und da der Scope-Hash über alle *getrackten*
Dateien läuft, ändert er sich ohne jede inhaltliche Änderung. **Das Messen veränderte den
gemessenen Zustand.** Lokal unsichtbar, weil das dort verwendete `python3`
`sys.pycache_prefix` auf einen zentralen Cache umlenkt.

Das ist kein Testartefakt, sondern ein echter F-03-Defekt: im normalen Ablauf (Reviewer läuft →
Agent committet mit `git add -A`) hätte er ein soeben erteiltes `PASS` still entwertet.

Reproduktion in einer Wegwerf-Kopie, mit `sitecustomize.py` auf CPython-Standardverhalten
normalisiert:

```
--- AKTUELLER Hook, ohne .gitignore (= CI-Bedingung) ---
  Bytecode im Projekt:              ['factory/guards/__pycache__/scope_hash.cpython-39.pyc']
  davon getrackt nach 'git add -A': ['factory/guards/__pycache__/scope_hash.cpython-39.pyc']
  ERGEBNIS: VERSCHIEDEN (Test faellt durch)
--- GEPATCHTER Hook (sys.dont_write_bytecode) ---
  Bytecode im Projekt:              (keiner)
  ERGEBNIS: GLEICH (Test besteht)
```

**Zielinvariante:** Das Berechnen oder Importieren des Scope-Hash-Mechanismus darf den
gemessenen Zustand niemals selbst verändern.

**Minimaler robuster Fix.** Die Invariante lässt sich nicht in `scope_hash.py` selbst
durchsetzen — CPython schreibt die `.pyc`, *bevor* der Modulcode läuft. Sie muss deshalb jeder
Importeur setzen, und das sind genau zwei: `.claude/hooks/subagentstop-write-review.py` und
`factory/guards/validate-finding.py`, je eine Zeile `sys.dont_write_bytecode = True`. Alle
übrigen Factory-Skripte rufen den Mechanismus als Subprozess auf, wobei per CPython-Semantik
kein Bytecode entsteht. Als Defense in Depth deckt `.gitignore` (`__pycache__/`, `*.py[cod]`)
jedes andere Werkzeug im Repository ab, insbesondere `python3 -m unittest`.

**Bewusst nicht getan:** kein Pfad wird nachträglich aus dem Hash ausgeschlossen (ein
sourceless `.pyc` kann Code ausführen — eine Ausnahmeliste wäre genau der blinde Fleck, den
dieser Auftrag beseitigt), keine plattformspezifische Sonderbehandlung, keine Änderung der
Review-/Commit-Bindungsinvariante.

**Regressionstests** (`ScopeHashPurityTests`, 8 Tests). Sie normalisieren den Interpreter über
ein `sitecustomize.py` **außerhalb** der Fixture auf CPythons dokumentierten Standard
(`sys.pycache_prefix = None`) — das *entfernt* eine Plattform-Sonderbehandlung, statt eine
einzuführen — und entfernen ein geerbtes `PYTHONDONTWRITEBYTECODE` aus der Umgebung, damit sie
nicht leer bestehen können. Rot/Grün-Trennung:

```
ohne Fix:  FAIL test_the_finding_validator_writes_no_bytecode
           FAIL test_git_add_after_measuring_tracks_no_bytecode
           FAIL test_scope_hash_is_unchanged_by_measuring_it
           FAIL test_the_review_binding_survives_a_measurement
           Ran 8 tests -- FAILED (failures=4)
mit Fix:   Ran 8 tests -- OK
```

Die vier übrigen Tests bestehen in **beiden** Läufen und sichern gegen Über-Reparatur ab: eine
echte Codeänderung verändert den Hash weiterhin, ein absichtlich getracktes `.pyc` bleibt Teil
des Hashes, und die Zahl der gehashten Dateien wird gegen die tatsächliche `git ls-files`-Liste
gezählt, sodass genau zwei Ausschlüsse (`factory/findings/`, `factory/reviews/`) nachweisbar
bleiben.

**Nebenfund in der Fixture:** Sie stempelte `factory/control-plane.sha256` nach dem
Initial-Commit, es war also ungetrackt und wurde beim ersten `git add -A` in den Hash gezogen —
optisch identisch mit dem Bytecode-Defekt. Die Fixture setzt ihren Zustand jetzt vorab. Kein
Produktionsdefekt: im echten Repository ist das Manifest committet.

## Green Runtime Fix Evidence

Alle folgenden Läufe stammen aus dem Zustand, der in diesem Branch reviewt und gemergt wird.

**Trust-Core-Negativtests — dieselben 29 Tests, die vorher 17 Fehlschläge lieferten:**

```
$ python3 -m unittest factory.guards.test_trust_core
Ran 29 tests in 3.438s
OK
```

**Vollständige Guard-Suite (8 Module, inklusive der acht neuen Purity-Tests):**

```
$ python3 -m unittest factory.guards.test_validate_finding factory.guards.test_validate_review \
    factory.guards.test_run_factory_checks factory.guards.test_create_finding_worktree \
    factory.guards.test_factory_preflight factory.guards.test_trust_core \
    factory.guards.test_control_plane factory.guards.test_gh_evidence
Ran 178 tests in 24.001s
OK
```

**Reinheit nach dem kompletten lokalen Lauf** -- weder Guards noch Tests hinterlassen
getrackten Bytecode:

```
$ git ls-files | grep -E "__pycache__|\.pyc$"
(keine Treffer)
```

**SubagentStop-/Provenienz-Tests (append-only Runden, Scope-Bindung, verworfene
Reviewer-Provenienz):**

```
$ python3 .claude/hooks/test_subagentstop_write_review.py
Ran 24 tests in 2.479s
OK
```

**Stop-Hook-Tests (inkl. P0-Stopp und Control-Plane-Drift):**

```
$ python3 .claude/hooks/test_stop_validate_findings.py
Ran 7 tests in 1.640s
OK
```

**Sandbox-Live-Schreibprobe gegen das echte `factory/reviews/` — bestanden, nicht
übersprungen, die OS-Sandbox blockiert also tatsächlich:**

```
$ python3 .claude/hooks/test_sandbox_protects_reviews.py
Ran 1 test in 0.028s
OK
```

**Zentraler Guard, live gegen das echte Repository.** Nachdem die sechs geschützten
Control-Plane-Dateien extern übernommen worden waren, meldete der Guard sie namentlich, bevor
neu gestempelt wurde — das ist der Nachweis, dass er echte Drift erkennt und nicht nur in
Fixtures funktioniert:

```
$ python3 factory/guards/validate-control-plane.py
CONTROL_PLANE_VERAENDERT: die Kontrollebene weicht vom gestempelten Manifest ab.
  - Inhalt geaendert: .claude/agents/finding-closure-reviewer.md (Manifest 019f1824a6f4…, aktuell cb3872b9ce57…).
  - Inhalt geaendert: .claude/hooks/subagentstop-write-review.py (Manifest 4d7b704cf1b5…, aktuell eb2faf437d68…).
  - Inhalt geaendert: .claude/hooks/test_stop_validate_findings.py (Manifest ba909c20c314…, aktuell adc276021592…).
  - Inhalt geaendert: .claude/hooks/test_subagentstop_write_review.py (Manifest 37191219da47…, aktuell 6dfe7f860f16…).
  - Inhalt geaendert: .claude/settings.json (Manifest 374a85b42280…, aktuell db4d52581595…).
  - Inhalt geaendert: .claude/skills/verify-finding/SKILL.md (Manifest 6cf3065d4a30…, aktuell 18b6452a37c9…).
EXIT:1
```

Nach bewusstem Neustempeln:

```
$ python3 factory/guards/validate-control-plane.py --update
Control-Plane-Manifest neu gestempelt: … (30 Dateien)
$ python3 factory/guards/validate-control-plane.py
Control-Plane unveraendert (30 Dateien gegen Manifest geprueft).
```

**Kanonischer Runner und Projekttests:**

```
$ python3 factory/guards/run-factory-checks.py
[OK]     finding-validator: EXAMPLE-FINDING.md
[OK]     finding-validator: FACTORY-TRUST-CORE-1.md
[OK]     control-plane-guard: Kontrollebene unveraendert
Factory-Checks: ALLE BESTANDEN

$ python3 factory/guards/run-project-tests.py
Kein Projektverzeichnis unter …/app -- nichts zu pruefen.
```

**Preflight (voll, mit Netz).** Alle Factory- und GitHub-Voraussetzungen grün, inklusive der neu
geprüften Control-Plane-Sperren und des Manifests. Der einzige offene Punkt ist
maschinenlokal und nicht Teil der Vorlage (`.claude/settings.local.json` ist gitignored) — er
belegt zugleich, dass die neue `too_broad`-Prüfung auf echten Daten greift:

```
[OK]      Geschuetzte Factory-/Review-/Hook-Dateien und Hooks korrekt in .claude/settings.json.
[FEHLT]   Zu breite lokale Freigaben: Bash(python3 -)
[OK]      Control-Plane unveraendert gegenueber factory/control-plane.sha256.
[OK]      Required Status Check 'factory-checks' ist auf main konfiguriert.
FACTORY_PREFLIGHT: BLOCKED (1 offene Voraussetzung(en))
```

**Externe CI:** siehe `CI Evidence` im Finding.

## Bootstrap-Situation (ausdrücklich dokumentiert)

Dieser Auftrag repariert die Mechanismen, die ihn prüfen. Daraus folgen drei Dinge, die nicht
weggeredet werden:

1. **Die alte Kontrollebene hat ihre eigene Reparatur nicht bewiesen.** Der rote Testlauf oben
   lief gegen die alten Guards und zeigt, dass sie die Lücken *nicht* erkannten. Der grüne
   Testlauf danach läuft gegen die neuen Guards. Kein Lauf beweist die Korrektheit der neuen
   Guards aus sich selbst heraus — das leisten die Negativtests, die externe CI und der
   unabhängige Review.
2. **Das Control-Plane-Manifest wird in genau diesem Auftrag zum ersten Mal gestempelt.** Ein
   Manifest, das im selben Commit entsteht wie die Dateien, die es beschreibt, beweist für diesen
   Commit nichts. Sein Wert beginnt beim *nächsten* Finding: ab dann ist jede Abweichung sichtbar.
3. **Dateien der Kontrollebene konnten vom implementierenden Agenten nicht geschrieben werden**
   (`.claude/hooks/`, `.claude/agents/`, `.claude/skills/`, `.claude/settings.json`,
   `factory/reviews/README.md`), weil genau dieser Schutz greift. Sie wurden als Patches
   ausgeliefert und von einem Menschen angewandt. Das ist keine Umgehung des Schutzes, sondern
   sein bestimmungsgemäßes Verhalten — und der Grund, warum ein `FACTORY_CHANGE` eine menschliche
   Entscheidung verlangt.

> **Korrektur zu Punkt 3, nachgetragen im Operational-Robustness-Paket.** Die ursprüngliche
> Fassung schrieb „**Vier** Dateien" und listete darunter fünf Pfadeinträge. Der unabhängige
> Review von Runde 1 hat die Zahl als falsch und die Zeitachse als unvollständig beanstandet.
> Richtig ist:
>
> - Extern eingespielt wurden **sechs** geschützte Control-Plane-Dateien (plus
>   `factory/reviews/README.md`, das kein Manifest-Eintrag ist):
>   `.claude/agents/finding-closure-reviewer.md`, `.claude/hooks/subagentstop-write-review.py`,
>   `.claude/hooks/test_stop_validate_findings.py`,
>   `.claude/hooks/test_subagentstop_write_review.py`, `.claude/settings.json` und
>   `.claude/skills/verify-finding/SKILL.md`. Der Abschnitt „Green Runtime Fix Evidence" oben
>   nannte bereits korrekt „die sechs geschützten Control-Plane-Dateien" — die beiden Stellen
>   widersprachen sich also.
> - Es gab **zwei** externe Übernahmerunden, nicht eine. Die zweite war nötig, nachdem die
>   externe CI den Scope-Hash-Reinheitsdefekt aufgedeckt hatte: dafür mussten
>   `.claude/hooks/subagentstop-write-review.py` und
>   `.claude/hooks/test_subagentstop_write_review.py` ein zweites Mal extern angewandt werden.
>   Erkennbar ist das daran, dass die im Guard-Output oben zitierten Hashes dieser beiden Dateien
>   (`eb2faf43…`, `6dfe7f86…`) nicht die endgültigen Manifest-Hashes sind (`3cac7ddd…`,
>   `8d98a894…`); genau darauf hat der Reviewer hingewiesen.
>
> Nichts davon war verschwiegen — die Zahl und die Zeitachse waren falsch. Sie werden hier
> korrigiert; das Review-Artefakt bleibt unverändert.
