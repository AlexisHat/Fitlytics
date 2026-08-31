# Fitlytics

Python-Anwendung zur Auswertung von Trainingsdaten aus `.fit`-Dateien und Recovery-Daten
aus dem Whoop-CSV-Export: Kennzahlen, Intervallanalyse und Diagramme in einer
Streamlit-Oberfläche.

## Voraussetzungen

- **Python 3.13** (siehe `.python-version`)
- **[uv]** zur Paket- und Umgebungsverwaltung

uv installieren, falls noch nicht vorhanden:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Installation

Im Projektverzeichnis:

```bash
uv sync
```

Nur die Laufzeitabhängigkeiten ohne Entwicklungswerkzeuge (mypy, ruff, pytest, ...):

```bash
uv sync --no-dev
```

## Anwendung starten

```bash
uv run streamlit run src/app/main.py
```

Die Oberfläche öffnet sich unter `http://localhost:8501`. Der Befehl muss **aus dem
Projektverzeichnis heraus** gestartet werden: die SQLite-Datenbank wird relativ dazu
unter `data/private/fitlytics.db` angelegt (der Ordner wird beim ersten Start
automatisch erzeugt).

## Daten

Alle Daten werden in der Seitenleiste der App hochgeladen, es ist keine manuelle
Vorverarbeitung nötig.

### Trainings (FIT)

Unter **„FIT-Dateien (Trainings)"** lassen sich beliebig viele `.fit`-Dateien auswählen.
Zu jeder Datei werden in der Seitenleiste Titel und Kategorie ergänzt, danach speichert
der Button „... speichern" die Trainings in die lokale Datenbank. Ein doppelter Upload derselben Datei wird erkannt und übersprungen. Es ist jedoch zu empfehlen nicht zu viele Datein aufeinmal hochzuladen, da sonst Streamlit sich aufhängen kann.

Zum **Ausprobieren ohne eigene Daten** gibt es einen Ordner mit echten
Trainingsaufzeichnungen: 15 Radeinheiten von Juni bis August 2026,Grundlagenfahrten,
Sweet-Spot- und Schwellenintervalle, VO2max-Blöcke und ein FTP-Test.

Dieser Ordner ist **nicht Teil des Repositories**, weil die Aufzeichnungen GPS-Spuren und
damit meine tatsächlichen Wohn- und Trainingsorte enthalten. Er wird separat
weitergegeben. Zum Nachvollziehen den erhaltenen Ordner nach

```
data/beispiel/trainings/
```

kopieren, oder von einem beliebigen anderen Ort aus in der App hochladen, für den Import
spielt der Pfad keine Rolle.

Die übrigen Dateien in `data/beispiel/` (`training_gueltig.fit`, `training_defekt.fit`,
`training_leer.fit`, `physiologische_zyklen_*.csv`) sind bewusst kleine bzw. defekte
Testfixtures für die Testsuite und nicht zur Demonstration gedacht.

### Recovery (Whoop-CSV)

Unter **„Whoop-CSV (Recovery)"** wird genau eine Datei erwartet:

```
physiologische_zyklen.csv
```

Sie stammt aus dem CSV-Datenexport der Whoop-App. Der Export kommt als Archiv
`my_whoop_data_<Datum>` und enthält mehrere CSVs (`Schlaf.csv`, `Trainings.csv`,
`logbuch_eintraege.csv`, ...) — davon wird **ausschließlich
`physiologische_zyklen.csv`** verwendet, weil nur sie die Tageswerte für Erholung,
Ruhepuls, HRV, Hauttemperatur, Atemfrequenz und Blutsauerstoff enthält.

Wichtig: Der Export muss **auf Deutsch** erzeugt werden (App-Sprache Deutsch). Der Import
liest die Spalten anhand ihrer deutschen Überschriften, z. B. `Startzeit des Zyklus`,
`Zeitzone des Zyklus`, `Erholungswert %`, `Herzfrequenzvariabilität (ms)`. Ein
englischsprachiger Export wird mit einer Fehlermeldung abgelehnt.

Eigene, echte Daten gehören nach `data/private/` — dieser Ordner ist per `.gitignore`
vom Repository ausgeschlossen.

## Projektstruktur

```
src/             Quellcode, ein Package je Fachkonzern (models/, readers/, analysis/, app/, ...)
tests/           Unit-, Property- und Doctests
data/beispiel/   eingecheckte Testfixtures (trainings/ wird separat weitergegeben)
data/private/    eigene, echte Daten und die SQLite-Datenbank (nicht im Repository)
docs/            Begleitdokumentation zum Projektbericht
```

## Qualitätssicherung

```bash
uv run ruff format --check .    # Formatierung
uv run ruff check .             # Linting
uv run mypy src tests           # Typprüfung (strict)
uv run pytest                   # Tests, inkl. Doctests
uv run interrogate -v src       # Docstring-Abdeckung
uv run python -m deal lint src  # Design by Contract, statisch
```

Diese Prüfungen laufen zusätzlich automatisch vor jedem Commit, sobald die Hooks
eingerichtet sind:

```bash
uv run pre-commit install
```
