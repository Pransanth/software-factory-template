# Bauauftrag: FACTORY-FINAL-REAUDIT-1

**Typ: `FACTORY_CHANGE`.** Dieser Auftrag verändert die Kontrollebene, die ihn kontrollieren
würde. Die geschützten Dateien können vom implementierenden Agenten nicht selbst geschrieben
werden; siehe „Bootstrap-Situation" unten für die vollständige Offenlegung.

**Kein neuer Audit.** Der Auftrag arbeitet ausschließlich die vier Restpunkte A–D aus
`factory/reviews/FACTORY-REAL-PROJECT-READINESS-1.round-2.md` ab. Neue Themen werden nicht
gesucht; neue Fähigkeiten entstehen keine.

## Primäre Sicherheitsgrenze

Für die beiden substanziellen Punkte ist es dieselbe Bewegung: **eine Prüfung hört auf zu raten,
wo sie nichts weiß.**

- **A** — Der einzige Finding-Parser löst Mehrdeutigkeit nicht mehr auf. Zwei Werte für dasselbe
  Feld heißen, dass das Dokument keinen Wert für dieses Feld hat; die Guards verweigern das
  Urteil, statt eines aus der zufällig letzten Zeile abzuleiten. Die eigentliche Grenze ist der
  **Abbruch vor dem ersten Lesen**: `validate-finding.py` prüft Mehrdeutigkeit, bevor Status,
  Severity oder `Review Artifact` überhaupt gelesen werden, und `validate-build-order.py` prüft
  sie, bevor der Status den Evidence-Lebenszyklus bestimmt. Ein Guard, der Mehrdeutigkeit meldet
  *und* trotzdem ein Urteil fällt, hätte die Lücke nur beschriftet.
- **B** — Der Dokumentations-Check hört auf, eine Positivliste wörtlicher Wendungen zu sein, und
  wird zu einer Regel: *erwähnen erzwingt ausschließen*. Zugleich hört `CLAUDE.md` auf, mehr zu
  versprechen, als diese Regel leisten kann. Beides gehört zusammen — eine geschärfte Prüfung mit
  weiterhin überzogener Beschreibung wäre derselbe Fehler in kleinerer Schrift.

C und D sind reine Dokumentationshygiene und verändern keine Sicherheitsgrenze. Sie stehen hier,
weil ein Record, der die Hälfte einer Änderung verschweigt, den unabhängigen Review gegen eine
Fiktion prüfen lässt — der Grund, aus dem der Bauauftrag überhaupt Pflicht ist.

## Verbindliche Reihenfolge

1. Negativtests schreiben und ROT beobachten, gegen den unveränderten Produktionsstand im echten
   Repository, mit den echten Guards (per Symlink geladen, nicht mit Kopien).
2. A umsetzen: `finding_format.py` meldet Duplikate, `validate-finding.py` und
   `validate-build-order.py` machen daraus einen harten Fehler mit Abbruch.
3. B umsetzen: Doku-Check umstellen, `CLAUDE.md` auf die tragbare Aussage reduzieren,
   `ONBOARDING.md` um den letzten Worktree-als-Routine-Eintrag bereinigen.
4. C und D im Bauauftrag von Paket 3 nachtragen bzw. entfernen — ausschließlich ergänzend,
   ohne eine einzige Zeile Evidence umzuschreiben.
5. Kanonischen Runner, Projekt-Test-Adapter, Preflight und die vollständige entdeckte Testsuite
   laufen lassen; ausdrücklich belegen, dass F-01 bis F-21 nicht wieder geöffnet werden.
6. Externe CI, unabhängiger Review des **gesamten** Control-Plane-Diffs, danach Closure.

## Acceptance Criteria

- Ein Finding mit zwei `Severity:`-Zeilen im kanonischen Block ist ein Guard-Fehler; der
  P0-Hard-Stop kann durch eine zweite Zeile nicht abgeschaltet werden.
- Ein Finding mit zwei `Status:`-Zeilen ist ein Guard-Fehler, und der Bauauftrags-Guard verweigert
  ebenfalls — der Evidence-Lebenszyklus darf nicht an einem geratenen Status hängen.
