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

## Meilenstein 6: Kennzahlen

### Trainingsdauer: elapsed_time und moving_time getrennt speichern

**Entscheidung:** `WorkoutMetrics` speichert sowohl `elapsed_time` (letzter minus erster Zeitstempel, inkl. Pausen) als auch `moving_time` (dieselbe Spanne abzüglich Lücken über 2 Sekunden). Beide als `timedelta`.

**Begründung:** Beide sind Interessant für die Analyse

---

### Fehlende Messreihe ergibt `None`, kein Fehler

**Entscheidung:** `avg_power`, `distance_m` usw. sind `None`, wenn die zugehörige Messreihe im Workout komplett fehlt (z. B. kein Leistungsmesser).

**Begründung:** Ein Rad ohne Leistungsmesser ist ein normaler, erwartbarer Zustand, kein Analysefehler

---

### Ein generischer `average()`-Rechenkern statt separater Funktionen je Kennzahl

**Entscheidung:** Ø-Herzfrequenz und Ø-Leistung nutzen dieselbe `average()`-Funktion in `analysis/metrics.py`

**Begründung:** Beide Berechnungen sind identisch (arithmetisches Mittel)

---

### Postcondition von `average()` toleriert Gleitkomma-Rundung

**Entscheidung:** Die Nachbedingung prüft `min ≤ Ergebnis ≤ max` über `_is_between()`, die einen Wert nahe einer Grenze (`math.isclose`) auch als gültig behandelt, statt strikt zu vergleichen.

**Begründung:** `hypothesis` fand einen Fall (drei identische Werte ≈700000), bei dem `sum/len` durch Rundung minimal unter das exakte Minimum fällt — auch `statistics.fmean` zeigt das. Eigenschaft von IEEE-754, kein Fehler in der Berechnung.

---

### Erweiterte Kennzahlen: Gerätewerte übernehmen vs. selbst rechnen

**Entscheidung:** `Workout` bekommt neue `device_*`/`total_*`-Felder (`total_ascent_m`, `total_descent_m`, `avg_grade_pct`, `total_work_j`, `device_normalized_power`, `device_intensity_factor`, `device_training_stress_score`) direkt aus der FIT-Session-Message. Höhenmeter, Steigung und Arbeit (`work_kj`) übernehmen diese Werte; NP/IF/TSS werden selbst berechnet und gegen die Gerätewerte validiert.

**Begründung:** Höhenmeter-Erkennung braucht Rauschfilterung der Barometer-Rohdaten — ein naives Aufsummieren der `altitude_m`-Deltas wäre kein besserer Nachbau, sondern ein schlechterer.
NP brauchen wir dagegen ohnehin für spätere Intervall-Analyse, wo es keinen Geräte-Session-Wert gibt. der Ganz-Workout-Fall ist nur ein Spezialfall und lässt sich sauber testen (eigene NP=178.8 W vs. Gerät 182 W, IF=0.851 vs. 0.865, TSS=99.8 vs. 101.7 — plausibel nah, nicht identisch, vermutlich weil das Gerät die 30s-Fenster anders an Pausen behandelt).

---

### TRIMP, Efficiency Factor, Decoupling: keine Geräte-Entsprechung

**Entscheidung:** `trimp()`, `efficiency_factor()` und `decoupling_pct()` sind vollständig eigene Berechnungen in `analysis/load.py` bzw. `analysis/efficiency.py`.

**Begründung:** Keines dieser Werte liefert das Gerät. TRIMP nutzt dieselbe Pausen-Schwelle wie `moving_time` (`PAUSE_GAP_THRESHOLD`, dafür aus `analysis/workout.py` exportiert statt privat), damit eine Auto-Pause keinen Trainingsreiz vortäuscht. `decoupling_pct` splittet nach Record-Index (nicht nach Zeit) — einfacher, bei nur 5,7 % Pausenanteil in der echten Datei eine vertretbare Näherung.

---

### FTP/hr_rest/hr_max als durchgereichte Parameter, kein Autoload

**Entscheidung:** Jede Funktion, die FTP oder HF-Grenzwerte braucht, nimmt sie als Parameter (Default `None` → Ergebnis `None`). Aufrufer übergeben `workout.ftp_watts` selbst, es gibt keinen automatischen Rückgriff darauf innerhalb der Funktionen.

**Begründung:** `hr_rest`/`hr_max` gibt es ohnehin in keiner FIT-Datei

---

