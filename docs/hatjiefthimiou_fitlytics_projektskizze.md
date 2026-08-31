# 1. Titel

Fitlytics

# 2. Kurzbeschreibung

Python-Anwendung zur Auswertung von Trainingsdaten aus FIT-Dateien und Recovery-Daten aus Health-CSV-Dateien.

# 3. Verwendete Pakete

* `fitdecode` um die `.fit`-Dateien einzulesen
* `polars` für die DataFrames
* `matplotlib` für Plots
* `sqlite3` für die lokale Speicherung
* `pydantic` für Datenmodelle und Validierung
* `streamlit` für die Benutzeroberfläche im Browser


# 4. Das Wesentliche

Trainingsdaten aus mindestens einer FIT-Datei und Health-Daten aus mindestens einer CSV-Datei einlesen.

Aus den Trainingsdaten sollen grundlegende Kennzahlen berechnet werden:

* Anzahl der Workouts
* Trainingsdauer
* durchschnittliche Herzfrequenz
* durchschnittliche Leistung
* maximale Herzfrequenz
* Distanz

Die Daten sollen in ein einheitliches internes Format gebracht werden. Danach sollen einfache Diagramme erzeugt werden, zum Beispiel:

* Trainingsdauer pro Einheit
* Herzfrequenzverlauf einer Einheit
* HRV-Verlauf über mehrere Tage
* Vergleich von Trainingsbelastung und Recovery-Werten

Genauere Analyse von Radintervallen:

* Dauer vom Intervall (finden über Sliding Window)
* Durchschnittswatt im Intervall
* Durchschnittspuls
* Entwicklung des Pulses innerhalb des Intervalls
* Bewertung wie gleichmäßig waren die Intervalle

GitHub-Commit-Graph-ähnliche Trainingsübersicht:

* Darstellung der Trainingsaktivität pro Tag
* Farbige Hervorhebung je nach Trainingsbelastung
* Schneller Überblick über Trainings- und Ruhetage

Wesentliche rdy wenn:

* FIT-Datei wird ohne manuelle Vorverarbeitung eingelesen
* eine CSV-Datei mit Recovery-Daten eingelesen werden kann
* die wichtigsten Kennzahlen korrekt berechnet werden
* Intervalle Analysiert werden
* Diagramme erzeugt werden

# 5. Nice to have

Automatische Kategorisierung von Trainings:

* Grundlagenfahrt
* Intervalltraining
* lange Einheit
* Gym-Session

Trainingsvorschlag für die nächste Einheit

Die Anwendung soll anhand der letzten Trainingseinheiten und der aktuellen Recovery eine passende nächste Einheit vorschlagen.

Dabei soll berücksichtigt werden:

* welche Trainingsarten zuletzt absolviert wurden
* ob bestimmte Trainingsreize lange nicht gesetzt wurden
* ob vor einer weiteren intensiven Einheit zunächst eine Grundlageneinheit sinnvoll ist

Beispiel:

* wurden zuletzt Schwellen- und Sweetspot-Intervalle gefahren, werden als Nächstes VO₂max-Intervalle vorgeschlagen
* wurde längere Zeit keine Grundlageneinheit gefahren, wird zunächst eine lockere Grundlagenfahrt empfohlen
* bei guter Recovery wird die Zielwattzahl leicht erhöht
* bei mittlerer Recovery wird die Zielwattzahl reduziert
* bei schlechter Recovery wird eine lockere Einheit oder ein Ruhetag vorgeschlagen


Weitere Erweiterungen:

* lokale Speicherung mehrerer Einheiten in SQLite
* Wochenberichte
* Trendanalysen
* Korrelation von Trainingsbelastung, HRV, Ruhepuls und Schlaf
* Import mehrerer Dateien auf einmal

# 6. Werkzeuge

* Paketverwaltung: uv
* Typechecker: mypy
* für Design by Contract: deal
* Linter/ formatter: ruff
* Tests: pytest
* Property-based Tests: hypothesis
* Pre-commit-Hooks: pre-commit

# 7. Offene Implementierungsentscheidungen

* Beispielhafte FIT- und CSV-Dateien prüfen
* Verfügbare Felder und Zeitformate festlegen
* Umgang mit fehlenden Werten definieren
* Internes Datenmodell festlegen
* Aufbau der Module bestimmen:

  * Import
  * Validierung
  * Analyse
  * Speicherung
  * Benutzeroberfläche
* Intervallerkennung festlegen:

* Berechnungsregeln definieren:

  * Trainingsdauer
  * Pausen
  * Durchschnittswerte
  * Trainingsbelastung
  * Gleichmäßigkeit von Intervallen
* SQLite-Datenbankschema festlegen
* Aufbau der Streamlit-Oberfläche festlegen
* Testfälle für Import, Kennzahlen und Intervallanalyse definieren


# 8. Meilensteine bei der Implementierung

1. Projektstruktur und Datenmodelle anlegen
2. FIT-Dateien einlesen
3. Health-CSV-Dateien einlesen
4. Daten validieren und vereinheitlichen
5. Kennzahlen berechnen
6. SQLite-Speicherung umsetzen
7. Diagramme erstellen
8. Intervallanalyse umsetzen
9. Streamlit-Oberfläche erstellen
10. Tests mit Beispieldaten schreiben
11. Anwendung mit echten Trainingsdaten prüfen
12. Fehler beheben und Dokumentation ergänzen

# 9. Erwartete Schwierigkeiten


* FIT-Dateien können unterschiedliche oder fehlende Felder enthalten.
* Health-CSV-Dateien können verschiedene Spalten und Zeitformate verwenden.
* Pausen und fehlerhafte Messwerte können Kennzahlen verfälschen.
* Die automatische Erkennung von Intervallen kann ungenau sein.
* Die Bewertung der Gleichmäßigkeit von Intervallen muss klar definiert werden.
* Trainings- und Recovery-Daten müssen zeitlich korrekt zugeordnet werden.
* Große FIT-Dateien können die Verarbeitung verlangsamen.
* Manche Traings vlt schwer zu klassifizieren
* Der Trainingsvorschlag könnte ohne ausreichende Regeln zu einfach wirken.
* Der Projektumfang könnte für den verfügbaren Zeitraum zu groß werden.
