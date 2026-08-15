# FACTORY-OPS-ROBUSTNESS-1

Status: VERIFYING
Severity: P1

## Befund

Paket 2 des Factory-v1-Audits (*Operational Robustness*). Nachdem der Trust Core
(`FACTORY-TRUST-CORE-1`, F-01…F-09 und F-17) die *Bindung* zwischen Behauptung und geprüftem
Gegenstand hergestellt hat, betrifft dieses Paket die Frage, ob die Factory im echten Betrieb
überhaupt verlässlich arbeitet: ob sie ihre eigenen Voraussetzungen ehrlich meldet, ob sie einen
Abbruch übersteht, ob sie neue Tests wirklich ausführt und ob sie unbeaufsichtigt laufen kann,
ohne auf eine Eingabe zu warten, die niemand macht.

Acht Audit-Befunde gehören dazu:

- **F-10** — Ein Bauauftrag war reine Prosa. Ein Finding konnte `IMPLEMENTING`, `VERIFYING`,
  `READY_FOR_CLOSURE` und `CLOSED` ohne jeden Bauauftrag erreichen. Der unabhängige Reviewer ist
  ausdrücklich angewiesen, kein eigenes Sicherheitsmodell zu erfinden, sondern den Bauauftrag
  gegen den Code zu halten — ohne Bauauftrag hält er nichts.
- **F-11** — `factory-preflight.sh --local-only` meldete `FACTORY_PREFLIGHT: PASS` und
  „unbeaufsichtigte Läufe sind bereit", obwohl sämtliche GitHub-/Remote-Gates übersprungen
  wurden. Das ist ein falsches Grün über eine Ebene, die gar nicht geprüft wurde.
- **F-12** — Die PR-Berechtigungsprobe klassifizierte nach dem Ausschlussprinzip: alles, was nicht
  erkennbar `403` war, galt als `PERMITTED`. Ein `401` (falsches Token), ein `404` (kein Zugriff)
  und jede unerwartete Antwort wurden damit als „Berechtigung vorhanden" gemeldet.
- **F-13** — Der Branch-Schutz wurde nur *gezählt* (`COUNT n`). Ein Ruleset, das ausschließlich
  Force-Push verbietet, erfüllte die Prüfung genauso wie ein vollständiger Schutz. Ob überhaupt
  ein Pull Request verlangt wird, ob der Required Status Check konfiguriert ist und ob
  erforderliche Approvals einen autonomen Merge verhindern, wurde nie festgestellt.
- **F-14** — Die Prüfung der Factory-Funktionsfähigkeit war eine reine Dateiexistenzprüfung. Ein
  Repository, dessen Pflichtdateien nur das Wort `placeholder` enthalten, bestand sie.
- **F-16** — Nach einem Session- oder Maschinenabbruch konnte ein neuer Agent nicht
  deterministisch feststellen, was bereits geschehen war: existiert der Branch, wurde gepusht,
  gibt es schon einen PR, ist CI grün, liegt ein Review vor, wurde bereits gemergt.
  `create-finding-worktree.sh create` scheiterte roh, wenn der Worktree schon existierte.
- **F-19** — Die CI zählte die auszuführenden Testmodule von Hand auf. Eine neue Testdatei lief
  nur mit, wenn jemand zusätzlich die Workflow-Datei anpasste — und die ist Control Plane, also
  ein `FACTORY_CHANGE`. Vergessen war still und ließ CI grün bleiben, gerade *weil* der neue Test
  nie lief. Zusätzlich verschwamm ein übersprungener Sandbox-Test mit einem bestandenen.
- **F-20** — `git credential fill` ist per Default interaktiv. Bei fehlendem oder gesperrtem
  Credential fiel es auf `/dev/tty` zurück — nicht auf stdin, ein Pipe half also nicht. Ein
  unbeaufsichtigter Lauf **hing** dann ohne Ausgabe und ohne Exit-Code.

