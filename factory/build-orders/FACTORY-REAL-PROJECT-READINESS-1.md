# Bauauftrag: FACTORY-REAL-PROJECT-READINESS-1

**Typ: `FACTORY_CHANGE`.** Dieser Auftrag verändert die Kontrollebene, die ihn kontrollieren
würde. Die geschützten Dateien können vom implementierenden Agenten nicht selbst geschrieben
werden; siehe „Bootstrap-Situation" unten für die vollständige Offenlegung.

## Primäre Sicherheitsgrenze

Die eigentliche Reparatur ist an allen drei Stellen dieselbe Bewegung: **eine Annahme über die
Umgebung wird durch eine Aussage der Umgebung ersetzt.** Die Factory hört auf zu wissen, wie das
Zielprojekt gebaut ist, und verlangt stattdessen, dass das Zielprojekt es ihr sagt.

Konkret an drei Stellen:

- **F-21** — Die Factory kennt das Testframework des Produkts nicht mehr. Sie führt aus, was
  `factory/project-tests.conf` deklariert, als Argumentliste ohne Shell. Sie kann deshalb nicht
  mehr „nichts gefunden" mit „nichts zu prüfen" verwechseln, weil sie gar nicht mehr sucht. Die
  Unterscheidung zwischen `TEMPLATE_WITHOUT_PRODUCT` und `REAL_PROJECT_WITHOUT_TEST_CONFIGURATION`
  ist die eigentliche Grenze: nur der erste Zustand darf ohne Produkttests grün sein.
- **F-18** — Lifecycle-Metadaten haben genau einen Ort, den kanonischen Metadatenblock. Fließtext
  kann sie nicht mehr setzen, weil sie dort nicht mehr gesucht werden. Der P0-Hard-Stop hängt
  damit an einer Struktur statt an einer Textreihenfolge.
- **F-15** — Für den Worktree wird keine Zusicherung formuliert, die nicht beobachtet wurde. Das
  Ergebnis ist entweder A (bewiesen unterstützt) oder B (bewusst sequentiell, technisch
  abgesichert) — nicht eine abgeschwächte Formulierung dazwischen.

Die zweite Grenze derselben Art: **eine nicht konfigurierte Testpflicht ist keine erfüllte
Testpflicht.** `factory/project-tests.conf` gehört deshalb in die Control Plane. Wer bestimmen
kann, welche Produkttests als gültige Verification gelten, darf das nicht während normaler
Finding-Arbeit tun.

## Verbindliche Reihenfolge

1. Negativtests schreiben und ROT beobachten (mit zitierter Ausgabe), gegen den unveränderten
   Produktionsstand im echten Repository.
2. F-21 vollständig umsetzen, bis dieselben Tests GRÜN sind.
3. F-18 vollständig umsetzen, mit allen bestehenden Findings und Bauaufträgen als
   Rückwärtskompatibilitäts-Korpus.
4. F-15 durch echten Worktree-/Sandbox-Beobachtungslauf im echten Repository entscheiden und das
   Ergebnis (A oder B) technisch absichern.
5. Integrationsleitfaden in `ONBOARDING.md`/`README.md` vervollständigen.
6. Kanonischen Runner, Projekttests und die vollständige entdeckte Testsuite laufen lassen;
   ausdrücklich belegen, dass die Pakete 1 und 2 nicht wieder geöffnet werden.
7. Externe CI, unabhängiger Review des **gesamten** Control-Plane-Diffs, danach Closure.

## Acceptance Criteria

- `factory/project-tests.conf` existiert, ist versioniert, steht im Control-Plane-Manifest, und
  jede dort deklarierte Testsuite wird bei jedem Lauf tatsächlich ausgeführt.
- Ein Exit-Code ungleich 0 eines einzigen konfigurierten Kommandos führt zum Gesamtfehler; ein
  späteres rotes Kommando kann von einem früheren grünen nicht überdeckt werden.
- Ein Repository mit Produktcode, aber ohne Testkonfiguration, meldet
  `REAL_PROJECT_WITHOUT_TEST_CONFIGURATION` und einen Exit-Code ungleich 0.
- Das reine Template ohne Produktcode meldet `TEMPLATE_WITHOUT_PRODUCT` und ist erwartbar grün;
  dieser Zustand ist im Klartext ausgewiesen, nicht implizit.
- Kein Kommando wird über eine Shell interpretiert; kein Kommando stammt aus Finding-Inhalten.
- `Status` und `Severity` werden ausschließlich aus dem kanonischen Metadatenblock gelesen. Ein
  zitiertes `Status: CLOSED` oder `Severity: P0` im Fließtext ändert die Bewertung nicht.
