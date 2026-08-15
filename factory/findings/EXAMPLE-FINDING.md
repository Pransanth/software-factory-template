# EXAMPLE-FINDING

Status: OPEN

## Befund

**Dies ist ausdrücklich ein Formatbeispiel, kein echter Befund.** Es existiert, damit in einer
frischen Kopie der Vorlage sichtbar ist, wie eine Finding-Datei aufgebaut sein muss, und damit
der kanonische Runner (`python3 factory/guards/run-factory-checks.py`) gegen eine reale Datei
läuft. In einem echten Projekt wird diese Datei durch die tatsächlichen Findings ersetzt oder
gelöscht — sie beschreibt bewusst kein konkretes Produkt und keine konkrete Schwachstelle.

Ein echter Befund steht hier in einfachen Worten: was beobachtet wurde, wo, und was im
schlimmsten Fall passieren kann. Bekannt oder unbekannt, ob es bereits ausgenutzt wurde, gehört
ebenfalls hierher.

## Analyse

Root Cause: Not yet analyzed
Affected Components: Not yet analyzed
Relevant Architecture: Not yet analyzed
Recommended Repair: Not yet analyzed
Regression Test Plan: Not yet analyzed
Central Guard Plan: Not yet analyzed
Expected Blast Radius: Not yet analyzed
Risk Assessment: Not yet analyzed
Expert Review Reason: Not yet analyzed
What Is Known: Not yet analyzed
What Remains Uncertain: Not yet analyzed
What An Expert Would Need To Review: Not yet analyzed

## Hinweise zum Format

- `Status:` ist der einzige Zustandsträger; erlaubte Werte und ihre Pflichtfelder stehen in
  [`.claude/rules/factory-workflow.md`](../../.claude/rules/factory-workflow.md).
- Bei `OPEN` dürfen die Analysefelder `Not yet analyzed` bleiben. Ab `ANALYZED` müssen die acht
  Analysefelder echt gefüllt sein, für `READY_FOR_CLOSURE`/`CLOSED` zusätzlich
  `Verification Evidence`, `CI Evidence` und `Review Artifact`.
- Ein Feld pro Zeile, `Feldname: Wert`. Platzhalter wie `TBD`, `TODO`, `N/A` gelten dem Guard
  nicht als ausgefüllt.
