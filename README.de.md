# mac-space-cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · **Deutsch**

Ein Skill, der den Speicherplatz deines Macs bereinigt.

> Workflow in sechs Stufen: Moduswahl, Umgebungs-Probe, Scan, Klassifikation, Bestätigung, Report. Jeder Kandidat wird L1-L4 eingestuft; alle Schreibvorgänge im Dateisystem laufen durch `safe_delete.py`, das eine interne Blocklist enthält und zusammen mit einem Sub-Agenten zur Privatsphären-Prüfung und einem Validator nach dem Rendering drei Schichten Guardrails bildet. Bytes, die im Trash auf das Leeren warten, werden separat gezählt und nicht in die Summe „freigegeben" eingerechnet. Null pip-Abhängigkeiten — nur macOS-Befehle und die Python-Standardbibliothek.

---

## Warum dieses Skill

Regelbasierte Cleaner (CleanMyMac, OnyX) verarbeiten nur Einträge, die ihre Regeln benennen können: ob ein bestimmtes `node_modules` noch in Benutzung ist, welche Verzeichnisse unter `~/Library/Caches` aktiven Nutzereinstellungen entsprechen und welche Rückstand sind — diese Beurteilungen liegen außerhalb der Regelreichweite, also überspringen solche Werkzeuge sie konservativ und lassen erheblichen rückgewinnbaren Speicher liegen.