- Der P0-Hard-Stop greift bei einem Finding, dessen kanonisches `Severity: P0` ist, unabhängig
  davon, welche Severity irgendwo im Text zitiert wird.
- Mehrzeilige Analyse- und Evidence-Felder werden vollständig gelesen; ein Platzhalter in einer
  Fortsetzungszeile wird erkannt.
- Alle bestehenden Findings und Bauaufträge dieses Repositories bleiben ohne Änderung gültig.
- Für F-15 steht am Ende eindeutig A oder B im Repository — keine unbewiesene
  Parallelitätsbehauptung.
- Die Invarianten aus F-01…F-14, F-16, F-17, F-19 und F-20 sind nachweislich unverändert wirksam.

## Scope

Erlaubt und abschließend:

```
factory/project-tests.conf                      (neu, Control Plane)
factory/guards/project_tests.py                 (neu)
factory/guards/finding_format.py                (neu)
factory/guards/test_project_tests.py            (neu)
factory/guards/test_finding_format.py           (neu)
factory/guards/test_worktree_protection.py      (neu)
factory/guards/run-project-tests.py
factory/guards/validate-finding.py
factory/guards/validate-build-order.py
factory/guards/run-factory-checks.py
factory/guards/validate-control-plane.py
factory/findings/FACTORY-REAL-PROJECT-READINESS-1.md
factory/build-orders/FACTORY-REAL-PROJECT-READINESS-1.md
factory/ONBOARDING.md
factory/README.md
CLAUDE.md
.claude/rules/factory-workflow.md
.claude/settings.json
.github/workflows/factory-ci.yml
factory/control-plane.sha256
```

Alles andere ist out of scope. `factory/reviews/**` wird nicht angefasst — Review-Runden sind
append-only und entstehen ausschließlich durch den `SubagentStop`-Hook. Die bereits geschlossenen
Findings `FACTORY-TRUST-CORE-1` und `FACTORY-OPS-ROBUSTNESS-1` und ihre Bauaufträge werden nicht
verändert; sie dienen als Regressionskorpus.

## Red Regression Evidence

Alle Läufe gegen den unveränderten Produktionsstand im echten Repository
(`/Users/clauskopp/Downloads/software-factory-template`, Branch
`factory-change/real-project-readiness-1`, HEAD `682aa95d211e1cc30cb80e182aed880adfbf0102` =
`origin/main`), **nicht** gegen eine Kopie.

**F-21 — ein reales Projekt wird still grün.** Angelegt wurde ein realistischer, nicht-python
Produktbaum mit einem absichtlich fehlschlagenden Test (`app/cmd/main.go`,
`app/cmd/main_test.go` mit `t.Fatal("dieser Produkttest ist absichtlich rot")`). Danach der
kanonische Produkttest-Einstiegspunkt:

```
$ python3 factory/guards/run-project-tests.py; echo "EXIT=$?"
Keine Tests unter /Users/clauskopp/Downloads/software-factory-template/app gefunden -- nichts zu pruefen.
EXIT=0
```

Die Factory meldet Erfolg für ein Projekt, dessen Tests sie nie ausgeführt hat und dessen
einziger Test rot ist. Der temporäre Produktbaum wurde danach wieder entfernt.

**F-18 — der P0-Hard-Stop wird durch zitierten Text umgangen.** Der echte Parser aus
`factory/guards/validate-finding.py` wurde direkt gegen realistischen Finding-Text ausgeführt:

```
=== Fall 1: zitiertes Severity: P1 vor dem echten Feld Severity: P0 ===
  geparster Status:   'OPEN'
  geparste Severity:  'P1'
  ERWARTET (kanonisch): Status='IMPLEMENTING', Severity='P0' -> P0-Hard-Stop muss greifen
  P0-Hard-Stop ausgeloest: False  []

=== Fall 2: mehrzeilige Root Cause ===
  Root Cause geparst: 'Der Dienst laeuft in einen Deadlock, weil zwei Locks in'
  ERWARTET: der vollstaendige, dreizeilige Text

=== Fall 3: Platzhalter in Zeile 2 eines mehrzeiligen Pflichtfelds ===
  Risk Assessment geparst: 'Erste Zeile klingt nach Inhalt.'
  Platzhalter erkannt: False  []
  ERWARTET: erkannt, weil der Wert als Ganzes ein TBD enthaelt
```

