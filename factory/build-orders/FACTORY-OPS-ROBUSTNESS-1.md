# Bauauftrag: FACTORY-OPS-ROBUSTNESS-1

**Typ: `FACTORY_CHANGE`.** Dieser Auftrag verändert erneut die Kontrollebene, die ihn
kontrollieren würde. Die geschützten Dateien konnten vom implementierenden Agenten nicht selbst
geschrieben werden; siehe „Bootstrap-Situation" unten für die vollständige Offenlegung.

## Primäre Sicherheitsgrenze

Die eigentliche Reparatur ist **kein weiterer Guard**, sondern eine Umkehr der Beweislast an
jeder Stelle, an der die Factory eine Aussage über ihre eigene Betriebsfähigkeit macht: eine
Zusicherung gilt nur noch dann als erfüllt, wenn sie **positiv beobachtet** wurde — nicht, wenn
kein bekannter Fehler auftrat.

Konkret an vier Stellen:

- Die PR-Berechtigung gilt nur als vorhanden, wenn GitHub die eigene Validierungsantwort liefert.
  Jede andere Antwort — auch eine unbekannte — blockt (F-12).
- Der Branch-Schutz gilt nur als ausreichend, wenn *gelesen* wurde, dass ein Pull Request
  erforderlich ist und der Required Status Check konfiguriert ist. Regeln zu zählen sagt nichts
  (F-13).
- Die Factory gilt nur als installiert, wenn Control-Plane-Guard, kanonischer Runner und die
  entdeckte Testsuite tatsächlich laufen und bestehen. Dateiexistenz sagt nichts (F-14).
- Eine Ebene, die nicht geprüft wurde, gilt nicht als bestanden: `--local-only` erreicht `PASS`
  nicht mehr, sondern `PARTIAL` mit eigenem Exit-Code (F-11).

Die zweite Grenze derselben Art betrifft die Zeit statt den Umfang: **veraltete Evidence ist
ungültige Evidence.** Der Resume-Pfad vergleicht jeden gespeicherten Wert gegen den heutigen
Zustand und meldet `stale`, statt ein altes „grün" auf neuen Code zu übertragen (F-16).

Und die dritte betrifft, was überhaupt geprüft wird: Tests werden **entdeckt**, nicht aufgezählt,
und ein übersprungener Sandbox-Test wird getrennt ausgewiesen statt in die Bestanden-Zahl
eingerechnet (F-19).

## Verbindliche Reihenfolge

1. Negativtests schreiben und ROT beobachten (mit zitierter Ausgabe).
2. Bindungen und Beobachtungen umsetzen, bis dieselben Tests GRÜN sind.
3. Zentrale Guards ergänzen (`validate-build-order.py`, `run-factory-tests.py`,
   `finding_state.py`) und in den kanonischen Runner bzw. die CI einhängen.
4. Kanonischen Runner, Projekttests und die vollständige entdeckte Testsuite laufen lassen.
5. Externe CI, unabhängiger Review des **gesamten** Control-Plane-Diffs, danach Closure.

## Acceptance Criteria

- Ein Finding erreicht `IMPLEMENTING` und alles Spätere nur mit einem Bauauftrag, der
  `validate-build-order.py` vollständig besteht; der kanonische Runner prüft jeden Bauauftrag.
- `factory-preflight.sh --local-only` meldet niemals `PASS`, sondern `PARTIAL` mit Exit 3.
- Die PR-Probe meldet `permitted` ausschließlich bei GitHubs Validierungsfehler; 401, 403, 404,
  Rate-Limit, leerer Body, Nicht-JSON und unbekannte Meldungen blocken.
- Ein Ruleset, das nur Force-Push verbietet, führt nicht zu einem vollständigen Preflight-PASS;
  erforderliche Approvals werden erkannt und als Governance-Punkt gemeldet, nicht umgangen;
  klassische Branch Protection wird zusätzlich gelesen und „nicht geschützt" nicht mit „nicht
  lesbar" verwechselt.
- Ein Repository, dessen Pflichtdateien Platzhalter sind, erreicht weder `PASS` noch `PARTIAL`.
- Unbekannte Shell-Freigaben in `settings.local.json` sind ein Blocker.
- `finding_state.py assess` unterscheidet deterministisch zwischen `current` und `stale` für Push,
  CI und Review; ein bereits existierender Worktree führt zu einem definierten Zustand und wird
  nie gelöscht; `gh-query.sh pr-for-branch` unterscheidet „kein PR" (Exit 3) von „Abfrage
  fehlgeschlagen" (Exit 4).
