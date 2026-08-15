# Software Factory – Leitplanken für Claude

Dieses Repository ist die übertragbare Vorlage einer "Software Factory": ein wiederholbarer
Prozess, mit dem Sicherheitsbefunde (und später andere technische Arbeit) kontrolliert von der
Meldung bis zum Abschluss durchlaufen — mit klaren Zuständen und Guards, die die Regeln
unabhängig von jeder einzelnen Claude-Anweisung durchsetzen.

Der Anspruch der Vorlage ist nicht "Claude darf alles", sondern: **normale Finding-Arbeit läuft
unbeaufsichtigt und ohne Routine-Rückfragen durch, und genau die wenigen echten
Entscheidungspunkte stoppen.**

## Aktueller Stand dieser Vorlage

Die Vorlage enthält ausschließlich Factory-Infrastruktur: Workflow-Definition, Guards, Hooks,
den unabhängigen Reviewer, die GitHub-/CI-Helfer, den Onboarding-Preflight und ein
Beispiel-Finding als Formatvorlage. Es gibt **keinen** Produktcode und **keinen** echten Fix.
Solange nichts anderes vereinbart ist:

- Baue keine Anwendung "auf Verdacht".
- Analysiere oder repariere das Beispiel-Finding nicht technisch — es ist bewusst nur eine
  Formatvorlage.

