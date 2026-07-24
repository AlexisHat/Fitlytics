# Beispieldaten

Kleine, eingecheckte Dateien für die Test- und Importlogik (siehe CLAUDE.md Abschnitt 6):

- `training_gueltig.fit` — gültige FIT-Datei, 20 Records + vollständige Session/Lap/Activity-
  Abschlussnachrichten. Erzeugt aus einer echten privaten Aufnahme mit
  [`scripts/build_example_fit.py`](../../scripts/build_example_fit.py) (kein GPS enthalten).
- noch offen: defekte und leere FIT-Variante, gültige und defekte/leere Whoop-CSV.

Echte, umfangreiche Trainingsdaten gehören **nicht** hierher, sondern nach `data/private/`
(nicht Teil des Repositories, nicht Teil der Testsuite).