Die Bereinigung direkt einem Agenten zu überlassen („Claude, räum meinen Mac auf") deckt diese Grauzonen ab, doch ohne harte Grenzen kann eine einzige Fehleinschätzung `.git` / `.env` / Keychains erreichen.

Dieses Skill setzt zuerst die Sicherheitsgrenze: die Blocklist von `safe_delete.py`, der Privatsphären-Reviewer und der Validator nach dem Rendering bilden drei Guardrails, die zur Laufzeit die genannten Pfade ablehnen. Unter dieser Voraussetzung wird das Urteil vollständig dem Agenten übertragen, der die Grauzonen abdeckt, die regelbasierte Werkzeuge nicht erreichen.

---

<!-- skillx:begin:setup-skillx -->
## Mit skillx ausprobieren

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

Führe diesen Skill ohne Installation aus:

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Räum auf meinem Mac auf."
```

Um nur eine Vorschau anstelle einer tatsächlichen Ausführung zu erhalten, hänge `--dry-run` an die Nachricht. Das Skill durchläuft alle sechs Stufen, aber `safe_delete.py` schreibt nichts ins Dateisystem (nur das `actions.jsonl` im workdir).

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Räum auf meinem Mac auf mit --dry-run, nur Vorschau, ohne wirklich etwas zu löschen."
```

Angetrieben von [skillx](https://skillx.run) — ein einziger Befehl, um beliebige Agent-Skills zu holen, zu scannen, zu injizieren und auszuführen.
<!-- skillx:end:setup-skillx -->

---

## Demo

Die Sprache des Reports wird durch die Konversationssprache bestimmt, mit der das Skill ausgelöst wird — eine Sprache pro Lauf. Unten: erster Eindruck, Englisch links, Chinesisch rechts, aus getrennten Läufen.

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="mac-space-cleanup-Report, erster Eindruck, Englisch" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="mac-space-cleanup-Report, erster Eindruck, Chinesisch" /></td>
</tr>
</table>

Vollständiger Report (Wirkungsübersicht · Aufschlüsselung · Detailprotokoll · Beobachtungen · Laufdetails · L1–L4-Risikoverteilung):
[Ganze Seite Englisch](assets/mac-space-cleanup.full.en.png) · [Ganze Seite Chinesisch](assets/mac-space-cleanup.full.zh.png)

---

## Install

Die dauerhafte Installation läuft über skillx. Falls du das skillx-CLI noch nicht hast:

```bash
curl -fsSL https://skillx.run/install.sh | sh
```

Installiere dann dieses Skill in das Skills-Verzeichnis eines beliebigen von skillx erkannten Agent-Harnesses (`~/.claude/skills/` für Claude Code etc.):

```bash
skillx install https://github.com/skillx-run/mac-space-cleanup
```

Öffne eine neue Agent-Sitzung, um die Skill-Liste zu aktualisieren. Für spätere Aktualisierung oder Entfernung: `skillx update mac-space-cleanup` / `skillx uninstall mac-space-cleanup`.

Die Installation von `trash` parallel dazu wird empfohlen (`brew install trash`). Ohne dieses Tool fällt `safe_delete.py` auf `mv` nach `~/.Trash` zurück, und die verschobenen Dateinamen tragen ein Zeitstempel-Suffix.

---

## Use

Sag in deiner Agent-Konversation eine Auslöse-Phrase wie:

| Auslöser | Der Skill wählt |
| --- | --- |
| „schnelle Bereinigung", „mach mir schnell Platz", „kurz durchwischen" | Modus `quick` (räumt risikoarme Punkte automatisch auf, ~30 s) |
| „tiefe Bereinigung", „analysiere den Speicherplatz", „finde die großen Brocken" | Modus `deep` (vollständiges Audit, Bestätigung pro Element für riskante Dinge, ~2–5 min) |
| „räume meinen Mac auf", „mein Mac ist voll" (mehrdeutig) | Der Skill fragt nach dem Modus, mit Zeitschätzungen |

Für eine Vorschau ohne Eingriffe ins Dateisystem hängst du `--dry-run` an die Nachricht an:

> „Räum auf meinem Mac auf mit --dry-run, nur Vorschau, ohne wirklich etwas zu löschen."

Der Report markiert oben den Dry-Run-Status und stellt jeder Zahl ein Äquivalent von „würden freigegeben" voran. RTL-Sprachen (Arabisch, Hebräisch, Persisch) erhalten automatisch `<html dir="rtl">`; feinjustiertes RTL-CSS ist eine bekannte Einschränkung.

---

## Scope

Räumt auf (Risikoeinstufung gemäß `references/category-rules.md`):

- Entwickler-Caches: Xcode DerivedData, Docker build cache, Go build cache, Gradle cache, ccache, sccache, JetBrains, Flutter SDK, Editor-Caches der VSCode-Familie (Code / Cursor / Windsurf / Zed `blob_store`).
- Paketmanager-Caches: Homebrew, npm, pnpm, yarn, pip, uv, Cargo, CocoaPods, RubyGems, Bundler, Composer, Poetry, Dart pub, Bun, Deno, Swift PM, Carthage. Versionsmanager (nvm / fnm / pyenv / rustup) zeigen nicht aktive Einträge pro Version an; aktive Pins werden automatisch aus den `.python-version` / `.nvmrc` jedes Projekts gelesen.
- AI/ML-Modell-Caches: HuggingFace (`hub/` L2 trash, `datasets/` L3 defer), PyTorch hub, Ollama (L3 defer; im deep-Modus dispatcht pro Modell über `ollama:<name>:<tag>` mit Referenzzählung der Blobs, sodass zwischen Tags geteilte Layer das Löschen eines Geschwister-Tags überleben), LM Studio, OpenAI Whisper, globaler Weights-&-Biases-Cache. Nicht-`base`-Envs von Conda / Mamba / Miniforge über die sieben gängigen macOS-Installationslayouts.
- Frontend-Tooling: Playwright-Browser + Driver, von Puppeteer mitgelieferte Browser.
- iOS/watchOS/tvOS-Simulator-Runtimes (über `xcrun simctl delete`, nicht `rm -rf`). iOS-`DeviceSupport/<OS>`-Einträge, deren major.minor mit einem aktuell gekoppelten physischen Gerät oder einer verfügbaren Simulator-Runtime übereinstimmt, werden automatisch auf L3 defer herabgestuft.
- App-Caches unter `~/Library/Caches/*`, saved application state und der Trash selbst. Caches kreativer Anwendungen (Adobe Media Cache / Peak Files, Final Cut Pro, Logic Pro) verwenden spezifische Labels statt des generischen `"System caches"`-Buckets.
- Logs, Absturzberichte.
- Alte Installer in `~/Downloads` (`.dmg / .pkg / .xip / .iso`, älter als 30 Tage).
- Lokale Time-Machine-Snapshots (über `tmutil deletelocalsnapshots`).
- Projekt-Build-Artefakte (nur deep-Modus; gescannt von `scripts/scan_projects.py` für jedes Verzeichnis mit `.git`-Wurzel):
  - L1 löschen: `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` (nur Elixir-Projekte), `Pods`, `vendor` (nur Go-Projekte).
  - L2 in den Trash: `.venv`, `venv`, `env` (Python-venvs — Wheel-Pins reproduzieren eventuell nicht exakt, daher das Recovery-Fenster); `coverage` (Test-Coverage-Reports, gebunden an `package.json` oder einen Python-Marker); `.dvc/cache` (content-adressierter DVC-Cache, gebunden an einen Geschwister-Marker `.dvc/config`; das Elternverzeichnis `.dvc/` enthält Nutzerstatus und bleibt erhalten).
  - System- / Paketmanager-Verzeichnisse (`~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.composer`, `~/.pub-cache`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash`) werden bei der Projekterkennung ausgeschlossen.
- Scan verwaister großer Verzeichnisse (nur deep-Modus): Verzeichnisse unter `~` mit ≥ 2 GiB, die keine andere Regel erfasst hat, werden als L3 defer markiert (`source_label="Unclassified large directory"`). Vor der endgültigen Einstufung führt der Agent eine kurze nur-lesende Untersuchung durch (höchstens 6 Befehle pro Kandidat), um `category` und `source_label` zu verfeinern; die Stufe L3 defer bleibt unabhängig vom Ergebnis gesperrt.

Harter Riegel — verweigert unabhängig vom Inhalt von `confirmed.json`; siehe `_BLOCKED_PATTERNS` in `scripts/safe_delete.py`:

- Verzeichnisse `.git`, `.ssh`, `.gnupg`.
- `~/Library/Keychains`, `~/Library/Mail`, `~/Library/Messages`, `~/Library/Mobile Documents` (iCloud Drive).
- Photos-Mediathek, Apple-Music-Mediathek.
- `.env*`-Dateien, SSH-Schlüsseldateien (`id_rsa`, `id_ed25519`, …).
- Editor-State der VSCode-Familie: `{Code, Cursor, Windsurf}/{User, Backups, History}` (ungespeicherte Änderungen, git-stash-Äquivalente, lokale Bearbeitungshistorie).
- `Auto-Save`-Ordner der kreativen Adobe-Apps — ungespeicherte Premiere- / After-Effects- / Photoshop-Projektdateien.

---

## Architecture

`SKILL.md` ist der Workflow-Vertrag des Agenten: Moduswahl, Klassifikation, Dialog und HTML-Rendering werden vom Agenten erledigt. Zwei Python-Skripte übernehmen die für den Agenten ungeeigneten Aufgaben — `scripts/safe_delete.py` ist der einzige Einstiegspunkt für Schreibvorgänge ins Dateisystem und liefert sechs dispatchte Aktionen, Idempotenz und Fehlerisolation pro Element; `scripts/collect_sizes.py` führt `du -sk` parallel über die Standardbibliothek aus. `references/` ist die Wissensbasis des Agenten, `assets/` enthält Report-Templates. Die Stage 6 lässt eine zweischichtige Reviewer-/Validator-Schicht laufen, die Privatsphären-Lecks abfängt, bevor der Nutzer den Report sieht. Das Arbeitsverzeichnis pro Lauf liegt unter `~/.cache/mac-space-cleanup/run-XXXXXX/`.

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # Haupt-Agent-Workflow (sechs Stufen)
├── scripts/
│   ├── safe_delete.py            # Sechs-Aktions-Dispatcher + Blocklist-Riegel
│   ├── collect_sizes.py          # paralleles du -sk
│   ├── scan_projects.py          # findet .git-wurzelnde Projekte + listet bereinigbare Artefakte
│   ├── aggregate_history.py      # laufübergreifender Konfidenz-Aggregator (Stage 5 HISTORY_BY_LABEL) + run-*-GC
│   ├── validate_report.py        # Prüfung nach dem Rendering (Regionen / Placeholders / Lecks / dry-run-Markierung)
│   ├── smoke.sh                  # Smoke gegen echtes fs
│   └── dry-e2e.sh                # End-to-end-Harness ohne LLM
├── references/
│   ├── cleanup-scope.md          # Whitelist / Blacklist (mit Querverweis auf die safe_delete-Blocklist)
│   ├── safety-policy.md          # L1-L4-Einstufung + Schwärzung + Degradierung
│   ├── category-rules.md         # 10 Kategorien mit Mustern + risk_level + action
│   └── reviewer-prompts.md       # Prompt-Template für den Schwärzungs-Sub-Agenten
├── assets/
│   ├── report-template.html      # HTML-Template mit sechs Regionen und Paar-Markern
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 X-Share-Karte
├── tests/                        # reine Standardbibliotheks-unittest-Suite
├── CHANGELOG.md
├── CLAUDE.md                     # Contributor-Invarianten
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations

- **Kein Undo-Stack.** Wiederherstellungswege sind der native Trash, die `archive/`-tar-Dateien im workdir und das migrate-Zielvolume.
- **Kein cron, kein Hintergrundlauf.** Jeder Lauf wird vom Nutzer ausgelöst.
- **Keine Cloud, keine Telemetrie.** Der workdir bleibt lokal.
- **Keine SIP-geschützten Pfade**, keine Deinstallation von `/Applications/*.app`.
- **Projektwurzel-Erkennung ausschließlich über `.git`.** Standard-git-Checkouts werden erkannt; Projekt-Arbeitsbereiche ohne `.git`-Verzeichnis nicht. Verschachtelte git-Submodule werden dedupliziert und erscheinen nicht als eigene Projekte.
- **Die Artefakt-Erkennung respektiert `.gitignore` nicht** — sie scannt feste Unterverzeichnis-Konventionsnamen (`node_modules`, `target`, …). Kann ein von git ignoriertes Verzeichnis zutage fördern und ein konventionsfremdes Verzeichnis übersehen.
- **Einzelrechner-Validierung.** Entwickelt und getestet auf macOS 25.x / 26.x mit Entwickler-Toolchain. Noch nicht zwischen Apple Silicon und Intel bzw. auf älteren macOS-Versionen validiert.

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # Sanity gegen echtes fs
./scripts/dry-e2e.sh                        # End-to-end ohne LLM
```

Die CI führt alle drei bei jedem push / PR über `.github/workflows/ci.yml` auf `macos-latest` aus.

Für nicht verhandelbare Invarianten (der Agent schreibt nicht direkt aufs fs, Schwärzung ist Pflicht usw.) siehe `CLAUDE.md`, für Release-Notes `CHANGELOG.md`.

---

## License

Apache-2.0 (siehe `LICENSE` und `NOTICE`).

## Credits

Entworfen und gebaut von [@heyiamlin](https://x.com/heyiamlin). Wenn dir der Skill Speicher gespart hat, teile ihn mit dem Hashtag `#macspaceclean`.