- Eine neue Testdatei unter `factory/guards/test_*.py` oder `.claude/hooks/test_*.py` läuft in CI,
  ohne irgendwo registriert zu werden; „nichts gefunden" ist ein harter Fehler; ein übersprungener
  Sandbox-Test wird als `SANDBOX_VERIFICATION: not_performed` ausgewiesen.
- Ein fehlendes GitHub-Credential führt sofort zu einem Blocker mit Exit ≠ 0, ohne Prompt, ohne
  Hänger, ohne Token in der Ausgabe.
- Ein bereits abgeschlossenes, gemergtes Finding bleibt gültig, wenn danach anderer Code geändert
  wird — ohne dass die F-03-Bindung gelockert wird.

## Scope

Erlaubt und abschließend:

```
factory/guards/validate-build-order.py     (neu)
factory/guards/finding_state.py            (neu)
factory/guards/run-factory-tests.py        (neu)
factory/guards/test_build_order.py         (neu)
factory/guards/test_closure_history.py     (neu)
factory/guards/test_ops_robustness.py      (neu)
factory/guards/validate-finding.py
factory/guards/run-factory-checks.py
factory/guards/scope_hash.py
factory/guards/gh_evidence.py
factory/guards/test_factory_preflight.py
factory/guards/test_run_factory_checks.py
factory/guards/test_trust_core.py
factory/guards/test_validate_finding.py
factory/scripts/factory-preflight.sh
factory/scripts/gh-api.sh
factory/scripts/gh-query.sh
factory/scripts/create-finding-worktree.sh
factory/control-plane.sha256
factory/findings/FACTORY-OPS-ROBUSTNESS-1.md
factory/build-orders/FACTORY-OPS-ROBUSTNESS-1.md
factory/build-orders/FACTORY-TRUST-CORE-1.md   (nur markierte Korrekturen, Reviewer-Hinweise B/C)
factory/build-orders/README.md
factory/README.md
factory/ONBOARDING.md
.claude/hooks/test_stop_validate_findings.py
.claude/hooks/test_subagentstop_write_review.py
.claude/rules/factory-workflow.md
.claude/skills/verify-finding/SKILL.md
.claude/settings.json
.github/workflows/factory-ci.yml
.gitignore
CLAUDE.md
```

Weil dies ein `FACTORY_CHANGE` ist, liegen die geschützten Factory-Pfade hier ausnahmsweise **im**
Scope. Genau deshalb muss der unabhängige Review den vollständigen Control-Plane-Diff prüfen und
nicht nur den Anlass.

Ausdrücklich **nicht** im Scope (Paket 3): **F-15, F-18, F-21** — keine echte
Parallelitätsarchitektur, keine Multi-Language-Projekt-Testintegration, keine
Finding-Format-Generalüberholung. `factory/reviews/**` wird nicht angefasst; die
Review-Historie bleibt append-only und unverändert.

## Red Regression Evidence

Alle Läufe gegen die **unveränderten** Guards des gemergten Trust-Core-Stands (`371a0a4`), in
einem separaten Worktree dieses Commits, in den ausschließlich die neuen Testdateien kopiert
wurden.

**Die drei neuen Testmodule zusammen — 66 von 83 rot:**

```
$ python3 -m unittest factory.guards.test_closure_history \
    factory.guards.test_ops_robustness factory.guards.test_build_order
Ran 83 tests in 7.852s
FAILED (failures=63, errors=3)
```

**F-10 — Bauauftragspflicht (`test_build_order`, 21 von 27 rot).** Die zentralen Fehlschläge:

```
FAIL: test_implementing_without_a_build_order_is_rejected      (Finding ohne Bauauftrag akzeptiert)
FAIL: test_verifying_without_a_build_order_is_rejected
FAIL: test_closed_without_a_build_order_is_rejected
FAIL: test_runner_rejects_a_finding_without_a_build_order      (auch der kanonische Runner)
FAIL: test_placeholder_section_is_rejected                     (TBD-Abschnitte akzeptiert)
FAIL: test_orphan_build_order_without_a_finding_is_rejected
FAIL: test_build_order_titled_for_another_finding_is_rejected
FAIL: test_red_evidence_without_quoted_output_is_rejected_at_implementing
```

Originalausgabe des zentralen Falls:

```
AssertionError: 2 != 1 : guard accepted what it must reject.
stderr:
python3: can't open file '.../factory/guards/validate-build-order.py': [Errno 2] No such file or directory
```

**F-12/F-13/F-16/F-19/F-20 (`test_ops_robustness`, 42 von 45 rot).** Nach Invariante gruppiert:

```
PrPermissionProbeTests   test_validation_error_proves_the_permission            (F-12)
                         test_401_bad_credentials_is_blocked_not_permitted      (F-12)
                         test_network_failure_is_reported_as_api_error...       (F-12)
                         test_a_created_pull_request_is_a_blocker               (F-12)
RulesetGuaranteeTests    test_force_push_only_ruleset_guarantees_nothing...     (F-13)
                         test_full_ruleset_is_recognised                        (F-13)
                         test_required_approvals_are_reported                   (F-13)
                         test_an_api_error_is_not_an_empty_ruleset              (F-13)
PrForBranchTests         alle 6                                                 (F-16)
WorktreeResumeTests      alle 3                                                 (F-16)
TestDiscoveryTests       alle 7                                                 (F-19)
NonInteractiveCredential test_a_missing_credential_blocks_immediately...        (F-20)
                         test_the_credential_value_is_never_printed             (F-20)
```

Bemerkenswert: **drei** Tests aus `PrPermissionProbeTests` bestanden schon vorher —
`test_404_not_found_is_blocked_not_permitted`, `test_403_forbidden_is_blocked` und
`test_empty_body_is_blocked` — weil der alte Modus schlicht nicht existierte und der Aufruf mit
Exit ≠ 0 endete. Sie sind trotzdem behalten: sie sichern jetzt ab, dass die *richtige* Ablehnung
aus dem *richtigen* Grund kommt.

**Blockierender Defekt: Closure-Historie (`test_closure_history`, 6 von 11 rot).**

```
FAIL: test_a_closed_finding_stays_valid_after_later_unrelated_work
FAIL: test_the_canonical_runner_survives_a_change_after_a_closure
FAIL: test_an_uncommitted_later_change_also_leaves_a_closure_valid
FAIL: test_commit_hash_equals_working_tree_hash_for_a_clean_tree
FAIL: test_a_finding_only_commit_does_not_move_the_hash
FAIL: test_a_product_change_does_move_the_commit_hash
```

Zuerst aber **live am echten Repository** beobachtet, nicht in einer Fixture: nach der ersten
Guard-Änderung dieses Pakets meldete der Validator für das bereits gemergte, geschlossene
Trust-Core-Finding:

```
$ python3 factory/guards/validate-finding.py factory/findings/FACTORY-TRUST-CORE-1.md
UNGÜLTIG: factory/findings/FACTORY-TRUST-CORE-1.md
  - Scope-Hash-Abweichung: Review-Artefakt
    'factory/reviews/FACTORY-TRUST-CORE-1.round-1.md' wurde gegen sha256:4a9a17a4…c47043
    erstellt, der aktuelle Stand ist sha256:f09994eb…8249d. Der geprüfte Codezustand ist nicht
    mehr der aktuelle -- ein neuer Review-Durchgang ist noetig.
EXIT=1
```

**Die fünf Tests aus `ClosureBindingIsNotRelaxedTests` bestanden in beiden Läufen** — vorher wie
nachher. Das ist der Über-Reparatur-Schutz: `READY_FOR_CLOSURE` bleibt an den aktuellen Stand
gebunden, ein Scope-Hash, den es nie gab, wird abgelehnt, ein `FAIL` für denselben Zustand
blockiert weiterhin, und ein fremdes Review schließt weiterhin nichts.

**F-11/F-14 — der Preflight-Defekt war in den alten Tests festgeschrieben.** Im unveränderten
Stand *behauptete* die Testsuite selbst das falsche Grün. `make_required_files()` schrieb dort in
jede Pflichtdatei den Text `placeholder`, und der Test dazu lautete
`self.assertIn("FACTORY_PREFLIGHT: PASS", result.stdout)`:

```
$ python3 -m unittest factory.guards.test_factory_preflight -v      (unveraenderter Stand)
test_fully_prepared_repository_passes_local_preflight ... ok
test_local_only_mode_skips_network_checks ... ok
Ran 20 tests in 3.724s
OK
```

Ein Repository aus lauter Platzhaltern, ohne jede GitHub-Prüfung, galt als „vollständig
vorbereitet". Dieser Test wurde **umgedreht, nicht gelöscht** (siehe
`test_fully_prepared_repository_reports_partial_in_local_only_mode`), und um
`test_a_repository_of_placeholders_never_passes` sowie
`test_local_only_can_never_reach_pass` ergänzt.

## Green Runtime Fix Evidence

Alle folgenden Läufe stammen aus dem Zustand, der in diesem Branch reviewt und gemergt wird.

**Vollständige, automatisch entdeckte Testsuite — 14 Module, 299 Tests:**

