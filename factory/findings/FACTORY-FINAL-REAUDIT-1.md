# FACTORY-FINAL-REAUDIT-1

Status: CLOSED
Severity: P2

## Befund

Abschlusspaket des Factory-v1-Audits. Es ist **kein neuer Gesamtaudit**, sondern die Abarbeitung
genau der vier Restpunkte, die der unabhängige Reviewer in
[`factory/reviews/FACTORY-REAL-PROJECT-READINESS-1.round-2.md`](../reviews/FACTORY-REAL-PROJECT-READINESS-1.round-2.md)
(Feld `Findings And Objections`) als ausdrücklich **nicht** closure-blockierend festgehalten hat
und die in `FACTORY-REAL-PROJECT-READINESS-1` unter `Open Points For Re-Audit` als A–D
weitergereicht wurden. Sie wurden dort bewusst nicht mehr repariert, weil jede weitere Änderung
den Scope-Hash bewegt und das gerade erteilte `PASS` ungültig gemacht hätte.

**A — Doppelte Metadatenfelder im kanonischen Block werden still aufgelöst.** F-18 hat festgelegt,
*wo* Lifecycle-Metadaten stehen dürfen. Offen blieb, was passiert, wenn dasselbe Feld dort
**zweimal** steht. Die Regel war „der letzte gewinnt", und sie war stumm. Gegen den unveränderten
Parser im echten Repository beobachtet:

```
A1 doppelte Severity -> geparst: 'P1' (kanonisch zuerst: P0)
A1 P0-Hard-Stop-Fehler: []
A2 doppelter Status -> geparst: 'OPEN'
A3 doppeltes Review Artifact -> geparst: 'factory/reviews/DEMO.round-1.md'
```

`Severity: P0` gefolgt von `Severity: P1` ergibt P1 und **keinen** P0-Hard-Stop. Derselbe
Mechanismus trifft `Status:` — und über den Status hängt die Evidence-Pflicht des Bauauftrags:
ein Finding mit `Status: VERIFYING` und darunter `Status: OPEN` wird als OPEN gelesen, womit der
Bauauftrags-Guard weder rote noch grüne Evidence verlangt und einen leeren Bauauftrag akzeptiert
(real beobachtet: `errors == []`). Und `Review Artifact` zweimal genannt lässt die Closure auf die
zuletzt genannte Runde zeigen.

**B — Der Doku-Guard erkennt die tatsächlich verwendeten Formulierungen nicht.** `CLAUDE.md`
behauptete, `test_worktree_protection.py` schlage fehl, „wenn irgendein Dokument die
Parallelitätsbehauptung wieder einführt". `PARALLELISM_CLAIM_RE` prüfte drei wörtliche Wendungen.
Gegen zehn Formulierungen gehalten — darunter die **frühere** Fassung aus `CLAUDE.md` selbst und
die im Repository übliche Umlautschreibung — blieben **9 von 10** unerkannt.

**C — Der Bauauftrag von Paket 3 verschweigt die Hälfte einer Änderung.** Für
`factory/scripts/factory-preflight.sh` nennt er nur „neue Pflichtdateien". Die zweite,
sicherheitsrelevante Hälfte derselben Änderung — die Entfernung von `Bash(git worktree *)` aus der
`required`-Liste (der ZERO_ROUTINE_APPROVALS-Liste), weil Factory v1 worktree-basierte
Parallelität bewusst nicht unterstützt — steht dort nicht. Im Code ist sie ausführlich begründet
und durch `test_raw_git_worktree_is_not_a_required_routine_grant` gepinnt, also nicht verdeckt;
wer nur den Bauauftrag liest, erfährt aber nichts davon.

**D — Kosmetik.** Derselbe Bauauftrag enthält den Out-of-Scope-Absatz zweimal, ein Artefakt der
Nachbesserung nach Review-Runde 1.