- Ein zweimal genanntes `Review Artifact` ist ein Guard-Fehler.
- Ein mehrdeutiges Finding wird **nicht weiter beurteilt**: genau ein Fehler, kein zusätzliches
  Urteil aus einem der beiden Werte.
- Die Erkennung ist gross-/kleinschreibungsunabhängig und gilt für jeden Feldnamen, nicht für eine
  kuratierte Liste.
- Eine eingerückte Wiederholung bleibt Fortsetzungszeile; eine Wiederholung in einem Fenced Block
  ist keine Wiederholung. Beide F-18-Regeln bleiben unverändert wirksam.
- Alle vier bestehenden Findings des Repositories bleiben ohne Änderung gültig.
- Der Doku-Check erkennt die zehn Formulierungen des Positivkorpus — darunter die frühere
  `CLAUDE.md`-Fassung und beide Umlautschreibungen — und meldet keinen Satz des Negativkorpus.
- `CLAUDE.md` beschreibt den Check als Formulierungsprüfung und nennt die geprüften Dokumente;
  die Aussage „schlägt fehl, wenn irgendein Dokument die Parallelitätsbehauptung wieder einführt"
  existiert nicht mehr.
- Die ZERO_ROUTINE_APPROVALS-Liste in `ONBOARDING.md` führt weder `Finding-Worktree` noch
  `create-finding-worktree.sh` als Routine auf.
- Der Bauauftrag von Paket 3 begründet die Entfernung von `Bash(git worktree *)` aus der
  `required`-Liste und enthält den Out-of-Scope-Absatz genau einmal.
- Die Invarianten aus F-01…F-21 sind nachweislich unverändert wirksam.

## Scope

Erlaubt und abschließend:

```
factory/guards/finding_format.py                (A: Duplikate melden statt aufloesen)
factory/guards/validate-finding.py              (A: harter Fehler mit Abbruch)
factory/guards/validate-build-order.py          (A: Status-Mehrdeutigkeit blockiert Evidence)
factory/guards/test_finding_format.py           (A: neue Klasse DuplicateFieldTests)
factory/guards/test_worktree_protection.py      (B: neuer Doku-Check + Korpora)
CLAUDE.md                                       (B: Guard-Behauptung auf das Tragbare reduziert)
factory/ONBOARDING.md                           (B: Worktree nicht mehr als Routine)
factory/build-orders/FACTORY-REAL-PROJECT-READINESS-1.md  (C: Nachtrag, D: Duplikat entfernt)
factory/findings/FACTORY-FINAL-REAUDIT-1.md     (neu, dieses Finding)
factory/build-orders/FACTORY-FINAL-REAUDIT-1.md (neu, dieser Bauauftrag)
factory/control-plane.sha256                    (Manifest, neu gestempelt)
```

Alles andere ist out of scope. `factory/reviews/**` wird nicht angefasst — Review-Runden sind
append-only und entstehen ausschließlich durch den `SubagentStop`-Hook. Die geschlossenen Findings
`FACTORY-TRUST-CORE-1`, `FACTORY-OPS-ROBUSTNESS-1` und `FACTORY-REAL-PROJECT-READINESS-1` werden
inhaltlich nicht verändert; sie dienen als Regressionskorpus. Am Bauauftrag von Paket 3 wird
ausschließlich ergänzt (C) und ein wörtliches Duplikat entfernt (D) — **kein** Evidence-Abschnitt,
keine Zahl, kein zitierter Lauf wird umgeschrieben. `.claude/settings*.json`,
`.github/workflows/**`, `.claude/hooks/**`, `.claude/agents/**`, `.claude/skills/**`,
`.claude/rules/**` und `factory/scripts/**` werden nicht angefasst: A–D verlangen dort nichts, und
eine Kontrollebenen-Änderung ohne Anlass ist genau die unzusammenhängende Mitnahme, die ein
`FACTORY_CHANGE`-Review aufdecken soll.

## Red Regression Evidence

Alle Läufe gegen den unveränderten Produktionsstand im echten Repository
(`/Users/clauskopp/Downloads/software-factory-template`, Branch
`factory-change/final-reaudit-1`, HEAD `f74a17a636213b2779ba62ea3e88f4cc5a81ef8a` =
`origin/main`), **nicht** gegen eine Kopie. Die neuen Testdateien liefen aus einem
Scratchpad-Verzeichnis, dessen `factory/guards/*.py` **Symlinks auf die echten Guards** sind —
geprüft wird der Produktionsstand, nicht eine Abschrift davon.