Fall 1 ist der schwerwiegendste: ein Finding, dessen kanonische Metadaten `Status: IMPLEMENTING`
und `Severity: P0` lauten, wird als `OPEN`/`P1` gelesen, weil ein aus dem Ticketsystem kopierter
Block weiter oben steht. Der P0-Hard-Stop aus Audit-Befund F-09 löst nicht aus — eine bereits
geschlossene Invariante hängt damit an einer Textreihenfolge.

**Ehrlich festgehalten, weil es die Evidence ehrlich hält:** ein vierter geprüfter Fall
(Fortsetzungszeilen wie `Schritt 1: …` erzeugen Phantom-Felder) trat **nicht** ein.
`FIELD_LINE_RE` verlangt `[A-Za-z][A-Za-z ]*` vor dem Doppelpunkt, und `Schritt 1` enthält eine
Ziffer. Der Fall wird deshalb nicht als Defekt geführt.

**F-15 — der Worktree-Modus ist unter der Factory-Sandbox nicht verfügbar.** Der Nachweis ist der
Beobachtungslauf selbst; er wurde im echten Repository mit dem kanonischen Mechanismus geführt:

```
$ factory/scripts/create-finding-worktree.sh create 682aa95d211e1cc30cb80e182aed880adfbf0102 .claude/worktrees/F15-PROBE fix/F15-PROBE
Preparing worktree (new branch 'fix/F15-PROBE')
error: unable to create file .claude/agents/finding-closure-reviewer.md: Operation not permitted
fatal: Could not reset index file to revision 'HEAD'.

$ factory/scripts/create-finding-worktree.sh create 682aa95d211e1cc30cb80e182aed880adfbf0102 wt-probe fix/F15-PROBE2
Preparing worktree (new branch 'fix/F15-PROBE2')
error: unable to create file .claude/agents/finding-closure-reviewer.md: Operation not permitted
fatal: Could not reset index file to revision 'HEAD'.
```

Zweimal, einmal mit dem Ziel innerhalb und einmal außerhalb von `.claude/` — es liegt also nicht
an der Platzierung. Einen Worktree auszuchecken heißt, jede getrackte Datei zu schreiben,
einschließlich der Kontrollebene; genau die ist gesperrt. Der F-05-Schutz und der Worktree-Modus
schließen einander konstruktionsbedingt aus. Die beiden Probe-Branches wurden anschließend
entfernt.

Das ist **keine Sandbox-Störung**, sondern eine reale Inkompatibilität, und sie wird ausdrücklich
**nicht** durch Lockerung von `permissions.deny`, `denyWrite` oder des Control-Plane-Schutzes
behoben. Ergebnis: **B — Factory v1 ist bewusst sequentiell.**

Nach der Reparatur blockiert das Skript denselben Aufruf **vorbeugend**, bevor `git worktree add`
überhaupt versucht wird, sodass kein halb erzeugter Worktree und kein verwaister Branch
zurückbleibt:

```
SANDBOX_WORKTREE_INCOMPATIBLE: Ein Finding-Worktree kann in dieser Sitzung nicht angelegt werden.
grund: Einen Worktree auszuchecken heisst, jede getrackte Datei zu schreiben -- einschliesslich der Kontrollebene (.claude/agents/**, .claude/hooks/**, factory/guards/**). Genau die ist fuer diesen Agenten gesperrt (permissions.deny + sandbox.filesystem.denyWrite). Positiv beobachtet: das Schreiben von '.claude/agents/.worktree-sandbox-probe' wurde verweigert.
einordnung: Das ist der Schutz aus Audit-Befund F-05 in bestimmungsgemaesser Funktion -- keine Stoerung, kein transienter Fehler und nichts, was durch Lockern von Berechtigungen zu 'reparieren' waere.
stattdessen: Factory v1 ist bewusst sequentiell spezifiziert (Audit-Befund F-15, Ergebnis B). Ein Finding nach dem anderen, im Hauptrepository, auf einem eigenen Branch -- siehe CLAUDE.md, 'Mehrere Findings: bewusst sequentiell (der unterstuetzte Ablauf)'. Parallele Claude-Worktree-Sessions sind als v1.x-Faehigkeit vorgemerkt, nicht Teil von v1.
```

Danach verifiziert: `git worktree list` zeigt nur das Hauptrepository, `git branch --list "fix/F15*"`
ist leer.