### HF-Zonenverteilung nach Karvonen statt %HFmax oder Geräte-Zonen

**Entscheidung:** `heart_rate_zone_distribution()` in `analysis/heart_rate_zones.py` nutzt die Herzfrequenzreserve (`HRR = (HF - hr_rest) / (hr_max - hr_rest)`), nicht simples %HFmax. `hr_rest`/`hr_max` sind Parameter wie bei TRIMP.

**Begründung:** Genauer als %HFmax, weil unterschiedliche Ruheherzfrequenzen bei gleicher Max-HF unterschiedliche aerobe Basis widerspiegeln genau der Vorteil, den eine selbst gebaute Anwendung gegenüber Standardwerten hat.

---

### Leistungszonen: vier gängige Modelle zur Auswahl

**Entscheidung:** `power_zone_distribution()` in `analysis/power_zones.py` lässt zwischen vier Zonenmodellen wählen (polarisiert 3, klassisch 5, British Cycling 6, Coggan/Allen 7), Default Coggan/Allen 7.

**Begründung:** Anders als bei HF-Zonen gibt es bei Leistungszonen kein einzelnes Standardmodell — diese vier sind die mir bekannten, gängigsten Einteilungen.

---

### Meilenstein-Reihenfolge: SQLite nach Streamlit statt davor

**Entscheidung:** SQLite-Speicherung (ursprünglich Meilenstein 7) wandert hinter Diagramme/Kalenderansicht, Intervallanalyse und Streamlit-Oberfläche, neu auf Position 10.

**Begründung:** Schema und Zugriffsmuster sollen sich an den tatsächlichen Anforderungen der Oberfläche orientieren statt spekulativ vorher entworfen zu werden

---

## Meilenstein 7: Diagramme

### Zwei Plot-Bibliotheken statt einer, nach Zweck getrennt

**Entscheidung:** `plotly` kommt als zusätzliche Abhängigkeit dazu und wird ausschließlich für die interaktive Multi-Panel-Zeitreihe eines einzelnen Trainings verwendet

**Begründung:** Für die Visualisierung wird Plotly anstelle von Matplotlib verwendet, da Plotly interaktive Diagramme mit Funktionen wie Zoom, Hover-Informationen und der gezielten Auswahl einzelner Datenbereiche ermöglicht.

---

### Eine geteilte x-Achse mit gestapelten y-Achsen statt `make_subplots`

**Entscheidung:** `build_timeline_figure` baut die Panels manuell über eine gemeinsame `xaxis` mit vier `domain`-gestaffelten y-Achsen statt über `plotly.subplots.make_subplots`.

**Begründung:** Bei `make_subplots` bleiben Hover, Spikelines und Tooltip auf das Panel unter dem Mauszeiger beschränkt — `shared_xaxes` koppelt nur Zoom/Pan, keine Hover-Events. Erst eine echte gemeinsame x-Achse lässt die Spike-Linie über alle Panels laufen, im Browser gegen echte Daten verifiziert.

---


### GPS-Position: `Latitude`/`Longitude` als definitorische Pydantic-Typen

**Entscheidung:** `RecordPoint` bekommt `latitude`/`longitude` (neue `Annotated`-Typen in `models/types.py`, `Field(ge=-90, le=90)` bzw. `ge=-180, le=180`). `readers/fit.py` konvertiert die rohen `position_lat`/`position_long`-Semicircles mit Faktor `180 / 2**31`.

**Begründung:** Die Gradgrenzen folgen aus der Größe selbst (wie bei `PercentInt`/`PercentFloat`), nicht aus physiologischer Plausibilität — gehören damit ins Modell, nicht nach `validation/ranges.py`. Ein aus einem defekten Semicircle-Wert entstehender Grad außerhalb der Grenzen lässt wie jedes andere Feld in `_build_record_point` die Konstruktion fehlschlagen und den Import als `FileImportError` melden, statt eine neue Sonderbehandlung nur für GPS einzuführen.

---

### `Workout.has_gps_track`: mindestens zwei Fixe statt „irgendein Fix"

**Entscheidung:** Neue Property direkt auf `Workout` (analog zu `PowerZoneDistribution.total_duration`). Liefert `True` erst ab mindestens zwei Records mit gesetzten `latitude`/`longitude`.

**Begründung:** Ein einzelner GPS-Punkt lässt sich nicht als Strecke zeichnen. Die Schwelle „mindestens zwei" folgt demselben Muster wie andernorts (`trimp`, `power_zone_distribution`: beide verlangen mindestens zwei Samples).