**A — der echte Parser löst Mehrdeutigkeit still auf:**

```
$ python3 probe_a.py
A1 doppelte Severity -> geparst: 'P1' (kanonisch zuerst: P0)
A1 P0-Hard-Stop-Fehler: []
A2 doppelter Status -> geparst: 'OPEN'
A3 doppeltes Review Artifact -> geparst: 'factory/reviews/DEMO.round-1.md'
```

Die zweite Zeile ist der eigentliche Befund: `vf._check_severity('IMPLEMENTING', 'P1')` liefert
eine leere Fehlerliste, obwohl das kanonisch zuerst genannte `Severity: P0` den Hard-Stop aus
F-09 auslösen müsste.

**A — dieselben Fälle als Regressionsklasse, rot gegen die unveränderten Guards:**

```
$ python3 -m unittest factory.guards.test_finding_format.DuplicateFieldTests
KeyError: 'duplicate_metadata_fields'
AssertionError: 0 != 1 : []
AssertionError: False is not true : Die Mehrdeutigkeit wird nicht benannt: ["Bauauftrag fehlt: ..."]
AssertionError: False is not true : Der Bauauftrags-Guard akzeptiert einen mehrdeutigen Status: []
Ran 10 tests in 0.008s
FAILED (failures=3, errors=10)
```

Die letzte Zeile vor dem Ergebnis ist die unangenehmste: `errors == []` heißt, dass der
Bauauftrags-Guard einen Bauauftrag zu einem Finding mit `Status: VERIFYING` **und**
`Status: OPEN` vollständig akzeptiert — als OPEN gelesen verlangt er weder rote noch grüne
Evidence.

**B — der alte Doku-Check erkennt die tatsächlich verwendeten Formulierungen nicht:**

```
$ python3 probe_oldregex.py
VERFEHLT Für echt gleichzeitige Arbeit sollte man einen eigenen Worktree pro Finding-Branch verwenden.
VERFEHLT Parallele Claude-Worktree-Sessions sind unterstützt.
ERKANNT  Parallele Claude-Worktree-Sessions werden unterstuetzt.
VERFEHLT Worktree-Parallelität ist verfügbar und erprobt.
VERFEHLT Worktree-Parallelitaet ist verfuegbar und erprobt.
VERFEHLT Parallele Findings sind möglich.
VERFEHLT Mehrere Findings können parallel bearbeitet werden.
VERFEHLT Parallelitaet ist sicher.
VERFEHLT Die Factory unterstützt parallel laufende Worktrees.
VERFEHLT Nebenläufige Finding-Sessions werden empfohlen.
alte Regex: 9/10 Formulierungen unerkannt
```

Der einzige Treffer ist die Wendung, aus der die Regex wörtlich gebaut war. Die erste Zeile ist
die **frühere** Fassung aus `CLAUDE.md` selbst — die Behauptung, gegen die der Check angeblich
schützte, hätte ihn passiert.

**B — die neuen Doku-Tests, rot gegen die unveränderte Dokumentation:**

```
$ python3 -m unittest factory.guards.test_worktree_protection.DocumentationTests
FAIL: test_a_finding_worktree_is_not_advertised_as_routine (entry='Finding-Worktree')
FAIL: test_a_finding_worktree_is_not_advertised_as_routine (entry='create-finding-worktree.sh')
FAIL: test_claude_md_does_not_promise_more_than_the_check_delivers
FAIL: test_no_document_claims_parallel_worktree_safety (document='CLAUDE.md')
Ran 10 tests in 0.006s
FAILED (failures=4)
```

Bemerkenswert an der letzten Zeile: der neue Check findet im **gesamten** aktuellen
Dokumentationsbestand genau eine Beanstandung — und es ist exakt der Satz, den der unabhängige
Reviewer als überzogene Guard-Behauptung benannt hatte. Alle übrigen Absätze, die Parallelität
diskutieren, um sie auszuschließen, bleiben unbeanstandet.

## Green Runtime Fix Evidence