**Nachtrag — der Befund ist präziser zu fassen.** Beim Verifikationslauf im echten Repository
zeigte sich, dass „ein Worktree lässt sich nicht anlegen" nur **innerhalb** der Projektwurzel
stimmt. Die `denyWrite`-Regeln einer laufenden Claude-Code-Session sind an **deren aktuelle
Projektwurzel** gebunden; für Pfade außerhalb greifen sie nicht:

```
$ touch "$TMPDIR/f15-scope-probe/factory/guards/validate-finding.py"
AUSSERHALB DES REPOS: factory/guards BESCHREIBBAR
$ touch "$TMPDIR/f15-scope-probe/.claude/agents/x.md"
AUSSERHALB DES REPOS: .claude/agents BESCHREIBBAR
```

Ein Worktree außerhalb der Projektwurzel gelingt deshalb — und ist **aus der erzeugenden Session
heraus** nicht durch deren Pfadgrenzen geschützt. Diese Session könnte dort jeden Guard
umschreiben, der sie beurteilt. Daraus folgt die verbindliche v1-Regel: **eine laufende
Factory-Session erzeugt keinen externen Worktree und arbeitet nicht darin weiter.**

**Ausdrücklich nicht behauptet, weil nicht getestet:** dass eine *neu gestartete*
Claude-Code-Session, deren eigene Projektwurzel dieser Worktree ist, keinen Schutz hätte. Für
Factory v1 ist das ohne Belang — v1 ist bewusst sequentiell und unterstützt Worktree-Parallelität
nicht, also wird die Frage nicht untersucht. Sie ungeprüft zu beantworten wäre genau der Fehler,
den dieses Paket beseitigt.

Aufgefallen ist das an einer verwaisten Worktree-Registrierung, die ein früherer Lauf des
ursprünglichen (fehlerhaften) Tests hinterlassen hatte — der Test legte selbst einen Worktree in
`$TMPDIR` an, was **gelang**. Sie ließ sich aus der Session nicht mehr entfernen:

```
$ git worktree prune
error: failed to delete '.git/worktrees/probe': Operation not permitted
$ git branch -D f15-probe-test
error: cannot delete branch 'f15-probe-test' used by worktree at '/private/tmp/.../probe'
```

Der Test wurde daraufhin ersetzt: er legt keinen Worktree mehr an, sondern prüft die Invariante
direkt (Control-Plane-Pfade im Repository nicht beschreibbar, außerhalb beschreibbar) und schlägt
an, wenn eine verwaiste Registrierung existiert. Ein Test darf keinen Schreibzugriff brauchen, den
der geprüfte Agent nicht hat.

## Green Runtime Fix Evidence

Alle Läufe im echten Repository auf Branch `factory-change/real-project-readiness-1`, Basis
`682aa95d211e1cc30cb80e182aed880adfbf0102`, nach dem vierten und letzten externen Apply-Schritt.
Vorher verifiziert: alle 25 vorbereiteten Dateien byte-identisch eingespielt (25/25, 0 abweichend).

**Vollständige entdeckte Testsuite — entscheidend die letzten drei Zeilen:**

```
Ran 355 tests in 53.9s
OK

ci_tests_run: 355
ci_test_failures: 0
ci_test_errors: 0
ci_tests_skipped: 0
SANDBOX_VERIFICATION: performed (1 Test(s) real ausgefuehrt)
FACTORY_TESTS: ALLE BESTANDEN
```

`ci_tests_skipped: 0` zusammen mit `SANDBOX_VERIFICATION: performed` belegt, dass **beide**
Sandbox-abhängigen Tests real ausgeführt wurden — der OS-Sandbox-Test für `factory/reviews/` und
der F-15-Beobachtungstest. Ein übersprungener Sandbox-Test wäre nach F-19 kein Nachweis.

**Kanonischer Runner:**

```
[OK]     finding-validator: EXAMPLE-FINDING.md
[OK]     finding-validator: FACTORY-OPS-ROBUSTNESS-1.md
[OK]     finding-validator: FACTORY-REAL-PROJECT-READINESS-1.md
[OK]     finding-validator: FACTORY-TRUST-CORE-1.md
[OK]     build-order-guard: FACTORY-OPS-ROBUSTNESS-1.md
[OK]     build-order-guard: FACTORY-REAL-PROJECT-READINESS-1.md
[OK]     build-order-guard: FACTORY-TRUST-CORE-1.md
[OK]     review-guard: FACTORY-OPS-ROBUSTNESS-1.round-1.md
[OK]     review-guard: FACTORY-TRUST-CORE-1.round-1.md
[OK]     control-plane-guard: Kontrollebene unveraendert
[OK]     project-tests-guard: TEMPLATE_WITHOUT_PRODUCT (Vorlage ohne Produktcode -- erwartet)
Factory-Checks: ALLE BESTANDEN
```