**Severity-Begründung: `P2`, nicht `P1`.** Keine laufende Ausnutzung, kein Produktionsschaden, und
die Vorlage enthält weiterhin keinen Produktcode. A fügt keine Fähigkeit hinzu: wer `P1`
schreiben will, schreibt es einmal hin — der Bypass verlangt zwei widersprechende Zeilen im
sichtbaren kanonischen Block, die in jedem Diff und in jedem Review stehen. Es ist aber mehr als
Kosmetik, weil eine bereits geschlossene Invariante (P0-Hard-Stop aus F-09, Evidence-Pflicht aus
F-10) an einer stillen Auflösungsregel hängt statt an einer Verweigerung. B, C und D haben keine
Sicherheitswirkung; sie sind Fälle von „die Dokumentation behauptet mehr, als die Prüfung
leistet" — genau die Klasse, die dieses Audit beseitigen sollte. Dieselbe Einstufung hat der
unabhängige Reviewer in Runde 2 vorgenommen.

**Dies ist ein `FACTORY_CHANGE`.** Die Reparatur verändert die Kontrollebene, die sie
kontrolliert. Vollständige Offenlegung im Bauauftrag unter „Bootstrap-Situation".

## Analyse

Root Cause: A und B haben dieselbe Wurzel: eine Pruefung wurde gegen den erwarteten Normalfall
  entworfen, nicht gegen den mehrdeutigen Fall. Bei A entstand die Regel 'spaeter ueberschreibt
  frueher' als Nebenprodukt eines Dictionary-Aufbaus in _collect_fields und wurde nie als
  Entscheidung getroffen; sie ist aber genau das, denn zwei widersprechende Werte fuer ein
  Lifecycle- oder Sicherheitsfeld bedeuten, dass das Dokument nicht sagt, was der Status ist.
  Eine unbekannte Angabe muss blockieren und darf nicht zu derjenigen Zeile aufgeloest werden,
  die zufaellig zuletzt kommt. Bei B wurde die Pruefung aus drei woertlichen Wendungen gebaut,
  die zum Zeitpunkt des Schreibens gerade zur Hand waren -- und die Dokumentation beschrieb
  danach nicht diese Pruefung, sondern die Absicht dahinter ('schlaegt fehl, wenn irgendein
  Dokument die Behauptung wieder einfuehrt'). C und D sind Buchfuehrungsfehler derselben Art wie
  die in Runde 1 beanstandeten: der Record laeuft dem Diff nach, weil eine Nachbesserung den Code
  aenderte und die Begruendung nicht mitzog.
Affected Components: factory/guards/finding_format.py (der einzige Finding-Parser),
  factory/guards/validate-finding.py (Closure-Gate, P0-Hard-Stop),
  factory/guards/validate-build-order.py (Evidence-Lebenszyklus ueber den Finding-Status),
  factory/guards/test_finding_format.py (neue Regressionsklasse DuplicateFieldTests),
  factory/guards/test_worktree_protection.py (neuer Doku-Check statt PARALLELISM_CLAIM_RE),
  CLAUDE.md (die ueberzogene Guard-Behauptung), factory/ONBOARDING.md (der Finding-Worktree als
  vermeintliche Zero-Approval-Routine), factory/build-orders/FACTORY-REAL-PROJECT-READINESS-1.md
  (C und D) sowie factory/control-plane.sha256 als Manifest.
Relevant Architecture: Es gibt genau einen Finding-Parser (F-18), und an seinem Ergebnis haengen
  drei bereits geschlossene Invarianten gleichzeitig: der P0-Hard-Stop (F-09) ueber Severity, die
  Bauauftrags- und Evidence-Pflicht (F-10) ueber Status, und das gesamte Closure-Gate (F-01 bis
  F-04) ueber Review Artifact. Der Parser hat keine zweite Meinung ueber sich: keine spaetere
  Schicht bemerkt, dass ein Status falsch aufgeloest wurde. Deshalb ist die einzig vertretbare
  Reaktion auf Mehrdeutigkeit dort, gar nicht zu urteilen. Der Doku-Guard aus B liegt auf einer
  anderen Ebene: die eigentliche F-15-Absicherung sind die Sandbox, die praeventive Blockade in
  create-finding-worktree.sh und die Preflight-Liste; der Textcheck verhindert nur, dass die
  Dokumentation eine Faehigkeit verspricht, die es nicht gibt. Er darf deshalb nicht so tun, als
  sei er ein Sprachverstaendnis.
Recommended Repair: A: _collect_fields meldet wiederholte Feldnamen, statt sie aufzuloesen;
  parse_finding gibt duplicate_metadata_fields und duplicate_analysis_fields zurueck.
  validate-finding.py macht daraus einen harten Fehler und bricht ab, bevor Status, Severity oder
  Review Artifact ueberhaupt gelesen werden -- ein Urteil aus einem von zwei widersprechenden
  Werten waere ein Urteil ueber ein Dokument, das es nicht gibt. validate-build-order.py prueft
  dieselbe Mehrdeutigkeit, bevor es den Status fuer den Evidence-Lebenszyklus verwendet. Die
  Regel gilt fuer jeden Feldnamen und nicht fuer eine kuratierte Liste sicherheitsrelevanter
  Felder: eine solche Liste waere die zweite, still divergierende Liste, die F-18 gerade
  beseitigt hat. B: die Pruefung wird umgedreht. Ein Satz, der Parallelitaet oder gleichzeitige
  Arbeit erwaehnt, muss sie im selben Satz ausschliessen; erwaehnen ohne Ausschluss ist der
  Befund. Das ist eine Formulierungspruefung und wird auch so dokumentiert -- CLAUDE.md wird auf
  die Aussage reduziert, die die Pruefung wirklich traegt. Zusaetzlich wird der letzte Ort
  bereinigt, an dem ein Finding-Worktree wie unterstuetzte Routine aussah
  (ZERO_ROUTINE_APPROVALS-Liste in ONBOARDING.md). C und D: Dokumentationskorrektur im Bauauftrag
  von Paket 3, ausschliesslich ergaenzend beziehungsweise das Duplikat entfernend; kein
  Evidence-Abschnitt und keine Review-Runde wird angefasst.
Regression Test Plan: Negativtests zuerst, gegen den unveraenderten Produktionsstand im echten
  Repository rot beobachtet, mit den echten Guards (per Symlink geladen, nicht mit Kopien).
  Fuer A eine neue Klasse DuplicateFieldTests in factory/guards/test_finding_format.py mit zehn
  Faellen: doppelte Severity wird gemeldet statt aufgeloest; doppelte Severity kann ein P0 nicht
  herabstufen; doppelter Status wird abgelehnt; doppeltes Review Artifact wird abgelehnt;
  Erkennung ist gross-/kleinschreibungsunabhaengig; ein mehrdeutiges Finding wird nicht weiter
  beurteilt (genau ein Fehler); eine eingerueckte Wiederholung bleibt Fortsetzungszeile; eine
  Wiederholung in einem Fenced Block ist keine Wiederholung; kein bestehendes Finding des
  Repositories wiederholt ein Feld; und der Bauauftrags-Guard verweigert einen mehrdeutigen
  Status. Fuer B vier neue Faelle in DocumentationTests plus der umgestellte Bestandstest: ein
  Positivkorpus von zehn Formulierungen (darunter die fruehere CLAUDE.md-Fassung und beide
  Umlautschreibungen) muss erkannt werden, ein Negativkorpus aus den real verwendeten
  ausschliessenden Saetzen darf nicht erkannt werden, ein zitierter Anspruch in einem Fenced Block
  ist kein Anspruch, eine ueber zwei Zeilen umbrochene Verneinung bleibt eine Verneinung, CLAUDE.md
  verspricht nicht mehr als die Pruefung leistet, und die ZERO_ROUTINE_APPROVALS-Liste fuehrt den
  Worktree-Pfad nicht als Routine. Danach Regression gegen F-01 bis F-21 ueber die vollstaendige
  entdeckte Testsuite, den kanonischen Runner, den Preflight und den Projekt-Test-Adapter.
Central Guard Plan: Kein neuer Guard, sondern zwei bestehende werden an der Stelle geschaerft, an
  der sie bisher geraten haben. Erstens bleibt finding_format.py der einzige Parser, meldet
  Mehrdeutigkeit aber jetzt strukturiert nach oben, sodass jeder Konsument sie sehen muss und
  nicht selbst nachimplementieren kann; validate-finding.py und validate-build-order.py sind die
  beiden Konsumenten und behandeln sie beide als harten Fehler. Zweitens wird der Doku-Check von
  einer Positivliste woertlicher Wendungen auf die Regel 'erwaehnen erzwingt ausschliessen'
  umgestellt und mit einem Positiv- und einem Negativkorpus im Test verankert, sodass eine spaeter
  eingefuehrte Behauptung auffaellt und ein korrekt ausschliessender Satz nicht faelschlich
  anschlaegt. Beide laufen im kanonischen Runner beziehungsweise in der automatisch entdeckten
  Testsuite und damit in jedem CI-Lauf, ohne irgendwo registriert werden zu muessen.
Expected Blast Radius: Ausschliesslich die Factory-Infrastruktur; kein Produktcode ist betroffen,
  weil die Vorlage keinen enthaelt. Fuer bestehende Findings ist die Aenderung
  rueckwaertskompatibel: kein Finding dieses Repositories wiederholt ein Feld, positiv geprueft
  ueber alle vier Findings. Nicht rueckwaertskompatibel ist genau der beabsichtigte Fall -- ein
  Finding, das dasselbe Feld zweimal angibt, wird ab jetzt abgelehnt statt still aufgeloest. Der
  Doku-Check kann Dokumentation melden, die Parallelitaet erwaehnt, ohne sie auszuschliessen; das
  ist sein Zweck. Vier Wirkungsorte ausserhalb der Guards: CLAUDE.md (eine Aufzaehlungsposition),
  ONBOARDING.md (eine Aufzaehlungsposition) und der Bauauftrag von Paket 3 (ein ergaenzter Absatz,
  ein entferntes Duplikat).
Risk Assessment: Das groesste Risiko der Aenderung ist ein falsches Rot am empfindlichsten Punkt
  der Factory: der Parser entscheidet ueber P0-Hard-Stop, Evidence-Pflicht und Closure-Gate
  gleichzeitig, und eine zu breite Duplikaterkennung koennte gueltige Findings blockieren. Die
  Gegenmassnahmen sind, dass die Fortsetzungsregel (eingerueckt) und die Fenced-Block-Regel aus
  F-18 unveraendert vorgeschaltet bleiben -- beide sind eigens getestet -- und dass alle
  bestehenden Findings als Regressionskorpus dienen. Beim Doku-Check ist das Risiko ein
  Fehlalarm auf korrekt formulierter Dokumentation; deshalb der Negativkorpus aus real
  verwendeten Saetzen und die Blockbildung, die eine ueber zwei Zeilen umbrochene Verneinung
  zusammenhaelt. Ausdruecklich nicht behauptet wird, dass der Check jede denkbare Umschreibung
  erkennt: er ist eine Formulierungspruefung, und genau das steht jetzt auch in CLAUDE.md. Das
  Risiko des Nichtstuns ist gering, aber nicht null: A laesst eine geschlossene Invariante an
  einer stillen Aufloesungsregel haengen, und B laesst eine Dokumentationszusage bestehen, die
  ihre Pruefung nicht deckt -- genau der Fehlertyp, den dieses Audit ueberall sonst beseitigt hat.
Verification Evidence: Alle Gates am 2026-08-15 im echten Repository auf Branch
  factory-change/final-reaudit-1 (Basis f74a17a636213b2779ba62ea3e88f4cc5a81ef8a) tatsaechlich
  ausgefuehrt, nicht behauptet. (1) Rot zuerst, gegen die unveraenderten Guards und per Symlink
  geladen, also gegen den Produktionsstand und nicht gegen eine Kopie:
  test_finding_format.DuplicateFieldTests meldete FAILED (failures=3, errors=10),
  test_worktree_protection.DocumentationTests meldete FAILED (failures=4). Der schwerste rote
  Fall war nicht die Severity, sondern der Bauauftrags-Guard: fuer ein Finding mit Status
  VERIFYING und darunter Status OPEN lieferte validate_build_order eine leere Fehlerliste, hat
  also einen Bauauftrag voellig ohne Evidence akzeptiert. (2) Byte-identische Verifikation nach
  dem einen externen Apply-Schritt: 6 von 6 geschuetzten Dateien identisch, 0 abweichend, dazu
  die beiden ungeschuetzten Dokumentationsdateien ebenfalls identisch. (3) Manifest: der Diff von
  factory/control-plane.sha256 umfasst genau sechs Zeilen fuer die sechs geaenderten
  Control-Plane-Dateien; validate-control-plane.py meldet 'Control-Plane unveraendert (42 Dateien
  gegen Manifest geprueft)', Exit 0. (4) Gruen danach: DuplicateFieldTests Ran 10, OK;
  DocumentationTests Ran 10, OK; beide Module zusammen Ran 47, OK. (5) Vollstaendige entdeckte
  Testsuite: run-factory-tests.py -- Ran 372 tests, ci_test_failures 0, ci_test_errors 0,
  ci_tests_skipped 0, SANDBOX_VERIFICATION: performed, FACTORY_TESTS: ALLE BESTANDEN. 372 statt
  356 entspricht exakt den 16 neu hinzugekommenen Faellen (10 fuer A, 6 fuer B), automatisch
  entdeckt ohne jede Registrierung. (6) Kanonischer Runner: ALLE BESTANDEN, Exit 0, einschliesslich
  finding-validator und build-order-guard fuer alle vier Findings, review-guard fuer alle vier
  Runden, control-plane-guard und project-tests-guard. (7) Projekt-Test-Adapter:
  TEMPLATE_WITHOUT_PRODUCT, Exit 0. (8) Regression gegen F-01 bis F-21 gezielt in zwei Gruppen:
  test_trust_core, test_ops_robustness, test_closure_history, test_build_order -- Ran 120, OK;
  test_validate_finding, test_validate_review, test_control_plane, test_gh_evidence,
  test_project_tests, test_factory_preflight, test_create_finding_worktree,
  test_run_factory_checks -- Ran 173, OK. Zusaetzlich live belegt: die drei bereits geschlossenen
  Findings bestehen den finding-validator weiterhin, obwohl dieser Commit den Scope-Hash bewegt --
  der Historien-Fallback fuer CLOSED wirkt unveraendert. (9) Hook- und Provenienztests direkt:
  test_stop_validate_findings.py Ran 7, OK; test_subagentstop_write_review.py Ran 24, OK;
  Sandbox-Verifikation test_sandbox_protects_reviews.py Ran 1, OK. (10) Preflight: Factory- und
  GitHub-Ebene gruen (Manifest, Runner, 372 CI-Tests, durchgefuehrte Sandbox-Verifikation,
  Default-Branch live, Push- und PR-Rechte, CI lesbar, PR-Pflicht auf main, Required Status Check
  factory-checks konfiguriert, keine erforderlichen Approvals). Er endet dennoch BLOCKED wegen
  zweier maschinenlokaler Punkte, die gemeldet und nicht umgangen werden -- siehe Known
  Limitations. Bootstrap-Offenlegung: die geschuetzten Control-Plane-Pfade konnten vom
  implementierenden Agenten nicht selbst geschrieben werden; der getestete Stand wurde im
  Scratchpad vorbereitet und ueber genau einen externen, menschlich ausgefuehrten Apply-Schritt
  eingespielt.