Dazu die drei dokumentierten Hinweise aus Trust-Core-Review-Runde 1: die überzogene
Schutzbehauptung in `CLAUDE.md`, die falsche Zahl in der Bootstrap-Offenlegung und die
unvollständige Scope-Beschreibung des Bauauftrags.

**Während der Umsetzung reproduziert: ein blockierender Defekt, der in keiner F-Nummer stand.**
Der Closure-Gate verglich den `Reviewed Scope Hash` gegen den *aktuellen* Repository-Hash — auch
für längst `CLOSED`-Findings. Damit wurde jede abgeschlossene Closure ungültig, sobald irgendetwas
am Code geändert wurde. Konkret: `FACTORY-TRUST-CORE-1` ist gemergt und `CLOSED`; die erste
Änderung in diesem Paket ließ `validate-finding.py` und damit den kanonischen Runner und die CI
rot werden. **Die Factory war nach ihrer ersten Closure faktisch schreibgeschützt** — dieses Paket
hätte nie grün werden können.

**Severity-Begründung:** `P1`, nicht `P0`. Es gibt keinen Hinweis auf laufende Ausnutzung und
keinen unmittelbaren Produktionsschaden; die Vorlage enthält keinen Produktcode. Zugleich ist es
mehr als ein Robustheitsproblem: der Preflight behauptete Betriebsbereitschaft, die nicht geprüft
war (F-11/F-12/F-13/F-14), und der Closure-Defekt machte die Factory nach einem Durchlauf
unbenutzbar.

**Dies ist ein `FACTORY_CHANGE`.** Der Auftrag verändert erneut die Kontrollebene, die ihn
kontrolliert. Die geschützten Dateien konnten vom implementierenden Agenten nicht selbst
geschrieben werden; siehe `Verification Evidence` und den Bauauftrag für die vollständige
Offenlegung.

## Analyse