---

### Open Street Map als Kartentyp

**Entscheidung:**  Open Street Map als Kartentyp

**Begründung:** Schon vorerfahrungen mir Open Street Map

---

### Doppelt befahrene Streckenabschnitte: höherer Messwert liegt oben

**Entscheidung:** Bei diesem Intervalltraining (Loop-/Aus-und-zurück-Strecke) liegen 89 % aller GPS-Punkte auf mehrfach befahrenen Stellen (bis zu 20-mal), die sich auf der Karte überlappen. Linie (Streckenverlauf, chronologisch) und Marker (Einfärbung) sind deshalb zwei getrennte Traces. Die Marker werden aufsteigend nach Metrikwert gezeichnet, sodass an jeder überlappenden Stelle immer der höchste dort gemessene Wert oben liegt. Fehlt der Messwert nur an einer einzelnen Stelle zwischen zwei bekannten Werten, wird er für die Einfärbung interpoliert; fehlt er ohne Nachbarwert (Anfang/Ende), wird der Punkt nicht eingefärbt gezeichnet.

**Begründung:** Bei einer festen Zeichenreihenfolge (z. B. chronologisch) würde eine frühe, lockere Runde eine spätere, harte Intervall-Wiederholung an derselben Stelle einfach zudecken. Der höchste Wert oben ist für die Trainingsanalyse aussagekräftiger, auch wenn das bei der Steigung (divergierende Skala) dazu führt, dass Anstiege Gefälle an überlappenden Stellen überdecken statt umgekehrt — eine bewusst in Kauf genommene Nebenwirkung derselben einheitlichen Regel für alle Metriken.

---

### Trainingsbelastung für die Kalenderansicht: TSS, sonst TRIMP als Fallback

**Entscheidung:** `training_load()` in `analysis/load.py` nutzt TSS, wenn die Einheit Leistungsdaten und ein bekanntes FTP hat, sonst TRIMP. `build_calendar()` in `analysis/calendar.py` ordnet ein Workout dem UTC-Datum von `start_time` zu (FIT-Dateien liefern keine lokale Zeitzone) und summiert die Belastung mehrerer Workouts am selben Tag. Ein negativer TRIMP-Wert (HF unter `hr_rest`) wird auf 0 gekappt, ebenso ein Tag, an dem keine der beiden Methoden berechenbar war (kein Leistungsmesser, kein bekanntes HF-Profil) — beides ist im Kalender nicht von einem echten Ruhetag unterscheidbar.

**Begründung:** TSS ist die exaktere Kennzahl bei vorhandenem Powermeter, TRIMP deckt jedes Training über die Herzfrequenz ab. Ruhetage werden im vollständigen Datumsbereich als `training_load=0.0` geführt statt ausgelassen, damit die Kalenderansicht eine lückenlose Wochen-/Tage-Struktur hat.

---

### Vier Diagramme aus der Projektskizze: drei abgedeckt, eines bewusst verworfen

**Entscheidung:** "Herzfrequenzverlauf einer Einheit" ist durch den Timeline-Plot abgedeckt, "Trainingsdauer pro Einheit" durch die Kennzahlen-Kachel in der Tagesansicht, "HRV-Verlauf über mehrere Tage" durch den Recovery-Trend auf der neuen Recovery-Seite. Der vierte Punkt, "Vergleich Trainingsbelastung/Recovery", wurde prototypisch gebaut (Balken der Tagesbelastung gegen die Recovery-Quote des Folgetags, zeitlich versetzt gepaart über `analysis.load_recovery`) und danach wieder verworfen.

