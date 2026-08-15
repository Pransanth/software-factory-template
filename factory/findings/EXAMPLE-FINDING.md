# EXAMPLE-FINDING

Status: OPEN
Severity: P2

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
- `Severity:` ist ab `ANALYZED` Pflicht und einer von `P0`, `P1`, `P2`, `P3`. Ein `P0` darf
  ausschließlich `OPEN`, `ANALYZED` oder `EXPERT_REVIEW_REQUIRED` erreichen — der Guard lehnt
  jeden weiteren Status ab.
- Bei `OPEN` dürfen die Analysefelder `Not yet analyzed` bleiben. Ab `ANALYZED` müssen die acht
  Analysefelder echt gefüllt sein, für `READY_FOR_CLOSURE`/`CLOSED` zusätzlich
  `Verification Evidence`, `CI Evidence` und `Review Artifact`.
- `Review Artifact` muss exakt `factory/reviews/<Finding-ID>.round-<N>.md` sein — das eigene,
  neueste Review-Artefakt dieses Findings. Fremde Pfade, andere Findings und ältere Runden
  werden abgelehnt.
- Ein Feld pro Zeile, `Feldname: Wert`. Platzhalter wie `TBD`, `TODO`, `N/A` gelten dem Guard
  nicht als ausgefüllt.