Root Cause: Der Trust Core hat die Bindung zwischen Behauptung und Gegenstand hergestellt, aber die Aussagen ueber die *Betriebsvoraussetzungen* blieben unverbunden. Der Preflight klassifizierte nach dem Ausschlussprinzip statt positiv (F-12: alles, was nicht erkennbar 403 war, galt als erlaubt), zaehlte Regeln statt sie zu lesen (F-13), prueste Dateiexistenz statt Funktionsfaehigkeit (F-14) und meldete PASS ueber eine Ebene, die er gar nicht betreten hatte (F-11). Dieselbe Sorte Luecke an anderen Stellen: der Bauauftrag war eine Konvention ohne Guard (F-10), die auszufuehrenden Tests waren eine handgepflegte Liste statt einer Entdeckung (F-19), der Zustand eines unterbrochenen Laufs war nirgends festgehalten und musste geraten werden (F-16), und die Credential-Abfrage konnte auf eine Antwort warten, die unbeaufsichtigt nie kommt (F-20). Der waehrend der Umsetzung gefundene Closure-Defekt hat eine eigene, engere Ursache: der Scope-Hash-Vergleich kannte nur den Arbeitsbaum, nicht die Historie, und beantwortete damit fuer ein bereits geschlossenes Finding dauerhaft die falsche Frage.
Affected Components: factory/scripts/factory-preflight.sh, factory/scripts/gh-api.sh, factory/scripts/gh-query.sh, factory/scripts/create-finding-worktree.sh, factory/guards/validate-build-order.py (neu), factory/guards/finding_state.py (neu), factory/guards/run-factory-tests.py (neu), factory/guards/validate-finding.py, factory/guards/run-factory-checks.py, factory/guards/scope_hash.py, factory/guards/gh_evidence.py, .github/workflows/factory-ci.yml, .claude/settings.json, .claude/rules/factory-workflow.md, .claude/skills/verify-finding/SKILL.md, CLAUDE.md sowie die zugehoerigen Testmodule.
Relevant Architecture: Die Factory hat vier Pruefschichten (Validatoren, kanonischer Runner, lokale Hooks, externe GitHub-CI mit Required Status Check) und zwei Eintrittspunkte in den Betrieb: den einmaligen Preflight und den wiederholten Finding-Lauf. Der Preflight ist die einzige Stelle, an der ueber die Betriebsbereitschaft geurteilt wird -- ein falsches Gruen dort wird von keiner spaeteren Schicht korrigiert, weil alle spaeteren Schichten voraussetzen, dass die Voraussetzungen stimmen. Der kanonische Runner ist die einzige Stelle, an der CI und lokaler Lauf dieselbe Logik ausfuehren; alles, was nicht ueber ihn laeuft (die handgepflegte Testliste im Workflow), ist per Konstruktion driftfaehig.
Recommended Repair: Jede Aussage ueber Betriebsbereitschaft an eine positive, deterministisch pruefbare Beobachtung koppeln statt an das Fehlen einer bekannten Fehlermeldung. Konkret: ein Bauauftrags-Guard mit gegenseitiger Bindung an das Finding (F-10); ein dritter Preflight-Ausgang PARTIAL, der PASS ueber ungepruefte Ebenen unmoeglich macht (F-11); eine PR-Probe, die nur eine echte Validierungsantwort als PERMITTED wertet und jede andere Antwort blockt (F-12); semantische Auswertung von Rulesets UND klassischer Branch Protection inklusive Required Approvals (F-13); ein Funktionsnachweis durch tatsaechliches Ausfuehren von Control-Plane-Guard, kanonischem Runner und Testentdeckung statt Dateiexistenz (F-14); eine minimale, maschinenlokale Zustandsbasis pro Finding plus idempotente Helfer und pr-for-branch (F-16); Testentdeckung statt Aufzaehlung, mit getrennter Meldung von CI-Test und echter Sandbox-Verifikation (F-19); eine explizit nicht-interaktive Credential-Abfrage (F-20). Der Closure-Defekt wird geschlossen, indem der Scope-Hash zusaetzlich aus einem Commit-Baum berechnet werden kann und ein CLOSED-Finding gegen den historischen Commit geprueft wird, in dem es tatsaechlich geschlossen wurde.
Regression Test Plan: Negativtests zuerst, gegen die unveraenderten Guards rot beobachtet. factory/guards/test_build_order.py deckt Bauauftragspflicht, Struktur, Platzhalter, Identitaet und Evidence-Lebenszyklus ab; factory/guards/test_closure_history.py deckt den blockierenden Closure-Defekt ab und sichert ausdruecklich, dass die F-03-Bindung nicht gelockert wurde; factory/guards/test_ops_robustness.py deckt PR-Probe, Branch-Schutz, Resume-Zustand, Worktree-Idempotenz, Testentdeckung und die nicht-interaktive Credential-Abfrage ab; test_factory_preflight.py wird um PARTIAL, Platzhalter-Erkennung, Funktionsnachweis und Allowlist-Semantik erweitert. Bestehende Tests, die die alte, schwaechere Semantik erwarteten, werden umgedreht statt geloescht.
Central Guard Plan: Drei neue zentrale Guards statt punktueller Pruefungen. validate-build-order.py erzwingt die Bauauftragsbindung und laeuft im kanonischen Runner, also in jedem CI-Lauf. run-factory-tests.py ersetzt die handgepflegte Testliste durch Entdeckung und macht 'nichts gefunden' zu einem harten Fehler. finding_state.py ist die einzige Stelle, an der Resume-Zustand interpretiert wird, und markiert Evidence als stale, sobald der Branch-Head sich bewegt hat. Alle drei sind ohne Netz testbar.
Expected Blast Radius: Ausschliesslich die Factory-Infrastruktur; kein Produktcode ist betroffen, weil die Vorlage keinen enthaelt. Fuer bestehende Kopien ist die Aenderung nicht rueckwaertskompatibel: Findings ab IMPLEMENTING ohne gueltigen Bauauftrag werden abgelehnt, 'factory-preflight.sh --local-only' liefert nicht mehr Exit 0, und der Preflight verlangt jetzt einen semantisch ausreichenden Branch-Schutz statt einer beliebigen Regelanzahl.
Risk Assessment: Das Hauptrisiko der Aenderung ist falsches Rot, nicht falsches Gruen: der Preflight wird deutlich strenger und wird in bestehenden Kopien Punkte melden, die vorher unbemerkt blieben. Das ist der Zweck. Ein zweites, ernster zu nehmendes Risiko liegt im Closure-History-Fix: er erweitert, welcher Baum fuer ein CLOSED-Finding als gueltige Bindung gilt. Er ist deshalb bewusst eng gefasst -- der Hash muss weiterhin exakt einem Baum entsprechen, dieser Baum kommt aus Gits Objektspeicher, und gesucht wird ausschliesslich unter Commits, die dieses Finding oder sein eigenes Review-Artefakt veraendert haben; READY_FOR_CLOSURE bleibt unveraendert an den aktuellen Stand gebunden. Das Risiko des Nichtstuns ist hoeher: ohne diesen Fix ist die Factory nach der ersten Closure nicht mehr benutzbar, und ohne die Preflight-Haertung meldet sie Betriebsbereitschaft, die nie geprueft wurde.
Verification Evidence: Alle Gates am 2026-08-15 im echten Repository auf Branch factory-change/operational-robustness-1 (Basis 371a0a4) tatsaechlich ausgefuehrt, nicht behauptet. (1) Regressionsmodule aus dem Testplan einzeln: python3 -m unittest factory.guards.test_build_order factory.guards.test_closure_history factory.guards.test_ops_robustness factory.guards.test_factory_preflight -- Ran 109 tests, OK. Dieselben Negativtests waren vor der Reparatur reproduzierbar rot (zitiert im Bauauftrag, Abschnitt Evidence). (2) Vollstaendige entdeckte Testsuite: python3 factory/guards/run-factory-tests.py -- Ran 299 tests, ci_test_failures: 0, ci_test_errors: 0, ci_tests_skipped: 0, FACTORY_TESTS: ALLE BESTANDEN. Entscheidend fuer F-19: SANDBOX_VERIFICATION: performed (1 Test real ausgefuehrt) -- der OS-Sandbox-Test wurde tatsaechlich verifiziert und nicht uebersprungen, weil dieser Lauf innerhalb einer aktiven Claude-Code-Sandbox stattfand. (3) Zentrale Guards direkt: python3 factory/guards/validate-build-order.py factory/build-orders/FACTORY-OPS-ROBUSTNESS-1.md -- GUELTIG; python3 factory/guards/validate-control-plane.py -- Control-Plane unveraendert (36 Dateien gegen Manifest geprueft); python3 factory/guards/finding_state.py assess FACTORY-OPS-ROBUSTNESS-1 -- deterministischer Zustandsblock ohne recorded state (sauberer Start). (4) Kanonischer Runner: python3 factory/guards/run-factory-checks.py -- Factory-Checks: ALLE BESTANDEN (finding-validator, build-order-guard, review-guard, control-plane-guard). (5) Projekttests: python3 factory/guards/run-project-tests.py -- Exit 0, kein app/-Verzeichnis (Vorlage ohne Produktcode, erwartet). Bootstrap-Offenlegung: die 32 geaenderten Control-Plane-Dateien konnten vom implementierenden Agenten nicht selbst geschrieben werden -- die Sperre wurde vorher positiv beobachtet (touch auf factory/guards/ ergab 'Operation not permitted'). Der Stand wurde in einer Arbeitskopie erzeugt und ueber einen externen, menschlich ausgefuehrten Apply-Schritt eingespielt; danach wurden alle 32 Dateien byte-identisch gegen die Arbeitskopie verifiziert (32 identisch, 0 abweichend) und das Manifest bewusst neu gestempelt.
CI Evidence: Not yet analyzed
Review Artifact: Not yet analyzed