**Begründung:** Der Prototyp lief fehlerfrei und war technisch korrekt — Belastung an Tag D wurde bewusst gegen die Recovery-Quote von Tag D+1 gestellt, da ein Whoop-Zyklus Schlaf plus Folgetag ist und der Score vor dem Tag feststeht (siehe „Whoop-Tagesbezug: Mittag-zu-Mittag"). Im Praxistest gegen echte Daten bot das Diagramm aber keinen erkennbaren Mehrwert für das Training: bei wenigen Trainingstagen im Verhältnis zu einem Jahr Recovery-Daten bestand die Ansicht überwiegend aus leeren Tagen, und selbst mit mehr Trainingsdaten liefert ein einzelner Balken/Punkt pro Tag keine Aussage, die nicht schon aus der bestehenden Recovery-Übersicht und dem Trainingskalender nebeneinander ablesbar wäre. Eine Umsetzung nur, weil sie in der Projektskizze steht, ohne dass sie dem Training etwas nützt, widerspräche dem Grundsatz "lieber weniger Umfang als ein unfertiges oder wertloses Feature" (CLAUDE.md §1, §7). Die Abweichung von der Minimalanforderung wird hier bewusst in Kauf genommen und im Bericht als solche benannt.

---

## Meilenstein 8: Intervallanalyse

### Lokale Baseline: zentriertes rollierendes Quantil (25 %) über 600s statt Median

> **Überholt** — die lokale Baseline wurde später vollständig verworfen, siehe „Bezugsniveau: Zwei-Klassen-Schwelle statt lokaler Baseline" weiter unten.

**Entscheidung:** `compute_baseline()` in `src/intervals/preprocessing.py` legt ein zentriertes rollierendes 25 %-Quantil (`BASELINE_QUANTILE = 0.25`, `BASELINE_WINDOW_S = 600`, `min_samples=1`) über die rohe Leistung, nicht den Median.

**Begründung:** Bei einer Intervall-Session mit hohem Arbeitsanteil (z. B. 5×4 min bei 240s Arbeit zu 180s Pause) ist die Belastung streckenweise die Mehrheit im 600s-Fenster — der Median driftet dann Richtung Blockleistung statt das Erholungsniveau abzubilden, gemessen als Startversatz von 60s auf "5×4 min sauber". Ein niedriges Quantil bleibt am Erholungsniveau verankert, solange ein nennenswerter Anteil des Fensters dort liegt. Randbehandlung weiterhin durch schrumpfendes statt aufgefülltes Fenster.

---

### Kandidatensuche: direkte Hysterese-Schwelle statt CUSUM + `scipy`

> **Teilweise überholt** — die Absage an CUSUM und `scipy` gilt weiter, die Hysterese auf der *rohen* Leistung wurde jedoch durch eine einzelne Schwelle auf der geglätteten Leistung ersetzt, siehe „Glättung vor der Erkennung" weiter unten.

**Entscheidung:** Ein erster Entwurf fand Blockkanten über ein kumuliertes Abweichungssignal (CUSUM) mit `scipy.signal.find_peaks`. Das wurde verworfen zugunsten einer einfachen Zwei-Schwellen-Hysterese direkt auf der rohen Leistung gegen die lokale Baseline (`find_threshold_candidates()` in `src/intervals/candidates.py`) — ohne Glättung, ohne kumuliertes Signal, ohne `scipy`.

**Begründung:** Der CUSUM-Ansatz brachte deutlich mehr Code und eine strukturelle Schwäche mit (ein isolierter Block ohne anschließenden Leistungsabfall erzeugt kein für `find_peaks` erkennbares Maximum, siehe frühere Fassung dieses Eintrags) und war für eine als "Sliding Window"-Erkennung skizzierte Aufgabe (Projektskizze) unangemessen aufwendig. Die einfachere Version behebt das CUSUM-Problem nebenbei (kein kumulatives Signal, das "stehen bleiben" kann) und kommt ohne `scipy`/`numpy` aus — beide Abhängigkeiten wieder aus `pyproject.toml` entfernt.

---

### Ausgabemodell: `IntervalBlock` mit Ø-Watt, Ø-Puls, Pulsentwicklung, Gleichmäßigkeit

**Entscheidung:** `build_interval_block()` in `src/intervals/blocks.py` wandelt ein erkanntes Kandidatenfenster in das eigentliche Berichtsobjekt um. Pulsentwicklung ist definiert als Ø-Puls der zweiten Hälfte minus Ø-Puls der ersten Hälfte des Blocks (positiv = Puls steigt); Gleichmäßigkeit als 1 minus Variationskoeffizient der Leistung im Block.

**Begründung:** Damit ist die in CLAUDE.md §11 offene Frage nach der Gleichmäßigkeits-Metrik entschieden (Variationskoeffizient, wie dort vorgeschlagen). Die Zweiteilung für die Pulsentwicklung ist die einfachste Definition, die eine Drift über den Block hinweg abbildet, ohne eine separate Regression zu benötigen.

---

## Meilenstein 9: Streamlit-Oberfläche

### Kalender-Intensitätsfarbe: kontinuierliche Prozentskala relativ zum härtesten Tag statt Quartil-Buckets

**Entscheidung:** `training_load_intensity_pct()` in `src/analysis/calendar.py` ersetzt die bisherigen 5 Quartil-Buckets durch eine kontinuierliche 0–100 %-Skala relativ zu den `training_load`-Werten des gerade angezeigten Kalenders (härtester Tag = 100 %, Ruhetag = 0 %, linear dazwischen); `calendar_view.py` färbt den Tages-Button entsprechend in einem Blauverlauf statt ihn nur fett darzustellen.

**Begründung:** Gleiche Logik wie zuvor — relativ zum eigenen Kalender statt fester TSS/TRIMP-Schwelle, weil ein Tag je nach Datenlage TSS oder TRIMP nutzt und beide nicht auf einer gemeinsamen absoluten Skala liegen — jetzt aber als sichtbarer Farbverlauf statt nur Fett-Schrift, auf ausdrücklichen Nutzerwunsch.

---

### Kalender: monatsweise Navigation statt einer durchgehenden Liste aller Wochen

**Entscheidung:** `build_calendar()` nimmt jetzt `year`/`month` statt den Datumsbereich aus den Workouts abzuleiten, und liefert immer genau einen vollständigen Monat (1. bis letzter Tag, auch ohne Workouts). `calendar_view.py` hält den aktuell angezeigten Monat in `st.session_state.calendar_month` mit ◀/▶-Buttons zum Wechseln.

**Begründung:** Die bisherige Ansicht zeigte alle Wochen zwischen erstem und letztem Workout durchgehend untereinander — bei mehreren Monaten Historie eine sehr lange Liste ohne Monats-Kontext. Als Nebeneffekt bezieht sich auch `training_load_intensity_pct()`s "härtester Tag im sichtbaren Kalender" jetzt auf den gezeigten Monat statt die komplette Historie.

---

### Intervallanalyse manuell per Button statt automatisch bei jedem Seitenaufruf

**Entscheidung:** `_render_intervals()` löst die Erkennung nicht mehr automatisch aus, sobald ein Tag mit Workout angezeigt wird, sondern erst nach Klick auf "Intervallanalyse starten" pro Workout. Der Zustand (`state_key = f"interval_analysis_active_{workout.start_time.isoformat()}"`) bleibt in `st.session_state`, damit das Ergebnis auch nach einem Rerun durch ein anderes Widget (z. B. die GPS-Metrik-Auswahl) sichtbar bleibt.

**Begründung:** nicht jede fahrt sind exakt intervalle

---

## Meilenstein 10: SQLite-Speicherung

### Bibliothek: `sqlite3` aus der Standardbibliothek

**Entscheidung:** `sqlite3` statt SQLAlchemy oder `sqlmodel`.

**Begründung:** War schon in der Projektskizze so vorgesehen, keine neue Abhängigkeit. Pydantic-Modelle sind bereits die interne Datenschicht — ein ORM würde nur eine zweite, parallele Modell-Hierarchie einführen. Passt zu "Einfachheit vor Library-Anspruch".

---

### `conn.row_factory = sqlite3.Row` statt Positions-Tupel

**Entscheidung:** Zeilen aus `SELECT`s werden per Spaltenname gelesen (`row["sport"]`), nicht per Index (`row[2]`).

**Begründung:** Robuster gegen künftige Spaltenumsortierung in den `SELECT`-Statements, lesbarer beim Zuordnen zu den Pydantic-Feldern.

---

### Speicherzeitpunkt: automatisch bei jedem Upload

**Entscheidung:** Workouts werden automatisch bei jedem Upload in SQLite gespeichert, kein separater "Speichern"-Button. Vorher wird geprüft, ob die Einheit schon in der DB existiert (genaue Prüflogik noch offen — Teil der Schema-Diskussion).

**Begründung:** Weniger Klicks; ohne Prüfung würde erneutes Hochladen derselben Datei zu doppelten Einträgen führen.

---

### Datenbank-Pfad: `data/private/fitlytics.db`, Verzeichnis wird bei Bedarf angelegt

**Entscheidung:** Die DB liegt unter `data/private/`, demselben (bereits per `.gitignore` ausgeschlossenen) Ordner wie echte private Trainingsdaten. `_load_persisted_workouts()` legt das Verzeichnis vorher mit `mkdir(parents=True, exist_ok=True)` an.

**Begründung:** Bei einem frischen Checkout existiert `data/private/` nicht (nicht Teil des Repositories) — ohne das `mkdir` würde `init_db()` beim allerersten Start mit `StorageError` fehlschlagen, was Anforderung 7 ("bei Dritten per README lauffähig") verletzen würde.

---

---

## Überarbeitung der Intervallanalyse

Die erste Fassung (Meilenstein 8) fand auf echten Fahrten nichts Brauchbares: auf einer 90-minütigen Einheit mit drei klar gefahrenen Achtminuten-Intervallen lieferte sie 8 Blöcke zwischen 61s und 266s, keiner davon deckungsgleich mit einem echten Intervall. Die folgenden Einträge dokumentieren den Umbau.

### Glättung vor der Erkennung: 30s zentrierter Mittelwert

**Entscheidung:** `smooth_power()` in `src/intervals/preprocessing.py` legt einen zentrierten 30s-Rolling-Mean über die Leistung (`SMOOTHING_WINDOW_S = 30`). Die gesamte Erkennung arbeitet auf dieser Spalte, nicht mehr auf der rohen Leistung.

**Begründung:** Die rohe 1-Hz-Leistung ändert sich im Median um 12 W pro Sekunde, auch mitten in einer gleichmäßigen Belastung. Jede Schwelle auf diesem Signal wird ständig über- und unterschritten: auf der Messfahrt zersplitterte die Hysterese ein Training in 214 Rohkandidaten. Die Zwei-Schwellen-Hysterese war ein Symptomkurieren dafür und entfällt mit der Glättung ersatzlos — eine Schwelle genügt.

---

### Bezugsniveau: Zwei-Klassen-Schwelle (Otsu) statt lokaler Baseline oder globalem Median

**Entscheidung:** `effort_threshold()` teilt die Leistungswerte einer Fahrt per Histogramm in eine leichte und eine harte Klasse und liefert den Schnitt, der die Varianz *zwischen* den Klassen maximiert (Verfahren nach Otsu, `OTSU_BINS = 64`). `compute_baseline()` wurde ersatzlos entfernt.

**Begründung:** Zwei Vorgänger scheiterten aus entgegengesetzten Gründen. Die lokale rollierende Baseline besteht innerhalb eines langen Intervalls überwiegend aus dem Intervall selbst und steigt mit — gemessen 143 W Baseline innerhalb eines Blocks mit Ø 220 W, wodurch die Ausstiegsschwelle den Block von innen auffrisst. Ein globaler Median scheitert spiegelbildlich, sobald die Intervalle mehr als die Hälfte der Fahrt ausmachen: im Szenario `clean_5x4min` (54 % Arbeitsanteil) liegt der Median bei 220 W, die Schwelle bei 286 W und damit über dem Maximum von 251 W — es wird gar nichts gefunden. Der Zwei-Klassen-Split hängt nicht davon ab, *wieviel* Zeit in welcher Klasse verbracht wird, und löst beides. Gemessen über alle 8 Szenarien und 4 echte Fahrten: Median 3/8, 25 %-Quantil 4/8, Otsu 6/8 bei zugleich präzisesten Blockgrenzen auf den echten Fahrten. Coasting (≤ `COASTING_POWER_W`) wird vorher ausgeschlossen, sonst bildet es eine dritte Klasse, an der sich der Schnitt festsetzt.

---

### Mindestdauer 120s: kurze Intervalle sind eine dokumentierte Grenze

**Entscheidung:** `MIN_BLOCK_DURATION_S = 120`. Blöcke darunter werden nicht gemeldet. Die Szenarien `ten_by_30s_with_pauses` und `single_1min_block_in_warmup` haben Tests, die prüfen, dass **nichts** erkannt wird.

**Begründung:** Die 30s-Glättung dämpft alles in ihrer eigenen Größenordnung weg; 30s-Sprints wären nur über eine zweite, deutlich kürzere Skala erkennbar. Gemessen wurde die Alternative: bei 60s käme das 1-Minuten-Szenario dazu, dafür entstehen zwei Fehltreffer auf `rolling_terrain_no_intervals`, bei 30s zusätzlich ein Fehltreffer auf der echten Fahrt. 120s hält alle acht Szenarien fehltrefferfrei. Ein Mehrskalen-Ansatz wäre ein eigenes Feature; ein unfertiges davon wäre schlechter als die klar benannte Grenze (CLAUDE.md §7). Nichts zu melden ist ehrlicher, als falsche Blöcke zu melden.

---
