# Code-Qualität: deaktivierte Regeln schrittweise wieder aktivieren

Ruff läuft mit `select = ["ALL"]`. Die folgenden Regeln sind in `pyproject.toml` unter `[tool.ruff.lint] ignore` bewusst deaktiviert. Pyright läuft vorerst im Modus `standard`.

## Deaktivierte Ruff-Regeln

| Regel | Was sie prüft | Warum deaktiviert | Treffer bei Einführung |
|---|---|---|---|
| `T201` | Kein `print()` | `print()` ist die Benutzeroberfläche dieser CLI-Tools | 94 |
| `CPY001` | Copyright-Hinweis am Dateianfang | Es gibt noch keine Lizenz und keinen festgelegten Rechteinhaber | 12 |
| `COM812` | Trailing Comma bei mehrzeiligen Aufrufen | Konflikt mit `ruff format`, der Formatter setzt Kommas selbst | 15 |
| `ISC001` | Implizit verkettete Strings in einer Zeile | Konflikt mit `ruff format` | 0 |
| `D203` | Leerzeile vor Klassen-Docstring | Widerspricht `D211` (keine Leerzeile), das aktiv bleibt | 11 |
| `D213` | Docstring-Zusammenfassung in der zweiten Zeile | Widerspricht `D212` (erste Zeile), das aktiv bleibt | 13 |

### Vorgehen für eine Regel

1. Treffer ansehen, ohne etwas zu ändern (die Regel wird dabei trotz `ignore` geprüft):
   ```
   uv run ruff check --select T201 --statistics
   uv run ruff check --select T201
   ```
2. Automatisch behebbare Treffer (`[*]` in der Statistik) beheben lassen:
   ```
   uv run ruff check --select T201 --fix
   ```
3. Den Rest von Hand beheben oder gezielt mit `# noqa: T201` und Begründung markieren.
4. Die Regel aus der `ignore`-Liste in `pyproject.toml` entfernen und prüfen, dass alles grün ist:
   ```
   uv run ruff format --check
   uv run ruff check
   ```

### Hinweise je Regel

- **`T201`:** Für das Wieder-Aktivieren müssten die Ausgaben auf das `logging`-Modul umgestellt werden (Logger mit einem Handler auf `stdout`, damit die Ausgabe für Nutzer:innen gleich bleibt). Das lässt sich Modul für Modul erledigen. Bis alle Module umgestellt sind, können die noch offenen Module über `[tool.ruff.lint.per-file-ignores]` ausgenommen werden, z.B. `"src/matrix_tools/watchdog.py" = ["T201"]`.
- **`CPY001`:** Sobald eine Lizenz (z.B. `LICENSE`-Datei) und ein Rechteinhaber festgelegt sind, an den Anfang jeder Datei einen Hinweis wie `# Copyright 2026 <Rechteinhaber>` setzen. Das erwartete Format lässt sich über `[tool.ruff.lint.flake8-copyright]` anpassen (`notice-rgx`, `author`).
- **`COM812`, `ISC001`:** Nicht wieder aktivieren, solange `ruff format` verwendet wird. Ruff warnt sonst selbst vor dem Konflikt.
- **`D203`, `D213`:** Nicht wieder aktivieren. Es gilt immer genau eine Regel aus jedem Paar (`D203`/`D211` bzw. `D212`/`D213`). Wer den anderen Stil bevorzugt, tauscht die Regeln: z.B. `D212` in die `ignore`-Liste und `D213` heraus, danach `uv run ruff check --select D213 --fix`.

## Pyright: von `standard` zu `strict`

Bei Einführung meldet `strict` 16 Fehler: 7× `reportMissingTypeStubs`, 5× `reportUnknownMemberType`, 4× `reportUnknownVariableType`. Sie stammen fast alle aus `matrix-nio`, das nur teilweise typisiert ist.

1. Einzelne Dateien zuerst umstellen: `# pyright: strict` als erste Zeile in eine Datei schreiben (z.B. `src/matrix_tools/paths.py`) und prüfen:
   ```
   uv run pyright
   ```
2. Fehler aus `matrix-nio` durch `isinstance`-Prüfungen oder kleine typisierte Hilfsfunktionen beheben. Fehlende Stubs (`reportMissingTypeStubs`) lassen sich bei Bedarf gezielt abschalten:
   ```toml
   [tool.pyright]
   reportMissingTypeStubs = false
   ```
3. Wenn alle Dateien `strict` bestehen, in `pyproject.toml` global umstellen und die `# pyright: strict`-Kommentare wieder entfernen:
   ```toml
   [tool.pyright]
   typeCheckingMode = "strict"
   ```
   Danach muss `uv run pyright` fehlerfrei durchlaufen.
