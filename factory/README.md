# Factory – kurze technische Einführung

Diese Datei erklärt in einfachen Worten, was die Bausteine in diesem Verzeichnis tun und wie sie
zusammenhängen. Für die genauen Zustandsregeln siehe
[`.claude/rules/factory-workflow.md`](../.claude/rules/factory-workflow.md).

## Was ist ein Finding?

Ein Finding ist eine einzelne Markdown-Datei unter `factory/findings/`, z. B.
[`P1-DEMO-1.md`](findings/P1-DEMO-1.md). Sie beschreibt einen Befund (aktuell nur
Sicherheitsbefunde) und trägt einen Status (`OPEN`, `ANALYZED`, ... siehe Workflow-Regeln). Je
nach Status müssen bestimmte Analysefelder ausgefüllt sein.

## Was ist ein Validator?

Ein Validator ist ein kleines, deterministisches Skript, das eine einzelne Finding-Datei gegen
die Regeln für ihren Status prüft — ohne KI, ohne Netzwerk, rein regelbasiert. Der aktuelle
Validator ist [`factory/guards/validate-finding.py`](guards/validate-finding.py):

```
python3 factory/guards/validate-finding.py factory/findings/P1-DEMO-1.md
```

Exit 0 = das Finding ist für seinen Status gültig, Exit 1 = ungültig (mit Fehlerliste). Er prüft
genau eine Datei und weiß nichts von anderen Findings oder davon, wer ihn aufruft.

## Was ist der gemeinsame Factory-Runner?

[`factory/guards/run-factory-checks.py`](guards/run-factory-checks.py) ist der **eine
kanonische Einstiegspunkt** für "sind alle Factory-Prüfungen aktuell grün?". Er findet alle
Finding-Dateien unter `factory/findings/`, lässt jede einzelne vom Validator prüfen, und liefert
ein Gesamtergebnis:

```
python3 factory/guards/run-factory-checks.py
```

Exit 0 = alle Checks bestanden, Exit 1 = mindestens einer fehlgeschlagen — mit einer klaren
Auflistung, welcher Check bei welcher Datei fehlgeschlagen ist. Heute gibt es nur eine Art Check
(Finding-Validierung); künftige Checks würden ebenfalls von hier aus laufen, statt an mehreren
Stellen eigene Prüflogik zu duplizieren.

## Was macht der Stop-Hook?

[`.claude/hooks/stop-validate-findings.py`](../.claude/hooks/stop-validate-findings.py) ist ein
Claude-Code-Stop-Hook: Er wird automatisch aufgerufen, wenn Claude versucht, eine Aufgabe in
diesem Repository zu beenden. Er enthält **keine eigene Prüflogik** — er ruft ausschließlich den
gemeinsamen Runner (`run-factory-checks.py`) auf und übersetzt dessen Ergebnis in das, was
Claude Code von einem Stop-Hook erwartet: bei Erfolg darf Claude stoppen, bei einem
fehlgeschlagenen Check wird der Stopp blockiert und Claude bekommt die Fehlermeldung als Grund
mitgeteilt.

## Was kann der Stop-Hook ausdrücklich NICHT garantieren?

Der Stop-Hook ist ein **lokaler Workflow-Guard**, **kein finales Security- oder Merge-Gate**.
Insbesondere:

- Er läuft nur, wenn Claude Code selbst versucht zu stoppen — er prüft nichts, wenn Dateien auf
  anderem Weg geändert werden (manuell, durch ein anderes Tool, durch ein Skript).
- Er behandelt einen wiederholten Stopp-Versuch (`stop_hook_active: true`) **nicht** als Beweis,
  dass ein Finding jetzt gültig ist — er prüft bei jedem einzelnen Versuch erneut den echten
  Zustand und blockiert konsequent weiter, solange etwas tatsächlich ungültig ist.
  Genau deshalb ist er **kein** eigenständiger Schutz vor einer Endlosschleife: Diese
  Garantie liefert Claude Code selbst, nicht dieses Skript. Laut offizieller Dokumentation
  überschreibt Claude Code einen Stop-Hook, nachdem er ohne erkennbaren Fortschritt acht Mal in
  Folge blockiert hat, beendet den Turn trotzdem und zeigt dabei eine Warnung, dass der Stop-Hook
  zu oft in Folge blockiert hat. Dieser Cap ist über die Umgebungsvariable
  `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` konfigurierbar. Das ist die eigentliche technische Grenze:
  Nach genügend Versuchen kann ein weiterhin ungültiger Zustand den Stopp trotzdem nicht mehr
  verhindern — der Stop-Hook allein kann einen ungültigen Zustand also **nicht absolut**
  ausschließen.