Sobald die Vorlage für ein echtes Projekt kopiert wird, kommt der Produktcode dazu — an
beliebiger Stelle und in beliebiger Sprache. Die Factory kennt weder ein Verzeichnis noch ein
Testframework des Produkts; sie führt aus, was [`factory/project-tests.conf`](factory/project-tests.conf)
deklariert (siehe „Produkttests" unten). Eine frühere Fassung dieses Absatzes nannte hier die
Konvention `app/` — die gibt es nicht mehr.

## Zuerst: einmaliges Onboarding

Bevor in einem **neuen** Projekt der erste Finding-Lauf startet, einmalig:

```
factory/scripts/factory-preflight.sh
```

Der Preflight prüft deterministisch alle Voraussetzungen (eigenes Repo, `origin`, Default-Branch,
repo-spezifisches GitHub-Credential, GitHub-API, `gh-api.sh`, `gh-query.sh`, PR-Rechte,
CI-Lesbarkeit, Branch-Schutz, Required Status Check, lokale Allows, geschützte Dateien) und
**führt die Factory tatsächlich aus** — Control-Plane-Guard, kanonischer Runner und die
automatisch entdeckte Testsuite. Ein Repository, dessen Pflichtdateien nur Platzhalter sind,
besteht ihn nicht.

Er endet mit genau einem von drei Ergebnissen:

| Ergebnis | Exit | Bedeutung |
|---|---|---|
| `FACTORY_PREFLIGHT: PASS` | 0 | Lokale **und** GitHub-/Remote-Ebene geprüft; unbeaufsichtigte Läufe sind bereit. |
| `FACTORY_PREFLIGHT: BLOCKED` | 1 | Mindestens eine Voraussetzung fehlt; jede wird mit dem exakten einmaligen Schritt genannt. |
| `FACTORY_PREFLIGHT: PARTIAL` | 3 | Nur mit `--local-only`: die lokale Ebene ist in Ordnung, die GitHub-Ebene wurde **nicht geprüft**. Das ist ausdrücklich kein PASS. |

`PARTIAL` existiert, weil `--local-only` früher `PASS` meldete und damit ein Urteil über eine
Ebene fällte, die es nie betreten hatte. Eine nicht geprüfte Ebene ist keine bestandene Ebene.

Er ändert **nichts** und automatisiert bewusst nichts, was aus Sicherheitsgründen menschlich
bleiben muss (Token-Erstellung, GitHub-Admin/Ruleset, Vergabe lokaler Berechtigungen). Details:
[`factory/ONBOARDING.md`](factory/ONBOARDING.md).

Ist der Preflight `BLOCKED`: die genannten Schritte melden, **nicht** umgehen, **nicht** durch
breitere Berechtigungen ersetzen — und danach den Preflight erneut ausführen. Meldet er einen
`[GOVERNANCE]`-Punkt (z. B. erforderliche Approvals auf dem Default-Branch), ist das keine
technische Aufgabe: der Projektinhaber entscheidet, ob die Factory autonom mergen darf oder ob
der letzte Schritt menschlich bleibt. Ein technischer Workaround dafür wird nicht gebaut.

## Produkttests: die Factory kennt das Testframework des Projekts nicht

Die Factory sucht **nicht** nach Testdateien und rät nicht, in welcher Sprache das Produkt
geschrieben ist. Das Projekt deklariert seine Testkommandos in
[`factory/project-tests.conf`](factory/project-tests.conf), und
[`factory/guards/run-project-tests.py`](factory/guards/run-project-tests.py) führt genau diese aus
— als Argumentliste, ohne Shell.

Vorher war das anders und still gefährlich (Audit-Befund F-21): gesucht wurde `app/**/test_*.py`.
Für ein Go-, Node-, Java- oder Multi-Service-Projekt fand die Suche nichts — und meldete Exit 0.
Die einzige Stelle, an der die Factory fragt „funktioniert das Produkt noch?", antwortete „ja",
ohne je einen Produkttest ausgeführt zu haben.

Es gibt genau drei Zustände, und nur der erste ist ohne Produkttests grün:

| Zustand | Exit | Bedeutung |
|---|---|---|
| `TEMPLATE_WITHOUT_PRODUCT` | 0 | Reine Vorlage: keine getrackten Dateien außerhalb der Factory-Pfade, `mode: template`. |
| `CONFIGURED` | 0 / 1 | Mindestens eine Suite deklariert; **jede** wird ausgeführt, ein einziger roter Exit-Code ist Gesamtfehler. |
| `REAL_PROJECT_WITHOUT_TEST_CONFIGURATION` | 2 | Produktcode vorhanden, aber keine Suite konfiguriert. Harter Blocker. |

„Nichts gefunden" bedeutet nie mehr Exit 0. Eine fehlende `project-tests.conf` ist immer ein
Blocker — die Vorlage liefert sie mit, ihr Fehlen heißt also, dass jemand sie entfernt hat.

## Grundregel: Sicherheitsbefunde nicht direkt reparieren

Sicherheitsbefunde werden **nicht direkt repariert**. Sie durchlaufen stattdessen den
Factory-Workflow und werden erst nach abgeschlossener Analyse und Verifikation umgesetzt.
Direktes "schnell mal fixen" umgeht die Analyse-, Test- und Nachvollziehbarkeitsschritte, die der
Workflow erzwingt, und ist deshalb nicht erlaubt.

## Workflow-Zustände

```
OPEN → ANALYZED → IMPLEMENTING → VERIFYING → READY_FOR_CLOSURE → CLOSED
```

Zusätzlich existiert der Eskalationszustand `EXPERT_REVIEW_REQUIRED` (siehe unten). Die genauen
Anforderungen an jeden Zustand stehen in [`.claude/rules/factory-workflow.md`](.claude/rules/factory-workflow.md).
Der standardisierte Weg von `IMPLEMENTING` bis `CLOSED` inklusive Push, PR, echter CI und Merge
ist der [`verify-finding`-Skill](.claude/skills/verify-finding/SKILL.md).

**Ab `IMPLEMENTING` braucht jedes Finding einen gültigen Bauauftrag** unter
`factory/build-orders/<Finding-ID>.md`. Das ist keine Konvention mehr, sondern eine technische
Bedingung: [`factory/guards/validate-build-order.py`](factory/guards/validate-build-order.py)
prüft Pfad, gegenseitige Bindung an das Finding, die Pflichtabschnitte, Platzhalter und —
abhängig vom Status — ob die Evidence-Abschnitte einen tatsächlich zitierten Lauf enthalten. Der
kanonische Runner führt ihn aus, also auch jede CI. Der Grund ist nicht Formalismus: der
unabhängige Reviewer soll ausdrücklich kein eigenes Sicherheitsmodell erfinden, sondern den
Bauauftrag gegen den echten Code halten — ohne Bauauftrag hält er nichts.

**Nach einem Abbruch wird der Zustand ermittelt, nicht geraten.** Stirbt eine Session mitten im
Lauf, beantwortet
[`factory/guards/finding_state.py`](factory/guards/finding_state.py) `assess <ID>`
deterministisch, was schon passiert ist: existiert der Branch, ist der zuletzt gepushte Stand
noch der aktuelle, gibt es einen Pull Request, deckt die CI-Evidence den heutigen Head, deckt das
letzte Review den heutigen Scope-Hash. Ergänzend liefert
`factory/scripts/gh-query.sh pr-for-branch <BRANCH>` die GitHub-Sicht (auch „bereits gemergt"),
und `create-finding-worktree.sh create` ist idempotent: ein bereits vorhandener Worktree wird
geprüft und gemeldet, nie gelöscht. **Veraltete Evidence gilt dabei als ungültig, nicht als
vorhanden** — ein „grün" von vor drei Commits ist kein Beleg für den heutigen Stand.

## Technische Entscheidungen trifft Claude selbst

Claude trifft normale technische Entscheidungen (Ursachenanalyse, Reparaturansatz, Testplan,
Guard-Design) eigenständig und begründet sie schriftlich im jeweiligen Finding. Ein
nicht-technischer Projektinhaber soll **nicht** pro forma technische Sicherheitsrisiken
freigeben müssen — das wäre keine echte Kontrolle, sondern nur ein Ritual.

Daraus folgt für den laufenden Betrieb: **keine technischen Routinefragen an den Benutzer.** Ob
ein Branch angelegt, ein Commit gemacht, gepusht, ein PR eröffnet, CI abgefragt, ein Review
angestoßen oder ein grüner PR gemerged wird, ist keine Frage — das ist die Routine, die diese
Factory autorisiert. Wenn eine Antwort aus den Regeln in diesem Repository ableitbar ist, wird sie
abgeleitet und nicht erfragt.

## Wann die Factory wirklich stoppt

Genau vier Situationen beenden den unbeaufsichtigten Lauf. Alles andere ist Routine.

1. **P0** — ein Befund mit akuter, laufender Ausnutzung bzw. unmittelbarem Produktionsschaden.
   Ein P0 wird nicht autonom durchgearbeitet: Befund festhalten, Sofortlage beschreiben, stoppen,
   Menschen einbeziehen. Das ist **technisch erzwungen**, nicht nur hier beschrieben: jedes
   Finding trägt ab `ANALYZED` ein Pflichtfeld `Severity:` (`P0`–`P3`), und der Guard lässt für
   `Severity: P0` ausschließlich die Zustände `OPEN`, `ANALYZED` und `EXPERT_REVIEW_REQUIRED` zu.
2. **`EXPERT_REVIEW_REQUIRED`** — Claude selbst oder der unabhängige Reviewer stellt fest, dass
   eine autonome Entscheidung nicht verantwortbar ist (ungewöhnlich hohes technisches Risiko,
   große Unsicherheit über die Auswirkungen, potenziell irreversible Konsequenzen). Status setzen,
   die fünf Pflichtfelder ausfüllen, stoppen.
3. **Echte Produkt- oder Scope-Entscheidung** — eine Frage, die nicht technisch, sondern
   inhaltlich ist: Was soll das Produkt können? Ist dieses Verhalten gewollt? Soll ein Feature
   fallen? Solche Fragen entscheidet der Projektinhaber, nicht die Factory.
4. **`AUTONOMY_BLOCKER`** — eine technische Voraussetzung der Factory selbst fehlt oder ist
   inkonsistent (z. B. Worktree-HEAD ≠ erwarteter Basis-SHA, Preflight `BLOCKED`, Required Status
   Check nicht konfiguriert). Konkret melden, nicht umgehen.

## Tests und Sicherheitskontrollen dürfen nicht abgeschwächt werden

Tests oder Sicherheitskontrollen dürfen niemals abgeschwächt, übersprungen oder entfernt werden,
nur damit etwas grün wird oder ein Status schneller erreicht wird. Wenn ein Test oder eine
Kontrolle einem Fix im Weg steht, ist das ein Signal, den Fix oder die Analyse zu überdenken —
nicht die Kontrolle zu schwächen.

Das gilt ausdrücklich auch für die Grenzen der Factory selbst: **Während eines Findings werden
keine Sicherheitsgrenzen gelockert.** Die gesamte Kontrollebene ist gegen Selbstveränderung
geschützt:

```
factory/reviews/**       factory/guards/**        factory/scripts/**
.claude/hooks/**         .claude/agents/**        .claude/skills/**
.claude/rules/**         .claude/settings*.json   .github/workflows/**
CLAUDE.md                factory/control-plane.sha256
factory/project-tests.conf
```

`factory/project-tests.conf` gehört seit dem Real-Project-Readiness-Paket dazu: dort steht, welche
Produkttests als gültige Verification gelten. Wer das während normaler Finding-Arbeit ändern
könnte, könnte eine rote Testsuite verschwinden lassen, ohne eine einzige Testdatei anzufassen.
Sie wird einmalig beim Onboarding eines echten Projekts konfiguriert — als `FACTORY_CHANGE`.

Der Schutz ist zweischichtig: lokal über `permissions.deny` und `sandbox.filesystem.denyWrite`
in `.claude/settings.json`, und — verbindlich, weil serverseitig — über
[`factory/guards/validate-control-plane.py`](factory/guards/validate-control-plane.py), das
diese Pfade in jedem CI-Lauf gegen das gestempelte Manifest `factory/control-plane.sha256`
prüft. Ein Finding, das diese Pfade anfassen will, ist per Definition außerhalb seines Scopes;
eine beabsichtigte Änderung daran ist ein **`FACTORY_CHANGE`** mit eigenem, strengerem Ablauf
(siehe [`.claude/rules/factory-workflow.md`](.claude/rules/factory-workflow.md)).

**Was „zweischichtig" genau heißt — und wo es das nicht heißt.** Der unabhängige Review von
`FACTORY-TRUST-CORE-1` hat zu Recht beanstandet, dass dieser Satz mehr versprach, als die
Konfiguration hielt: `CLAUDE.md` und `factory/control-plane.sha256` standen in der Liste oben,
aber in keinem `deny`- und keinem `denyWrite`-Eintrag. Beide sind jetzt lokal gesperrt, der Satz
stimmt also für jeden Pfad der Liste. Zwei Einschränkungen bleiben und werden nicht
weggeschrieben:

- **Das Manifest kann sich nicht selbst hashen.** Für `factory/control-plane.sha256` existiert
  die serverseitige Schicht naturgemäß nicht; dort wirken die lokale Sperre und die Sichtbarkeit
  im Diff. Deshalb ist auch ein `--update` des Manifests kein Routinebefehl mehr, den die Session
  selbst absetzen kann — er gehört in den bewussten, extern angewandten `FACTORY_CHANGE`-Schritt.
- **Wer beides im selben Commit ändert, besteht den Guard.** Das ist die dokumentierte
  Bootstrap-Grenze (siehe `validate-control-plane.py` und `.claude/rules/factory-workflow.md`),
  keine Lücke, die diese Zeilen schließen könnten. Was der Guard leistet, ist der Wechsel von
  stiller Drift zu einem Manifest-Diff, den ein Review nicht übersehen kann.

Die lokale Schicht ist außerdem *lokal*: sie gilt auf der Maschine, auf der Claude Code läuft,
und sagt nichts darüber, was in einem Pull Request ankommt. Verbindlich ist die serverseitige
Prüfung. Der Preflight prüft beide Schichten und meldet fehlende Einträge namentlich.

Auch die richtige Reaktion auf eine Approval-Abfrage ist **nie**, die Berechtigungen zu
erweitern, sondern den Befehl in die unten beschriebene einfache Form zu bringen.

## Git-Routine: einfache Befehle aus dem Repo-Verzeichnis, nie `git -C <pfad>`

Alle Routine-Git-Befehle der Factory laufen als **einfache** Befehle aus dem bereits richtigen
Arbeitsverzeichnis — der Repo-Wurzel bzw. dem Worktree des jeweiligen Findings:

```
git add <pfade>
git commit -m "..."
git fetch origin
git push origin <branch>
```

Genau diese einfache Form ist allowlistet und läuft ohne Approval-Abfrage. Die Allowlist-Einträge
sind **Präfix-Muster** (`git add *`, `git commit *`, `git fetch origin`, `git push origin *`, …).
Ein vorangestelltes `-C` verschiebt den Befehlsanfang und trifft deshalb kein einziges Muster
mehr: `git -C <pfad> commit …` erzeugt eine Approval-Abfrage und bricht damit einen
unbeaufsichtigten Factory-Lauf ab. Daraus folgt:

- **Kein** `git -C <pfad> commit …`, `git -C <pfad> push …` o. Ä. für normale Finding-Arbeit.
  Stattdessen zuerst in das richtige Verzeichnis wechseln und dann den einfachen Befehl absetzen.
  In v1 ist das immer die Repo-Wurzel: die Factory arbeitet sequentiell, siehe „Mehrere Findings"
  unten.
- Auch keine Ersatzkonstruktionen wie `cd <pfad> && git commit …`: zusammengesetzte Befehle,
  Subshells, Command-Substitution (`$(...)`), Pipelines und inline `python3 -c "..."` treffen die
  Präfix-Muster ebenso wenig und sind für Routinearbeit generell zu vermeiden.
- Die richtige Reaktion auf eine Routine-Approval-Abfrage ist **nie**, Berechtigungen zu
  erweitern (insbesondere keine breiten Muster wie `git *` oder `git -C *`), sondern den Befehl
  in die einfache Form aus dem korrekten Arbeitsverzeichnis zu bringen.

Einzige Ausnahme: *innerhalb* eines Factory-Skripts, das ohnehin als ein einziger allowlisteter
Aufruf läuft, darf `git -C <worktree>` verwendet werden, um gezielt einen **anderen** Worktree
lesend zu prüfen — so verifiziert `create-finding-worktree.sh` den HEAD des gerade erzeugten
Worktrees. Für Befehle, die die Session selbst absetzt, gilt die Regel ausnahmslos.

## Der Default-Branch wird ermittelt, nie geraten

Die Vorlage ist übertragbar: der Default-Branch kann `main`, `master`, `trunk` oder anders heißen.
Die dokumentierte Konvention ist **`origin/<default-branch>`**, wobei `<default-branch>` vorher
deterministisch bestimmt wird — live vom Remote, nicht aus dem lokal gecachten (und
notorisch veraltenden) `refs/remotes/origin/HEAD`:

```
factory/scripts/create-finding-worktree.sh resolve
```

gibt genau dafür `DEFAULT_BRANCH <name>` und `BASE_SHA <sha>` aus. Alternativ liefert
`factory/scripts/gh-query.sh default-branch` die GitHub-Sicht derselben Information.

## Finding-Branches: immer `--no-track`, Basis vor dem ersten Schreiben prüfen

`.git/config` ist für die Sandbox nicht schreibbar. Das ist eine gewollte Grenze und wird **nicht**
gelockert. Ein Branch, dessen Startpunkt ein Remote-Tracking-Ref ist, richtet aber per Default
Upstream-Tracking ein (`branch.autoSetupMerge`) und schreibt dafür `branch.<name>.remote` und
`branch.<name>.merge` nach `.git/config`. Das scheitert an der Sandbox mit `could not lock config
file .git/config: Operation not permitted` und lässt die Branch-Erzeugung fehlschlagen.

Ein Finding-Branch braucht dieses Tracking nicht — gepusht wird ohnehin explizit mit
`git push origin <branch>`. Kanonisch sind deshalb vier einzelne, einfache Befehle aus dem
Repo-Verzeichnis:

```
git fetch origin
git switch --no-track -c <finding-branch> origin/<default-branch>
git rev-parse HEAD
git rev-parse origin/<default-branch>
```

Die beiden SHAs müssen **identisch** sein, bevor irgendetwas geschrieben wird. Bei Abweichung:
`AUTONOMY_BLOCKER: ...` melden und nicht weiterarbeiten.

Für Worktrees gilt dasselbe; dort setzt `factory/scripts/create-finding-worktree.sh` (siehe
unten) `--no-track` selbst und verifiziert die Basis, bevor es den Worktree freigibt. Beides ist
durch [`factory/guards/test_create_finding_worktree.py`](factory/guards/test_create_finding_worktree.py)
deterministisch abgesichert — inklusive des Falls, dass ein stale lokaler Branch bzw. ein
verwaister Remote-HEAD existiert und `.git/config` nicht schreibbar ist.

### Erwartete Sandbox-Meldungen, die **kein** `AUTONOMY_BLOCKER` sind

Zwei Meldungen erscheinen im Normalbetrieb, obwohl der Befehl erfolgreich ist. Beide sind Folge
derselben gewollten Sandbox-Grenzen und **kein** Grund, einen Lauf abzubrechen — maßgeblich ist
der Exit-Code und die tatsächliche Wirkung, nicht die Textausgabe:

- `fatal: failed to store: ...` bei `git fetch origin` und `git push origin <branch>`: der
  Credential-Helper darf den System-Schlüsselbund nicht beschreiben. Fetch und Push selbst laufen
  durch (Exit 0, Refs werden korrekt aktualisiert) — nachprüfbar mit
  `git rev-parse origin/<default-branch>`.
- `error: could not lock config file .git/config` zusammen mit `warning: update of config-file
  failed` beim **Löschen** eines Branches (`git branch -d` / `-D`): Git will den zugehörigen
  Config-Abschnitt mit entfernen und darf nicht. Der Branch wird trotzdem gelöscht
  (`Deleted branch ...`).

Der Unterschied zur Branch-**Erzeugung** oben ist wesentlich und der Grund, warum `--no-track`
dort zwingend ist: derselbe verweigerte Schreibzugriff lässt die Erzeugung **hart fehlschlagen**,
während er beim Löschen nur eine Warnung ist.

## Mehrere Findings: bewusst sequentiell (der unterstützte Ablauf)

**Factory v1 arbeitet ein Finding nach dem anderen**, im Hauptrepository, auf einem eigenen
Branch. Parallele Claude-Worktree-Sessions sind **nicht** Teil von v1. Das ist keine Vorliebe,
sondern die beobachtete Folge des Control-Plane-Schutzes.

### Der unterstützte Ablauf für normale P1-Arbeit

Das ist der vollständige, geprüfte Weg — es gibt keinen zweiten:

```
git fetch origin
git switch --no-track -c fix/<ID> origin/<default-branch>
git rev-parse HEAD
git rev-parse origin/<default-branch>
```

Die beiden SHAs müssen identisch sein, bevor irgendetwas geschrieben wird (bei Abweichung:
`AUTONOMY_BLOCKER`). Danach im **Hauptverzeichnis** arbeiten und den Finding über den
[`verify-finding`-Skill](.claude/skills/verify-finding/SKILL.md) bis `CLOSED` und Merge führen.
Erst wenn dieses Finding gemergt ist, beginnt das nächste.

Kommen mehrere Findings gleichzeitig herein, werden sie **nacheinander** abgearbeitet, nicht
gleichzeitig. Ist eines blockiert (`EXPERT_REVIEW_REQUIRED`, `P0`, Governance-Entscheidung), wird
sein Branch stehen gelassen und das nächste Finding von `origin/<default-branch>` aus begonnen —
sequentiell heißt nicht, dass ein blockiertes Finding alles andere aufhält.

### Parallelität ist als v1.x-Fähigkeit vorgemerkt

Sie ist **nicht** verworfen, sondern zurückgestellt, bis sie belegbar ist. Der Weg dorthin führt
ausdrücklich **nicht** über eine Lockerung von `permissions.deny`, `sandbox.filesystem.denyWrite`
oder des Control-Plane-Schutzes — das wäre der Tausch einer bewiesenen Sicherheitsgrenze gegen
eine unbewiesene Bequemlichkeit. Eine spätere v1.x müsste die Inkompatibilität an ihrer Wurzel
lösen (etwa indem der Worktree ohne Schreibzugriff auf die Kontrollebene entsteht) und danach die
Beobachtung unten erneut erheben.
[`factory/guards/test_worktree_protection.py`](factory/guards/test_worktree_protection.py) zeigt
an, wenn sich die Umgebung geändert hat.

Frühere Fassungen dieses Abschnitts beschrieben Worktrees als verfügbaren Modus für „echt
gleichzeitige" Arbeit. Der Audit hat nicht behauptet, dass das kaputt sei — er hat festgestellt,
dass es **unbewiesen** war. Also wurde es geprüft, im echten Repository, mit dem kanonischen
Mechanismus der Factory:

```
$ factory/scripts/create-finding-worktree.sh create <BASE_SHA> .claude/worktrees/F15-PROBE fix/F15-PROBE
Preparing worktree (new branch 'fix/F15-PROBE')
error: unable to create file .claude/agents/finding-closure-reviewer.md: Operation not permitted
fatal: Could not reset index file to revision 'HEAD'.
```

Mit einem Ziel an anderer Stelle **innerhalb** des Repositories wiederholt, identisches Ergebnis.
Einen Worktree auszuchecken heißt, jede getrackte Datei zu schreiben, und die Kontrollebene
(`.claude/agents/**`, `.claude/hooks/**`, `factory/guards/**`, …) ist genau das, was die Sandbox
diesem Agenten verweigert.

**Der zweite Befund liegt eine Ebene tiefer.** Die `denyWrite`-Regeln einer laufenden
Claude-Code-Session sind an **deren aktuelle Projektwurzel** gebunden (`./factory/guards`,
`./.claude/agents`, …). Für Pfade außerhalb dieser Wurzel greifen sie nicht — positiv beobachtet,
nicht angenommen:

```
$ touch "$TMPDIR/f15-scope-probe/factory/guards/validate-finding.py"
AUSSERHALB DES REPOS: factory/guards BESCHREIBBAR
$ touch "$TMPDIR/f15-scope-probe/.claude/agents/x.md"
AUSSERHALB DES REPOS: .claude/agents BESCHREIBBAR
```

Ein Worktree **außerhalb** der Projektwurzel lässt sich deshalb anlegen — und ist **aus dieser
Session heraus** nicht durch deren Pfadgrenzen geschützt. Diese Session könnte dort jeden Guard
umschreiben, der sie beurteilt, und das Ergebnis in den Branch committen. Daraus folgt die
verbindliche Regel: **eine laufende Factory-v1-Session erzeugt keinen externen Worktree und
arbeitet nicht darin weiter.**

**Was hier ausdrücklich NICHT behauptet wird:** dass eine *neu gestartete* Claude-Code-Session,
deren eigene Projektwurzel dieser Worktree ist, keinen Schutz hätte. Das wurde nicht getestet, und
eine ungeprüfte Aussage darüber wäre genau der Fehler, den dieses Paket beseitigt. Für Factory v1
ist die Frage ohne Belang: v1 ist bewusst sequentiell und unterstützt Worktree-Parallelität nicht,
also wird sie nicht untersucht.

Drittens lässt sich ein einmal angelegter externer Worktree aus der erzeugenden Session **nicht
mehr aufräumen**: `git worktree prune` scheitert mit `failed to delete '.git/worktrees/...':
Operation not permitted`, weil `.git/` ebenfalls geschützt ist. Ein solcher Eintrag bleibt stehen.

Hier funktioniert nichts falsch — die Sandbox tut genau das, wofür sie da ist, und ihre
Wurzelbindung ist normal. Falsch war die Dokumentation, die einen Modus versprach, dessen
Sicherheitsannahmen nie geprüft worden waren.

Daraus folgt für die Praxis:

- Ein Finding zur Zeit, im Hauptverzeichnis, auf `factory-change/<name>` bzw. `fix/<ID>`.
- `create-finding-worktree.sh create` **blockiert diesen Fall aktiv, bevor** es `git worktree add`
  überhaupt versucht: es prüft mit einer Schreibprobe auf `.claude/agents/`, ob die Kontrollebene
  beschreibbar ist, und beendet sich bei Verweigerung sofort mit `SANDBOX_WORKTREE_INCOMPATIBLE`
  (Exit 4). So bleibt kein halb erzeugter Worktree und kein verwaister Branch zurück, und der
  Zustand sieht nicht wie eine vorübergehende Störung aus.
- **Niemals `git worktree add` von Hand mit einem Ziel außerhalb der Projektwurzel.** Genau dort
  funktioniert es — und aus der erzeugenden Session heraus ohne deren Control-Plane-Grenzen. Das
  Skript blockiert vorher; wer es umgeht, umgeht die Kontrollebene dieser Session.
- Die Fragen, die F-15 zum Worktree gestellt hat — ist `<worktree>/factory/reviews/` geschützt,
  wohin schreibt der `SubagentStop`-Hook, welche Projektwurzel gilt, wie ist der Scope-Hash
  zugeordnet — bleiben für v1 **offen und ohne Belang**: innerhalb der Projektwurzel entsteht kein
  Worktree, in dem man sie stellen könnte, und außerhalb arbeitet v1 grundsätzlich nicht weiter.
  Einen Worktree ohne Prüfung als „sicher" zu bezeichnen wäre genau die unbewiesene Zusicherung,
  die dieses Paket beseitigt.
- [`factory/guards/test_worktree_protection.py`](factory/guards/test_worktree_protection.py) hält
  die Beobachtung fest und schlägt fehl, wenn irgendein Dokument die Parallelitätsbehauptung
  wieder einführt.

Sollte eine spätere Version parallele Findings unterstützen wollen, ist der Weg nicht, den Schutz
zu lockern, sondern die Beobachtung neu zu erheben — der Test oben zeigt an, wenn sich die
Umgebung geändert hat.

### Der Worktree-Mechanismus selbst bleibt korrekt

Die folgenden Regeln gelten unverändert für den Fall, dass Worktrees in einer anderen Umgebung
(z. B. ohne aktive Sandbox) verwendet werden. Sie sind der Grund, warum der Mechanismus nicht
entfernt, sondern nur als nicht-verfügbar dokumentiert wird.

**Worktree-Basis: immer explizit `origin/<default-branch>`, nie EnterWorktrees impliziten
"fresh"-Default.** EnterWorktrees `fresh`-Basis-Modus (harness-seitiger Default) löst "den
Default-Branch" über den lokal gecachten Symref `refs/remotes/origin/HEAD` auf. `git fetch origin`
aktualisiert diesen Symref **nicht** — nur ein expliziter `git remote set-head` tut das. Ist er
verwaist (real beobachtet: er zeigte auf einen alten, bereits gemergten Feature-Branch), entsteht
ein neuer Finding-Worktree still von einem veralteten Commit. EnterWorktree selbst bietet keinen
Parameter für einen expliziten Basis-Ref/SHA.

Deshalb für jeden Finding-Worktree zwingend zweistufig über
[`factory/scripts/create-finding-worktree.sh`](factory/scripts/create-finding-worktree.sh) gehen,
statt `EnterWorktree` direkt einen neuen Worktree anlegen zu lassen:

```
factory/scripts/create-finding-worktree.sh resolve
factory/scripts/create-finding-worktree.sh create <BASE_SHA-aus-resolve> .claude/worktrees/<ID> fix/<ID>
```

Das sind zwei getrennte, einfache Befehle: den von `resolve` ausgegebenen `BASE_SHA` ablesen und
im zweiten Aufruf wörtlich einsetzen — keine Command-Substitution, keine Subshell (siehe
"Git-Routine" oben).

Das Skript fragt den Remote nach seinem Default-Branch, fetcht `origin`, bestimmt den erwarteten
Basis-SHA explizit, legt den Worktree direkt von diesem Ref an (mit `--no-track`) und vergleicht
unmittelbar danach — vor jeder weiteren Schreiboperation — den tatsächlichen Worktree-HEAD gegen
den erwarteten SHA. Bei Abweichung wird der Worktree sofort verworfen, `AUTONOMY_BLOCKER: ...`
ausgegeben und nicht weitergearbeitet. Erst nach einem erfolgreichen `create` (Exit 0,
`WORKTREE_READY ...`) den Worktree über `EnterWorktree` mit `path: .claude/worktrees/<ID>`
betreten — niemals über `EnterWorktree`s `name`-Parameter, der wieder den impliziten,
symref-abhängigen `fresh`-Default verwenden würde.

## GitHub, PR, CI und Merge: feste Helfer statt ad-hoc-Konstruktionen

`gh` wird **nicht** vorausgesetzt und muss nicht installiert werden. Der gesamte GitHub-Zugriff
läuft über zwei Skripte, die je als ein einziger, statisch erkennbarer Befehl laufen:

- [`factory/scripts/gh-api.sh`](factory/scripts/gh-api.sh) — minimaler REST-Zugriff. Er nimmt das
  Credential aus dem git-credential-Helper (repo-spezifisch, inklusive `path` aus der
  origin-URL) und zielt immer auf das Repository, auf das `origin` zeigt. Kein Token in einer
  Datei, kein Token in der Ausgabe.
- [`factory/scripts/gh-query.sh`](factory/scripts/gh-query.sh) — feste Unterbefehle für die
  Routine: `repo`, `default-branch`, `pr`, `pr-summary`, `pr-create`, `check-runs`,
  `check-runs-summary`, `required-check`, `actions-run`, `actions-run-summary`, `actions-jobs`,
  `actions-jobs-summary`, `branch-rules`, `required-checks`, `merge`.

Die `-summary`-Unterbefehle existieren genau deshalb, damit für eine Routineabfrage **kein**
inline `python3 -c`, keine Pipeline und keine Zwischen-JSON-Datei nötig ist: Jeder liefert direkt
`key: value`-Zeilen auf stdout. Wer eine Routineabfrage per Pipeline oder Temp-Datei nachbaut,
erzeugt genau die Approval-Abfrage, die diese Skripte vermeiden.

**Die Merge-Entscheidung wird nicht aus Prosa gelesen.** Dafür gibt es zwei feste Regeln:

- `factory/scripts/gh-query.sh required-check <SHA> [NAME]` liefert **genau ein** Urteil
  (`success`, `failed`, `pending`, `absent`, `api_error`) und einen eindeutigen Exit-Code
  (`0/1/2/3/4`). Nur Exit 0 darf zu einem Merge führen. `absent` ist kein Erfolg: "der Check ist
  nicht da" ist nicht "der Check ist grün".
- `factory/scripts/gh-query.sh merge <PR> <METHOD> <ERWARTETER-HEAD-SHA>` verlangt den Head-SHA,
  für den CI-Evidence und Review tatsächlich vorliegen. Er wird lokal geprüft und zusätzlich an
  die GitHub-Merge-API übergeben, sodass ein zwischenzeitlich eingetroffener Push den Merge
  serverseitig scheitern lässt statt mitzureisen.

Ein API-Fehler (401, 403, 404, 422, 429, 5xx, Netzwerk) ist **niemals** ein leerer Normalzustand:
alle Helfer melden `api_error:` und enden mit einem Exit-Code ungleich 0.

### Der Merge kann eine menschliche Bestätigung verlangen — das ist eine Plattformgrenze

Beim Abschluss von `FACTORY-TRUST-CORE-1` wurde der kanonische Befehl

```
factory/scripts/gh-query.sh merge <PR> squash <ERWARTETER-HEAD-SHA>
```

vom Auto-Mode-Klassifikator von Claude Code abgelehnt, obwohl er bereits die vorgesehene
einfache, allowlistete Form hatte. Die Analyse dazu, mit dem, was in derselben Sitzung
beobachtbar war:

- **Es lag nicht an der Schreibweise und nicht an der Allowlist.** Jeder andere Unterbefehl
  desselben Skripts — `pr-summary`, `required-check`, `check-runs-summary`, `default-branch`,
  `actions-run-summary` — lief in derselben Sitzung ohne jede Rückfrage durch, gedeckt von
  demselben Präfixmuster `Bash(factory/scripts/gh-query.sh *)`. Blockiert wurde ausschließlich
  `merge`.
- **Der Klassifikator urteilt also über die Wirkung, nicht über die Form.** Ein Merge auf einen
  geschützten Default-Branch ist die einzige nach außen wirkende, praktisch irreversible Aktion
  der gesamten Pipeline. Dass eine Plattformschicht dafür eine menschliche Bestätigung will, ist
  nachvollziehbar.
- **Repo-lokal ist das nicht sauber vermeidbar.** Es gäbe nur unzulässige Wege: breite
  `Bash`-/`git`-/`curl`-/`python3`-Freigaben, eine Lockerung der Sandbox, Eingriffe in globale
  Claude-Einstellungen oder ein selbstgebauter Merge-Pfad an `gh-query.sh merge` vorbei. Jeder
  davon würde genau die Kontrolle entfernen, deretwegen der Merge-Gate existiert. Deshalb wird
  keiner davon gebaut.

**Konsequenz für den Betrieb:** Der Merge ist der eine Routineschritt, der eine menschliche
Bestätigung erfordern kann. Die Factory umgeht das nicht, sondern hält davor sauber an und nennt
den exakten Befehl inklusive erwartetem Head-SHA. Was das Risiko begrenzt, ist bereits gebaut:
der Merge ist per F-08 an genau diesen SHA gebunden — der Mensch bestätigt damit exakt den
reviewten Stand, und ein zwischenzeitlich eingetroffener Push lässt den Merge serverseitig
scheitern statt mitzureisen.

Verbindlich ist der **Required Status Check** auf dem geschützten Default-Branch (Job `factory-checks`
aus [`.github/workflows/factory-ci.yml`](.github/workflows/factory-ci.yml)). Ein roter CI-Lauf
wird repariert, nicht umgangen; ein abgelehnter Merge wird gemeldet, nicht erzwungen. Nach dem
Merge wird der tatsächliche Remote-Stand verifiziert (`git fetch origin` +
`git rev-parse origin/<default-branch>`), nicht angenommen.