Alle Läufe im echten Repository auf Branch `factory-change/final-reaudit-1`, Basis
`f74a17a636213b2779ba62ea3e88f4cc5a81ef8a`, nach dem einen externen Apply-Schritt.

**Byte-identische Verifikation der eingespielten Dateien** (die sechs geschützten aus dem
Apply-Schritt plus die zwei ungeschützten, die der Agent selbst geschrieben hat):

```
$ cmp -s <vorbereitet> <repo>  je Datei
  identisch: factory/guards/finding_format.py
  identisch: factory/guards/validate-finding.py
  identisch: factory/guards/validate-build-order.py
  identisch: factory/guards/test_finding_format.py
  identisch: factory/guards/test_worktree_protection.py
  identisch: CLAUDE.md
  Ergebnis: 6 identisch, 0 abweichend
  identisch: factory/ONBOARDING.md
  identisch: factory/build-orders/FACTORY-REAL-PROJECT-READINESS-1.md
```

**Control-Plane-Manifest.** Der Diff von `factory/control-plane.sha256` umfasst genau sechs
Zeilen, die den sechs geänderten Control-Plane-Dateien entsprechen — keine Datei wurde still
mitgestempelt, keine entfernt:

```
$ python3 factory/guards/validate-control-plane.py
Control-Plane unveraendert (42 Dateien gegen Manifest geprueft).
EXIT=0
```

**A — die zehn Duplikat-Regressionen, die vorher rot waren:**

```
$ python3 -m unittest factory.guards.test_finding_format.DuplicateFieldTests
..........
Ran 10 tests in 0.007s
OK
```

**B — die zehn Doku-Tests, die vorher vier Fehlschläge hatten:**

```
$ python3 -m unittest factory.guards.test_worktree_protection.DocumentationTests
..........
Ran 10 tests in 0.006s
OK
```

**Beide betroffenen Module vollständig:**

```
$ python3 -m unittest factory.guards.test_finding_format factory.guards.test_worktree_protection
Ran 47 tests in 0.527s
OK
```

**Vollständige entdeckte Testsuite — 372 statt vorher 356, exakt die 16 neuen Fälle:**

```
$ python3 factory/guards/run-factory-tests.py
Ran 372 tests in 55.462s
OK

ci_tests_run: 372
ci_test_failures: 0
ci_test_errors: 0
ci_tests_skipped: 0
SANDBOX_VERIFICATION: performed (1 Test(s) real ausgefuehrt)
FACTORY_TESTS: ALLE BESTANDEN
```

`ci_tests_skipped: 0` zusammen mit `SANDBOX_VERIFICATION: performed` belegt, dass die
sandbox-abhängigen Tests real gelaufen sind — ein übersprungener Sandbox-Test wäre nach F-19 kein
Nachweis.

**Kanonischer Runner:**

```
$ python3 factory/guards/run-factory-checks.py
[OK]     finding-validator: EXAMPLE-FINDING.md
[OK]     finding-validator: FACTORY-FINAL-REAUDIT-1.md
[OK]     finding-validator: FACTORY-OPS-ROBUSTNESS-1.md
[OK]     finding-validator: FACTORY-REAL-PROJECT-READINESS-1.md
[OK]     finding-validator: FACTORY-TRUST-CORE-1.md
[OK]     build-order-guard: FACTORY-FINAL-REAUDIT-1.md
[OK]     build-order-guard: FACTORY-OPS-ROBUSTNESS-1.md
[OK]     build-order-guard: FACTORY-REAL-PROJECT-READINESS-1.md
[OK]     build-order-guard: FACTORY-TRUST-CORE-1.md
[OK]     review-guard: FACTORY-OPS-ROBUSTNESS-1.round-1.md
[OK]     review-guard: FACTORY-REAL-PROJECT-READINESS-1.round-1.md
[OK]     review-guard: FACTORY-REAL-PROJECT-READINESS-1.round-2.md
[OK]     review-guard: FACTORY-TRUST-CORE-1.round-1.md
[OK]     control-plane-guard: Kontrollebene unveraendert
[OK]     project-tests-guard: TEMPLATE_WITHOUT_PRODUCT (Vorlage ohne Produktcode -- erwartet)
Factory-Checks: ALLE BESTANDEN
EXIT=0
```