- Er läuft mit den Rechten des lokalen Nutzers und lässt sich durch Konfiguration umgehen oder
  deaktivieren (z. B. Hooks überspringen, Einstellungen ändern). Ein Nutzer mit
  Schreibzugriff auf `.claude/settings.json` kann ihn jederzeit abschalten.
- Er prüft nur formale Vollständigkeit der Finding-Felder, nicht deren inhaltliche Richtigkeit.

Ein wirklich verlässliches Gate — z. B. bevor Code in einen geschützten Branch gelangt — braucht
eine serverseitige Prüfung (CI), die nicht vom lokalen Rechner oder von Claude Code selbst
abhängt. Diese Schicht gibt es jetzt: siehe "Die Prüfkette: lokal bis CI" weiter unten. (Ein
Branch-Schutz, der einen fehlgeschlagenen CI-Lauf tatsächlich verbindlich macht, ist noch nicht
konfiguriert — CI prüft aktuell, blockiert aber noch keinen Merge.)

## Shared vs. local Claude settings

Dieses Repo hat zwei getrennte Claude-Code-Einstellungsdateien mit bewusst unterschiedlichem
Zweck:

- **`.claude/settings.json`** ist die **übertragbare, versionierte Factory-Konfiguration**. Sie
  gehört zur Vorlage selbst: der Stop-Hook und generische Demo-Schutzregeln (aktuell
  `Bash(docker *)`, `Bash(git push *)`, `Bash(gh *)` verboten), die für jede Kopie dieses Repos
  gleichermaßen sinnvoll sind. Diese Datei wird committet.
- **`.claude/settings.local.json`** ist **persönlich/maschinenspezifisch** und **niemals Teil der
  Factory-Vorlage**. Hier stehen Regeln, die nur auf dem konkreten Rechner der jeweiligen Person
  Sinn ergeben — zum Beispiel absolute Pfade zu anderen, lokalen Projekten auf derselben
  Maschine (in diesem Fall: die Isolation gegenüber einem anderen lokalen Projekt namens
  ein anderes lokales Projekt). Diese Datei wird **nicht** committet (siehe `.gitignore`).

Faustregel: **Absolute Pfade zu irgendetwas außerhalb dieses Repos gehören ausschließlich in
`settings.local.json`.** Wird dieses Repo als Vorlage für ein echtes Projekt kopiert, kann
`settings.json` unverändert mitgenommen werden — `settings.local.json` dagegen ist per Definition
für jede Maschine neu und individuell einzurichten (oder wegzulassen).

## Die Prüfkette: lokal bis CI

Es gibt vier Schichten, aber nur **eine** Prüflogik — jede Schicht ruft nur die davor auf,
niemand implementiert die Regeln ein zweites Mal:

```
lokaler Validator            factory/guards/validate-finding.py     (prueft 1 Finding)
        ↓
gemeinsamer Factory-Runner   factory/guards/run-factory-checks.py   (prueft alle Findings)
        ↓
Claude Stop-Hook             .claude/hooks/stop-validate-findings.py (ruft den Runner beim Stop-Versuch auf)
        ↓
GitHub CI                    .github/workflows/factory-ci.yml        (ruft denselben Runner-Befehl in GitHub Actions auf)
```

Der Stop-Hook hilft **Claude**, lokal innerhalb einer laufenden Session korrekt zu arbeiten — er
ist an das Claude-Code-Stop-Ereignis gekoppelt und hat, wie oben beschrieben, eine dokumentierte
technische Grenze (der 8-Block-Cap).

**Die GitHub-CI (`factory-ci.yml`) ist davon komplett unabhängig.** Sie kennt keine Claude-Session,
keinen Stop-Hook und kein `stop_hook_active` — sie checkt bei jedem Push auf `main` und bei jedem
Pull Request gegen `main` den Repository-Zustand frisch aus und lässt exakt denselben Befehl
laufen, den auch der Stop-Hook und jeder Entwickler lokal ausführen können:

```
python3 factory/guards/run-factory-checks.py
```

Damit prüft CI **denselben Zustand ein zweites Mal, unabhängig davon, ob oder wie der Stop-Hook
lokal reagiert hat** — auf einem frischen GitHub-Actions-Runner, ohne Secrets, ohne Schreibrechte,
ohne Docker, ohne Claude-/Anthropic-API. Das ist die Absicherung dafür, dass "lokal grün" (oder
"vom Stop-Hook durchgelassen") tatsächlich auch "in CI grün" bedeutet — unabhängig davon, ob der
lokale Rechner, die Claude-Session oder der Stop-Hook selbst kompromittiert, deaktiviert oder
falsch konfiguriert wäre.
