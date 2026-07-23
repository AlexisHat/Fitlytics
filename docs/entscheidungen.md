# Designentscheidungen

Rohfassung für die Kapitel des Projektberichts. Pro Entscheidung: Problem, gewählte Lösung,
verworfene Alternative, Begründung. Wird fortlaufend während der Entwicklung ergänzt.

## Meilenstein 1: Projektgerüst

### `src/`-Layout statt flachem Paket

**Problem:** Wie wird das Python-Paket im Repository angeordnet?
**Lösung:** `src/fitlytics/` als Paketwurzel, `hatchling` als Build-Backend, editable Install
über `uv sync`.
**Alternative verworfen:** Paket direkt im Repo-Wurzelverzeichnis (`fitlytics/` neben
`pyproject.toml`).
**Begründung:** Das `src/`-Layout verhindert, dass Tests versehentlich gegen den
Arbeitsordner statt gegen das installierte Paket laufen, und ist für ein mit `uv`
verwaltetes Projekt der übliche Standard.

### Ruff-Regelumfang und Docstring-Konvention

**Problem:** Welche `ruff`-Regeln sind aktiv, insbesondere im Hinblick auf die geforderten
Google-Style-Docstrings?
**Lösung:** `select = ["E", "F", "I", "UP", "B", "N", "D"]` mit
`[tool.ruff.lint.pydocstyle] convention = "google"`; die Docstring-Regeln (`D`) gelten nur
für `src/`, nicht für `tests/`.
**Alternative verworfen:** `D`-Regeln auch auf Tests anwenden; oder gar keine
`pydocstyle`-Regeln und stattdessen ausschließlich auf `interrogate` verlassen.
**Begründung:** `interrogate` prüft nur, *ob* eine Docstring existiert, nicht ihre Struktur.
Die `D`-Regeln erzwingen zusätzlich Google-Konvention (Args/Returns/Raises) bereits beim
Schreiben. Für Testfunktionen ist eine Docstring-Pflicht nicht sinnvoll, da der Testname den
Sachverhalt bereits beschreibt und CLAUDE.md die Docstring-Pflicht auf „jede öffentliche
Funktion" der Fachlogik bezieht.

### `pytest`-Exit-Code 5 im pre-commit-Hook

**Problem:** `pytest` liefert Exit-Code 5, solange keine Tests/Doctests existieren (frühe
Commits vor Meilenstein 2). `pre-commit` wertet jeden Exit-Code ≠ 0 als Fehler und hätte
damit *jeden* Commit blockiert, nicht nur den Toolchain-Report.
**Lösung:** Der lokale `pytest`-Hook fängt Exit-Code 5 ab und behandelt ihn als Erfolg;
echte Testfehler (Exit-Code 1) blocken weiterhin.
**Alternative verworfen:** Hook unverändert lassen und Commits bis zum ersten echten Test
manuell mit `--no-verify` umgehen.
**Begründung:** `--no-verify` widerspricht der Vorgabe, Hooks nicht zu überspringen. Das
gezielte Abfangen von Exit-Code 5 ist eine reine Tooling-Entscheidung (kein fachlicher
Fallback im Sinne von Abschnitt 10) und lässt echte Fehler weiterhin durchschlagen.

### Design-by-Contract-Prüfung: `deal lint`/`deal test` statt `deal prove`

**Problem:** Wie wird automatisiert geprüft, dass `@deal.pre`/`@deal.post`-Verträge nicht
verletzt werden?
**Lösung:** `deal lint` (statische Prüfung) und `deal test` (automatisch generierte Tests
gegen `@deal.pure`-Funktionen) als harte Anforderung (§2) und als pre-commit-Hooks.
**Alternative verworfen:** Zusätzlich `deal prove` für formale Beweise.
**Begründung:** `deal prove` benötigt das separate Paket `deal-solver` als weiteren
SMT-Solver-Unterbau. Das ist eine zusätzliche Abhängigkeit ohne unmittelbaren Mehrwert
gegenüber der bereits eingerichteten Hypothesis-Anbindung (siehe nächster Punkt) und wurde
bewusst nicht ergänzt.

### Hypothesis mit `crosshair`-Backend statt reinem Zufallssampling

**Problem:** Property-based Tests mit `hypothesis` sampeln standardmäßig zufällig — für
Rechenkerne mit engen Randbedingungen (z. B. Kennzahlen, Intervallerkennung) kann das
Gegenbeispiele leicht übersehen.
**Lösung:** Das Paket `hypothesis-crosshair` (zieht `crosshair-tool`/`z3-solver` nach) als
Dev-Abhängigkeit ergänzt, um bei Bedarf `@settings(backend="crosshair")` zu nutzen —
symbolische statt rein zufällige Suche nach Gegenbeispielen.
**Alternative verworfen:** `deal prove` (siehe oben) als alleinigen formalen
Verifikationsweg.
**Begründung:** Der Ansatz wurde in der begleitenden Vorlesung behandelt und passt direkt
an die für Meilenstein 6 (Kennzahlen) und Meilenstein 9 (Intervallanalyse) ohnehin
vorgesehenen Hypothesis-Tests an. Nachteil: `z3-solver` ist mit ca. 37 MB eine spürbar
größere Abhängigkeit; das ist für ein Uniprojekt mit `uv sync` als Installationsweg
akzeptabel. Konkrete Funktionen, die mit dem crosshair-Backend getestet werden, werden erst
bei den jeweiligen Meilensteinen festgelegt.

### Ordnername `data/private/` statt `data/privat/`

**Problem:** CLAUDE.md nannte den Ordner für echte, nicht eingecheckte Trainingsdaten
ursprünglich `data/privat/` (deutsche Schreibweise); tatsächlich angelegt wurde
`data/private/`.
**Lösung:** CLAUDE.md an den bereits bestehenden Ordnernamen `data/private/` angepasst.
**Alternative verworfen:** Vorhandenen Ordner samt Inhalt auf `data/privat/` umbenennen.
**Begründung:** Der Ordner enthielt bereits eine reale Beispieldatei; die Dokumentation an
die bestehende Realität anzupassen war der kleinere, risikoärmere Eingriff.
