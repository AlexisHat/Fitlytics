# Fitlytics

Python-Anwendung zur Auswertung von Trainingsdaten aus `.fit`-Dateien und Recovery-Daten
aus Health-CSV-Dateien: Kennzahlen, Intervallanalyse und Diagramme in einer
Streamlit-Oberfläche.

> Das Projekt befindet sich in Entwicklung. Die Streamlit-Oberfläche entsteht gerade
> schrittweise; die SQLite-Speicherung folgt erst danach — hochgeladene Daten gelten
> bislang nur für die laufende Browser-Sitzung.

## Voraussetzungen

- Python 3.13
- [uv](https://docs.astral.sh/uv/) zur Paket- und Umgebungsverwaltung

## Installation

```bash
uv sync
```

Installiert alle Laufzeit- und Entwicklungsabhängigkeiten in eine projekteigene
virtuelle Umgebung (`.venv/`).

## Anwendung starten

```bash
uv run streamlit run src/app/main.py
```

Öffnet die Oberfläche unter `http://localhost:8501`. FIT-Dateien und die Whoop-CSV
werden über die Seitenleiste hochgeladen; da die SQLite-Speicherung noch aussteht, gehen
importierte Daten beim Neuladen der Seite oder Neustart der App wieder verloren.

## Projektstruktur

```
src/             Quellcode, ein Package je Fachkonzern (models/, errors/, app/, ...)
tests/           Tests (Unit-, Property- und Doctests)
data/beispiel/   kleine, eingecheckte Beispieldateien (FIT/CSV, auch defekte Varianten)
data/private/    eigene, echte Trainingsdaten (nicht Teil des Repositories)
docs/            Projektskizze und Begleitdokumentation zum Bericht
```

## Qualitätssicherung

```bash
uv run ruff format .          # Formatierung
uv run ruff check .           # Linting
uv run mypy src tests         # Typprüfung (strict)
uv run pytest                 # Tests, inkl. Doctests
uv run interrogate -v src     # Docstring-Abdeckung
uv run python -m deal lint src  # Design-by-Contract: statische Prüfung
uv run python -m deal test src  # Design-by-Contract: generierte Tests gegen @deal.pure-Funktionen
```

Alle Prüfungen laufen zusätzlich automatisiert vor jedem Commit über `pre-commit`:

```bash
uv run pre-commit install
```