CI Evidence: Echte externe GitHub-CI, gruen fuer exakt den Head-SHA
  7fe83dfe4bf9baac2f51663d5cd4bf3205e765c3 auf PR #7
  (https://github.com/Pransanth/software-factory-template/pull/7). Das Urteil ist nicht aus Prosa
  gelesen, sondern vom festen Helfer: factory/scripts/gh-query.sh required-check
  7fe83dfe4bf9baac2f51663d5cd4bf3205e765c3 -- verdict: success, check_name: factory-checks,
  matching_runs: 2, Exit 0. Nur Exit 0 darf zu einem Merge fuehren; 'absent' waere kein Erfolg.
  Zugehoerige Actions-Laeufe, beide auf demselben Head-SHA und beide conclusion=success:
  id=31900303242 (Factory CI, event=pull_request) und id=31900284150 (Factory CI, event=push).
  Der Job factory-checks fuehrt den kanonischen Runner, den Projekt-Test-Adapter und die
  automatisch entdeckte Testsuite aus; die 16 in diesem Paket neu hinzugekommenen Testfaelle liefen
  dort mit, ohne irgendwo registriert worden zu sein (F-19 im echten Betrieb). Anmerkung zur
  Aussagekraft: in der CI laeuft keine Claude-Code-Sandbox, die sandbox-abhaengigen Tests werden
  dort also als SANDBOX_VERIFICATION: not_performed ausgewiesen und zaehlen nicht als bestanden --
  ihr realer Nachweis stammt aus dem lokalen Lauf dieser Sitzung (ci_tests_skipped: 0,
  SANDBOX_VERIFICATION: performed), siehe Verification Evidence.
Review Artifact: factory/reviews/FACTORY-FINAL-REAUDIT-1.round-1.md
Human Decision (FACTORY_CHANGE): Punkt 5 des FACTORY_CHANGE-Ablaufs verlangt eine menschliche
  Entscheidung, weil eine Kontrollebene, die ihre eigene Reparatur allein freigibt, keine Kontrolle
  ist. Sie liegt in zwei getrennten Handlungen des Projektinhabers vor: (1) Der ausdrueckliche
  Auftrag, diesen finalen Re-Audit nach FACTORY_CHANGE-Regeln durchzufuehren und bis Closure und
  Merge zu bringen, wurde in Kenntnis seines FACTORY_CHANGE-Charakters erteilt, einschliesslich der
  ausdruecklichen Vorgabe, geschuetzte Dateien nicht selbst zu entsperren und alle geschuetzten
  Aenderungen in einem externen Apply-Paket zu buendeln. (2) Der externe Apply-Schritt wurde
  bewusst manuell im normalen Terminal ausgefuehrt; sein Skriptkopf legt offen, dass es ein
  FACTORY_CHANGE ist, welche sechs Dateien er schreibt und dass das Manifest neu gestempelt wird.
  Die Entscheidung wird nicht aus dem PASS des Reviewers abgeleitet.
Review History: Runde 1 endete mit Result PASS (Reviewed Scope Hash
  sha256:bd333f85413813c2718a75301d36770e2e49d9f6bc3d3329177e1edad380a0c9, Reviewer Agent Type
  finding-closure-reviewer). Der Reviewer hat den gesamten Control-Plane-Diff als FACTORY_CHANGE
  gepruefft und die roten Evidence-Zahlen mechanisch gegen den heutigen Testtext rekonstruiert
  statt sie zu uebernehmen; die Rueckwaertskompatibilitaet hat er selbst nachgeprueft (kein
  wiederholter Feldname in irgendeinem der fuenf Findings) und die Manifest-Buchhaltung
  nachgezaehlt (42 Hash-Zeilen, Diff genau sechs). Zwei nicht closure-blockierende Einwaende hat er
  festgehalten; sie stehen unter Open Points nachfolgend und wurden nicht weggeschrieben.
Open Points After Review: Der unabhaengige Reviewer hat in Runde 1 zwei konkrete, ausdruecklich
  nicht closure-blockierende Einwaende erhoben, die bewusst NICHT mehr repariert wurden. Der Grund
  ist derselbe, aus dem Paket 3 seine Restpunkte weitergereicht hat: beide liegen in
  factory/guards/test_worktree_protection.py, einer geschuetzten Control-Plane-Datei, die der
  implementierende Agent nicht schreiben kann; jede Reparatur haette einen zweiten externen
  Apply-Schritt, eine Verschiebung des Scope-Hashes und damit den Verfall des soeben erteilten PASS
  bedeutet. (1) UEBERZOGENE DOCSTRING: die Klassen-Docstring von DocumentationTests
  (test_worktree_protection.py, 'No unproven parallelism claim may exist in the repository.') sagt
  weiterhin 'im Repository', waehrend tatsaechlich vier benannte Dokumente auf Satzebene geprueft
  werden. Das ist derselbe Fehlertyp, den Punkt B fuer CLAUDE.md beseitigt hat -- die
  Anforderungsquelle fuer B (FACTORY-REAL-PROJECT-READINESS-1, Open Points For Re-Audit, Punkt B)
  nennt allerdings ausschliesslich die CLAUDE.md-Formulierung, und der korrekte Geltungsbereich
  steht im selben File unmittelbar darueber im Modulkommentar ('Deliberately NOT scanned:
  factory/findings/**, ... factory/reviews/**') und darunter im DOCS-Tupel. Aus einer
  Testdatei-Docstring wird keine Entscheidung abgeleitet. (2) KOSMETIK: der Modulkommentar
  derselben Datei schreibt 'all nine of the formulations in POSITIVE_CORPUS below went undetected',
  waehrend POSITIVE_CORPUS zehn Eintraege hat; die Evidence im Bauauftrag sagt korrekt 9/10. Ein
  Kommentar, keine Pruefung. Beide sind P3/Improvement, keine P0- oder P1-Regression, und beide
  sind hier festgehalten statt weggeschrieben. Vom Reviewer zusaetzlich benannte Restrisiken, alle
  ohne Sicherheitswirkung und im Code bzw. in CLAUDE.md offengelegt: RULED_OUT_RE ist bewusst
  lenient (ein Satz wie 'Frueher war das anders: parallele Worktrees sind jetzt unterstuetzt' kaeme
  durch); die Umstellung von test_no_document_claims_parallel_worktree_safety ist nicht in jeder
  Richtung strenger (ein Satz mit einer der drei alten Wendungen UND einem Ausschlussmarker wird
  jetzt durchgelassen), netto aber deutlich breiter (10 statt 1 erkannte Formulierung); zwei der
  vier geprueften Dokumente enthalten ueberhaupt keinen Parallelitaetsterminus, und ein geloeschtes
  Dokument wird still uebersprungen; test_a_finding_worktree_is_not_advertised_as_routine prueft
  zwei Literale, eine andere Formulierung wuerde nicht anschlagen; und die neue Duplikatregel macht
  zwei gleichnamige Spalte-0-Zeilen im Analyse-Abschnitt zum harten Fehler, was als gewolltes neues
  Rot im Blast Radius dokumentiert ist.
Known Limitations: Zwei Punkte bleiben nach diesem Paket offen und werden nicht weggeschrieben.
  (1) Der Preflight endet auf dieser Maschine BLOCKED, aus zwei Gruenden, die beide nichts mit
  A bis D zu tun haben: unbekannte Shell-Freigaben in .claude/settings.local.json (Altbestand
  frueherer Sitzungen; die Datei ist gitignored, nicht Teil der Vorlage und wurde in diesem Paket
  nicht angefasst -- ihre Bereinigung ist ausdruecklich ein menschlicher Schritt, und die Factory
  erteilt sich keine Rechte selbst; FACTORY-TRUST-CORE-1 dokumentiert denselben Zustand als
  Praezedenzfall) und die nicht-interaktive Credential-Abfrage, die den Schluesselbund nicht lesen
  darf. Der zweite Punkt ist eine Grenze der Abfrageform, nicht ein fehlendes Credential: im selben
  Lauf melden gh-api.sh, gh-query.sh, die Contents- und Pull-Request-Rechtepruefung und die
  Actions-Lesbarkeit alle OK. (2) Der Doku-Guard aus B ist ausdruecklich eine
  Formulierungspruefung und kein Sprachverstaendnis. Er erkennt die tatsaechlich verwendeten
  Schreibweisen in beiden Umlautvarianten und meldet jeden Satz, der Parallelitaet oder
  gleichzeitige Arbeit erwaehnt, ohne sie im selben Satz auszuschliessen; eine hinreichend freie
  Umschreibung kann ihm entgehen. Genau das steht jetzt auch in CLAUDE.md, statt wie bisher mehr
  zu versprechen. Die eigentliche F-15-Absicherung bleibt unveraendert die Sandbox, die praeventive
  Blockade in create-finding-worktree.sh und die Preflight-Liste. Beide Punkte sind Improvement
  beziehungsweise P3, kein P0 und kein P1.
