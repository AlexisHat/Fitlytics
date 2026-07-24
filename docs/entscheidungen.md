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

### FIT-Import: Fehlerbehandlung an der Systemgrenze

**Entscheidung:** `import_fit_file` fängt alle `fitdecode`-Exceptions und `OSError` und wirft sie als `FileImportError` neu; verlangt genau eine `session`-Message; eine leere `records`-Liste (Pydantic-Fehler) wird ebenfalls als `FileImportError` neu geworfen statt roh durchgereicht.

**Begründung:** Einheitliche Fehlerart an der Modulgrenze keine Nutzereingabe (kaputte/leere Datei, Datei ohne Session) soll die Anwendung zum Absturz bringen.

---

### FIT-Import: pfad- und stream-fähige Schnittstelle

**Entscheidung:** `import_fit_file(source: str | Path | IO[bytes])` reicht `source` unverändert an `fitdecode.FitReader` durch, das selbst zwischen Pfad, datei-artigem Objekt und rohen Bytes unterscheidet.

**Begründung:** Dieselbe Funktion funktioniert unverändert mit einem Testpfad (`data/beispiel/...`) und später mit `st.file_uploader()`s `UploadedFile` (Subklasse von `io.BytesIO`) — keine separate Wrapper-Logik nötig.

---