```
$ python3 factory/guards/run-factory-tests.py --quiet
Entdeckte Testmodule (14):
  - factory/guards/test_build_order.py
  - factory/guards/test_closure_history.py
  - factory/guards/test_control_plane.py
  - factory/guards/test_create_finding_worktree.py
  - factory/guards/test_factory_preflight.py
  - factory/guards/test_gh_evidence.py
  - factory/guards/test_ops_robustness.py
  - factory/guards/test_run_factory_checks.py
  - factory/guards/test_trust_core.py
  - factory/guards/test_validate_finding.py
  - factory/guards/test_validate_review.py
  - .claude/hooks/test_sandbox_protects_reviews.py
  - .claude/hooks/test_stop_validate_findings.py
  - .claude/hooks/test_subagentstop_write_review.py

ci_tests_run: 299
ci_test_failures: 0
ci_test_errors: 0
ci_tests_skipped: 1
SANDBOX_VERIFICATION: not_performed (…this process is not running under an active Claude Code
OS sandbox…)
FACTORY_TESTS: ALLE BESTANDEN
```

Der eine übersprungene Test ist die Sandbox-Verifikation. Sie wird **getrennt ausgewiesen** und
nicht in die Bestanden-Aussage eingerechnet — genau die Vermischung, die F-19 beanstandet hat.
Dieser Lauf fand in einer Arbeitskopie außerhalb der Repo-Sandbox statt; der Lauf im echten
Repository ist unten getrennt aufgeführt.

**Die neuen Module einzeln, gegen die reparierten Guards:**

```
$ python3 -m unittest factory.guards.test_build_order
Ran 27 tests -- OK                     (vorher 21 Fehlschlaege)

$ python3 -m unittest factory.guards.test_closure_history
Ran 11 tests -- OK                     (vorher 6 Fehlschlaege)

$ python3 -m unittest factory.guards.test_ops_robustness
Ran 45 tests in 2.472s -- OK           (vorher 42 Fehlschlaege)

$ python3 -m unittest factory.guards.test_factory_preflight
Ran 26 tests in 12.871s -- OK          (20 vorher, 6 neue)
```

**Der Closure-History-Fix reproduziert den Arbeitsbaum-Hash exakt** — nachgewiesen gegen den
bekannten, im echten Review-Artefakt gestempelten Wert:

```
$ python3 factory/guards/scope_hash.py --commit HEAD
scope_hash: sha256:4a9a17a48ca0ca32de59d88e1950ca2e660329b309a0cb3177be8a2293c47043
scope_files: 36
```

Das ist bitgleich der Wert, den `Reviewed Scope Hash` in
`factory/reviews/FACTORY-TRUST-CORE-1.round-1.md` trägt. Der Commit-basierte Pfad ist damit keine
zweite, laxere Berechnung, sondern dieselbe.

**Und der zuvor rote Live-Fall ist grün, ohne dass die Bindung gelockert wurde:**

```
$ python3 factory/guards/validate-finding.py factory/findings/FACTORY-TRUST-CORE-1.md
GÜLTIG: factory/findings/FACTORY-TRUST-CORE-1.md (Status: CLOSED, Severity: P1)
```

**Kanonischer Runner, Projekttests, Control-Plane-Guard und der Preflight im echten Repository:**
siehe `Verification Evidence` im Finding.

## Bootstrap-Situation (ausdrücklich dokumentiert)

Wie beim Trust Core gilt auch hier, und es wird nicht weggeredet:

1. **Die geschützten Control-Plane-Dateien konnte der implementierende Agent nicht selbst
   schreiben.** Das ist der Schutz aus F-05 in bestimmungsgemäßer Funktion. Sie wurden als
   fertiger Stand im Scratchpad vorbereitet, von einem Menschen außerhalb der Sandbox angewandt
   und danach byte-identisch verifiziert. Die genaue Zahl und Liste der extern eingespielten
   Dateien steht im Finding unter `Verification Evidence` — die Lehre aus dem Trust-Core-Review,
   dessen Zahlenangabe falsch war.
2. **Das Manifest wird im selben Commit aktualisiert wie die Dateien, die es beschreibt.** Für
   diesen Commit beweist es deshalb nichts. Sein Wert liegt beim *nächsten* Finding. Neu ist
   immerhin, dass `factory/control-plane.sha256` jetzt auch lokal gesperrt ist, das Neustempeln
   also ebenfalls ein bewusster externer Schritt ist und nicht mehr nebenbei passieren kann.
3. **Die Entwicklung fand in einer Arbeitskopie statt**, nicht im echten Repository, weil die
   Sandbox das Schreiben in die Kontrollebene verhindert. Alle oben zitierten Läufe stammen aus
   dieser Arbeitskopie; die Läufe im echten Repository nach dem externen Anwenden sind im Finding
   getrennt dokumentiert. Wo beide vorliegen, zählt der Lauf im echten Repository.
