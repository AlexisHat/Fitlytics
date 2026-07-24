# Designentscheidungen

## Meilenstein 1: Projektgerüst

### Ruff-Regelumfang und Google-Style-Docstrings

**Entscheidung:** Es werden die Ruff-Regeln `E`, `F`, `I`, `UP`, `B`, `N` und `D` verwendet. Für Docstrings gilt die Google-Konvention; die `D`-Regeln werden nur auf `src/` angewendet.

**Begründung:** So werden Stil- und Dokumentationsfehler bereits beim Schreiben erkannt, während Testdateien von unnötigen Docstring-Anforderungen ausgenommen bleiben.

---

### `pytest`-Exit-Code 5 im pre-commit-Hook

**Entscheidung:** Der Exit-Code 5 (`No tests collected`) wird im pre-commit-Hook als erfolgreicher Lauf behandelt.

**Begründung:** Dadurch schlägt der Hook in frühen Projektphasen ohne Tests nicht unnötig fehl, während echte Testfehler weiterhin erkannt werden.

---

### Design by Contract mit `deal`

**Entscheidung:** Für Verträge werden `deal lint` und `deal test` verwendet und als pre-commit-Hooks ausgeführt.

**Begründung:** Dadurch werden Vertragsverletzungen sowohl statisch als auch durch automatisch generierte Tests frühzeitig erkannt.

---

### Hypothesis mit CrossHair-Backend

**Entscheidung:** Für ausgewählte Property-Based-Tests wird bei Bedarf das CrossHair-Backend (`hypothesis-crosshair`) eingesetzt.

**Begründung:** Die symbolische Analyse findet Gegenbeispiele zuverlässiger als reines Zufallssampling und eignet sich besonders für Funktionen mit vielen Randbedingungen.

---

## Meilenstein 2: Datenmodelle

### Datenexploration in einem Jupyter-Notebook

**Entscheidung:** Die Rohdaten (FIT, `physiologische_zyklen.csv`) werden in `notebooks/datenexploration.ipynb` mit ausgeführten Zellen exploriert; Notebooks sind von ruff und den Whitespace-Hooks ausgenommen.

---

### Paketstruktur: Subpackages je Fachkonzern statt Wrapper-Package

**Entscheidung:** Code liegt direkt unter `src/` als ein Package je Fachkonzern (`src/models/`, `src/errors/`, künftig `src/readers/` usw.), ohne . `tests/` spiegelt dieselbe Struktur.

**Begründung:** Klarere Trennung nach Verantwortlichkeit, kürzere Imports (`from models import Workout` statt
`from fitlytics.models import Workout`). Finde ich persönlich deutlich übersichtlicher

---

### Beispiel-FIT-Datei erstellen lassen

**Entscheidung:** `data/beispiel/training_gueltig.fit` wurde durch ein von der ki geschriebendes skript erstellt, da ich nur große .fit datein zur verfügung habe und diese zu lange brauchen würden, wenn man jedes mal den import test laufen lassen würde.

---

### mypy-Override für `fitdecode`

**Entscheidung:** `[[tool.mypy.overrides]]` mit `module = "fitdecode.*"` und `ignore_missing_imports = true` ergänzt.

**Begründung:** `fitdecode` liefert keine Typstubs also ohne Override meldet `mypy --strict` bei jedem Import einen `import-untyped`-Fehler.

---