**F-21 — Projekt-Test-Adapter, alle drei Zustände.** Der Template-Zustand real im Repository:

```
$ python3 factory/guards/run-project-tests.py; echo "EXIT=$?"
PROJECT_TESTS: TEMPLATE_WITHOUT_PRODUCT
Keine getrackten Dateien ausserhalb der Factory-Pfade und 'mode: template' -- eine reine Kopie der Vorlage ohne Produktcode.
Das ist der EINZIGE Zustand, in dem null Produkttests als bestanden gelten. Sobald Produktcode dazukommt, ist eine Testkonfiguration Pflicht (siehe factory/ONBOARDING.md).
EXIT=0
```

Die beiden anderen Zustände sind in `test_project_tests.py` gegen echte Wegwerf-Repositories
gepinnt: `test_missing_configuration_file_with_product_code_is_never_a_pass` und
`test_adding_product_code_turns_that_template_into_a_blocker` (gleiche fehlende Datei, andere
Pflicht), sowie die tatsächliche Ausführung konfigurierter Suiten
(`test_multiple_suites_all_run` prüft Marker-Dateien beider Kommandos,
`test_second_suite_red_makes_the_whole_run_fail` belegt, dass eine spätere rote Suite nicht von
einer früheren grünen überdeckt wird).

**F-15 — präventive Blockade, real im Repository, ohne jede Mutation:**

```
$ factory/scripts/create-finding-worktree.sh create 682aa95... .claude/worktrees/F15-FINAL fix/F15-FINAL
SANDBOX_WORKTREE_INCOMPATIBLE: Ein Finding-Worktree kann in dieser Sitzung nicht angelegt werden.
grund: ... Positiv beobachtet: das Schreiben von '.claude/agents/.worktree-sandbox-probe' wurde verweigert.
einordnung: Das ist der Schutz aus Audit-Befund F-05 in bestimmungsgemaesser Funktion ...
stattdessen: Factory v1 ist bewusst sequentiell spezifiziert (Audit-Befund F-15, Ergebnis B) ...
```

Danach `git worktree list` → nur das Hauptrepository; `git branch --list "fix/F15*"` → leer. Die
Blockade greift **vor** `git worktree add`, es entsteht also weder ein Worktree noch ein Branch
noch eine Registrierung.

**Neue Regressionsmodule zusammen:**

```
$ python3 -m unittest factory.guards.test_finding_format factory.guards.test_project_tests factory.guards.test_worktree_protection
Ran 56 tests in 3.4s
OK
```

**Regression gegen die abgeschlossenen Pakete 1 und 2:**

```
$ python3 -m unittest factory.guards.test_trust_core factory.guards.test_ops_robustness factory.guards.test_closure_history factory.guards.test_build_order
Ran 120 tests in 19.2s
OK
```

Damit sind Review-/Scope-Bindung, append-only Reviews, Control-Plane-Schutz, P0-Hard-Stop,
deterministische CI-Evidence, Merge mit erwartetem Head-SHA, Preflight-Semantik, Resume-State,
Testentdeckung und die nicht-interaktive Credential-Abfrage nachweislich unverändert wirksam.

## Bootstrap-Situation

Dieselbe Offenlegung wie bei `FACTORY-TRUST-CORE-1` und `FACTORY-OPS-ROBUSTNESS-1`, weil sie
weiterhin zutrifft: Die geschützten Control-Plane-Pfade sind für den implementierenden Agenten
lokal gesperrt (`permissions.deny` + `sandbox.filesystem.denyWrite`). Er kann die Reparatur
deshalb nicht selbst einspielen. Der getestete Stand wird in einem Scratchpad vorbereitet und
über **einen** externen, menschlich ausgeführten Apply-Schritt eingespielt; danach wird jede
eingespielte Datei byte-identisch gegen die Vorbereitung verifiziert, und sämtliche Tests laufen
erneut im echten Repository.

Die dokumentierte Grenze bleibt bestehen und wird nicht weggeschrieben: wer eine
Control-Plane-Datei und das Manifest im selben Commit ändert, besteht `validate-control-plane.py`.
Was der Guard leistet, ist der Wechsel von stiller Drift zu einem Manifest-Diff, den ein Review
nicht übersehen kann.