Die drei bereits abgeschlossenen Findings bestehen `finding-validator` weiterhin, obwohl dieser
Commit den Scope-Hash bewegt — das ist der Historien-Fallback für `CLOSED` aus dem
Operational-Robustness-Paket in Funktion, live nachgewiesen.

**Projekt-Test-Adapter:**

```
$ python3 factory/guards/run-project-tests.py
PROJECT_TESTS: TEMPLATE_WITHOUT_PRODUCT
EXIT=0
```

**Regression gegen F-01…F-21, in zwei Gruppen:**

```
$ python3 -m unittest factory.guards.test_trust_core factory.guards.test_ops_robustness \
      factory.guards.test_closure_history factory.guards.test_build_order
Ran 120 tests in 19.327s
OK

$ python3 -m unittest factory.guards.test_validate_finding factory.guards.test_validate_review \
      factory.guards.test_control_plane factory.guards.test_gh_evidence \
      factory.guards.test_project_tests factory.guards.test_factory_preflight \
      factory.guards.test_create_finding_worktree factory.guards.test_run_factory_checks
Ran 173 tests in 29.742s
OK
```

**Hook-/Provenienz-Tests und Sandbox-Verifikation, direkt ausgeführt:**

```
$ python3 .claude/hooks/test_stop_validate_findings.py      -> Ran 7 tests, OK
$ python3 .claude/hooks/test_subagentstop_write_review.py   -> Ran 24 tests, OK
$ python3 .claude/hooks/test_sandbox_protects_reviews.py    -> Ran 1 test, OK
```

**Preflight.** Die Factory- und GitHub-Ebene ist grün, einschließlich Control-Plane-Manifest,
kanonischem Runner, 372 CI-Tests, durchgeführter Sandbox-Verifikation, Branch-Schutz, Required
Status Check und Push-/PR-Rechten. Zwei Punkte bleiben `[FEHLT]`, beide **maschinenlokal** und
beide unabhängig von A–D:

```
[FEHLT]   Unbekannte Shell-Freigaben in .claude/settings.local.json: ... (Altbestand aus
          frueheren Sitzungen; die Datei ist gitignored und nicht Teil der Vorlage)
[FEHLT]   Kein GitHub-Credential ... im git-credential-Helper (nicht-interaktiv geprueft)
FACTORY_PREFLIGHT: BLOCKED (2 offene Voraussetzung(en))
```

Beide werden gemeldet und **nicht umgangen**. Der erste ist genau die F-14/E-Positivprüfung in
Funktion; seine Bereinigung ist ausdrücklich ein menschlicher Schritt, und die Factory erteilt
sich keine Rechte selbst — `settings.local.json` wurde in diesem Paket nicht angefasst.
`FACTORY-TRUST-CORE-1` dokumentiert denselben Zustand als Präzedenzfall. Der zweite ist eine
Grenze der *nicht-interaktiven* Abfrageform, nicht ein fehlendes Credential: im selben
Preflight-Lauf haben `gh-api.sh`, `gh-query.sh`, die Contents- und Pull-Request-Rechteprüfung und
die Actions-Lesbarkeit alle `[OK]` gemeldet.

## Bootstrap-Situation

Dieselbe Offenlegung wie bei den drei vorangegangenen Paketen, weil sie weiterhin zutrifft: die
geschützten Control-Plane-Pfade (`factory/guards/**`, `CLAUDE.md`, `factory/control-plane.sha256`)
sind für den implementierenden Agenten lokal gesperrt (`permissions.deny` +
`sandbox.filesystem.denyWrite`). Er kann die Reparatur deshalb nicht selbst einspielen. Der
getestete Stand wird in einem Scratchpad vorbereitet und über **einen** externen, menschlich
ausgeführten Apply-Schritt eingespielt; danach wird jede eingespielte Datei byte-identisch gegen
die Vorbereitung verifiziert, und sämtliche Tests laufen erneut im echten Repository.

Die dokumentierte Grenze bleibt bestehen und wird nicht weggeschrieben: wer eine
Control-Plane-Datei und das Manifest im selben Commit ändert, besteht `validate-control-plane.py`.
Was der Guard leistet, ist der Wechsel von stiller Drift zu einem Manifest-Diff, den ein Review
nicht übersehen kann.
