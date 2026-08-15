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

## Green Runtime Fix Evidence

Wird nach Abschluss der Implementierung mit den tatsächlichen Ausgaben gefüllt (kanonischer
Runner, Projekttests, vollständige Guard- und Hook-Testsuite, CI-Lauf).

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
3. **Vier Dateien der Kontrollebene konnten vom implementierenden Agenten nicht geschrieben
   werden** (`.claude/hooks/`, `.claude/agents/`, `.claude/skills/`, `.claude/settings.json`,
   `factory/reviews/README.md`), weil genau dieser Schutz greift. Sie wurden als Patches
   ausgeliefert und von einem Menschen angewandt. Das ist keine Umgehung des Schutzes, sondern
   sein bestimmungsgemäßes Verhalten — und der Grund, warum ein `FACTORY_CHANGE` eine menschliche
   Entscheidung verlangt.
