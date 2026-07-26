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

### Whoop-Zeitzonenformat: `"UTCZ"` als Sonderfall

**Entscheidung:** Die Spalte „Zeitzone des Zyklus" hat drei reale Werte: `UTC+02:00`, `UTC+01:00` und `UTCZ`. `_parse_utc_offset` behandelt `"UTCZ"` explizit als Sonderfall statt es als `UTC±HH:MM` zu parsen.

**Begründung:** Beim Prüfen der echten CSV festgestellt

---

### Whoop-Import: lokales Datum vs. UTC-Zeitstempel

**Entscheidung:** `RecoveryDay.date` bleibt das lokale Kalenderdatum aus der CSV, `cycle_start` ist dieselbe Zeit nach UTC konvertiert.

*(In Meilenstein 5 revidiert, siehe „Whoop-Tagesbezug: Mittag-zu-Mittag".)*

---

## Meilenstein 5: Validierung und Vereinheitlichung

### UTC-Prüfung als Annotated-Typ im Modell

**Entscheidung:** `UtcDatetime` in `src/models/types.py` lehnt naive Zeitstempel ab und rechnet aware-Werte verlustfrei nach UTC um. Alle Zeitfelder der Modelle nutzen diesen Typ.

**Begründung:** Timezone-Awareness ist eine strukturelle Eigenschaft des Typs, kein Prüfschritt — es gibt keinen gültigen `Workout` mit naivem Zeitstempel. Im Modell gilt sie auf jedem Konstruktionsweg, auch beim Rücklesen aus SQLite. Ein nachgelagerter Schritt könnte das nicht zusichern, weil das Objekt zwischen Konstruktion und Prüfung ungültig existierte. Naive Werte werden abgelehnt statt als UTC angenommen: Raten würde jeden Zeitstempel eines anders konfigurierten Geräts still um Stunden verschieben.

---

### Definitorische Grenzen im Modell, physiologische in der Validierung

**Entscheidung:** Was aus der Größe selbst folgt (Prozent 0–100, Distanz/Leistung nicht negativ), steht als Pydantic-Constraint im Modell. Was nur unwahrscheinlich ist (HF 20–240, HRV ≤ 300 ms, Hauttemperatur 20–45 °C), steht als benannte Konstante in `src/validation/ranges.py`.

**Begründung:** Die beiden Fälle haben verschiedene Konsequenzen. Ein Prozentwert von 120 macht den Datensatz ungültig; eine HF von 250 ist ein Sensorartefakt in einem sonst brauchbaren Datensatz. Nur die erste Klasse darf die Konstruktion verhindern. Die Grenzen sind bewusst großzügig — sie sollen Aussetzer fangen, nicht den Sportler bewerten.

---

### Null ist ein Messwert, kein Fehlwert

**Entscheidung:** Bei `power`, `cadence` und `speed_ms` ist 0 gültig und wird nicht verworfen. Bei `heart_rate` liegt die Untergrenze bei 20, eine 0 wird also verworfen.

**Begründung:** In der echten Trainingsdatei stehen 667 Nullwerte bei der Leistung und 571 bei der Trittfrequenz — das ist Rollenlassen, kein Defekt. Eine Herzfrequenz von 0 gibt es dagegen nicht; sie bedeutet, dass der Brustgurt den Kontakt verloren hat.

---

### Wertebereichsverstoß: Einzelwert verwerfen statt Einheit ablehnen

**Entscheidung:** Ein unplausibler Messwert wird auf `None` gesetzt, der Record bleibt erhalten. Gezählt wird das im `ValidationReport`, den die Oberfläche anzeigt. Verworfene Alternative: die ganze Einheit als `DataValidationError` ablehnen.

**Begründung:** Ein Ausreißer unter 4972 Records darf keine zweistündige Ausfahrt kosten, und der Record selbst trägt den Zeitstempel, auf dem jede spätere Zeitreihe beruht. Damit das kein stiller Fallback ist, wird jeder verworfene Wert gezählt und sichtbar gemacht — sonst würde sich die Durchschnitts-HF klammheimlich verbessern.

---

### Validierung als eigene Stufe nach dem Import

**Entscheidung:** `src/validation/` mit `validate_workout` und `validate_recovery_days`, die `(Daten, ValidationReport)` zurückgeben. Die Reader aus M3/M4 bleiben unverändert. Verworfene Alternative: Validierung in die Reader integrieren.

**Begründung:** Die Reader bedeuten weiterhin „Datei originalgetreu einlesen". Als eigene Stufe prüft derselbe Code auch Daten, die aus der Datenbank zurückkommen, und lässt sich ohne Beispieldatei testen.

---

### Whoop-Tagesbezug: Mittag-zu-Mittag

**Entscheidung:** `RecoveryDay.date` ist das lokale Datum von `Startzeit + 12 h` statt das Startdatum selbst.

**Begründung:** Ein Whoop-Zyklus ist kein Kalendertag — er umfasst einen Schlaf plus den folgenden Wachtag. In den echten Daten (344 Zyklen) beginnen 327 nach Mitternacht, 14 aber davor. Bei diesen 14 fiel der Start auf den Vortag und kollidierte mit dem Zyklus, der am selben Datum nach Mitternacht begann: 12 doppelte Kalenderdaten. Die Verschiebung um 12 Stunden ordnet jeden Zyklus dem Tag zu, in dem sein Mittag liegt. Sie löst alle 12 Duplikate, ist stabil im Bereich +10 h bis +14 h (also nicht an diesen Datensatz überangepasst) und lässt 327 der 344 Zeilen unverändert. Erst dadurch wird `date` eindeutig — und ein Duplikat zu einem aussagekräftigen `DataValidationError`. Ohne die Korrektur würde ein Workout mit der Recovery des falschen Tages verrechnet.

---

### `deal test` ist kein Prüfkriterium

**Entscheidung:** `deal test` bleibt als pre-commit-Hook bestehen, zählt aber nicht mehr zu den harten Anforderungen. Die Verträge werden durch `deal lint` und eigene Property-Tests abgesichert.

**Begründung:** `deal test` generiert Testfälle ausschließlich für `@deal.pure`-Funktionen und überspringt alle anderen stillschweigend mit Exit-Code 0 — eine absichtlich verletzte Postcondition blieb im Test unentdeckt. Die leere Ausgabe bedeutet „nichts getestet", nicht „alles grün". `@deal.pure` nur zu setzen, damit das Werkzeug etwas findet, wäre teuer erkauft: es schließt `@deal.has()` ein und prüft Seiteneffekte bei jedem einzelnen Aufruf.

---
