# mac-space-cleanup · macOS cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · **Español** · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

Un **skill** que limpia el espacio en disco de tu Mac — cauto, honesto, multietapa.

> El skill conduce al agente a través de una limpieza en siete etapas (modo → sondeo → escaneo → clasificación → confirmación → informe → apertura) con **clasificación de riesgo L1–L4**, **contabilidad honesta del espacio recuperado** (dividida en `freed_now` / `pending_in_trash` / `archived`) y **múltiples barreras de seguridad** (una blocklist determinista en código, un sub-agente revisor de privacidad y un validador post-render). Cero dependencias de pip — solo comandos de macOS y la biblioteca estándar de Python.

---

<!-- skillx:begin:setup-skillx -->
## Pruébalo con skillx

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

Ejecuta este skill sin instalar nada:

```bash
skillx run https://github.com/skillx-run/mac-space-cleanup "Libera espacio en mi Mac."
```

Con tecnología de [skillx](https://skillx.run) — descarga, escanea, inyecta y limpia cualquier agent skill con un solo comando.
<!-- skillx:end:setup-skillx -->

---

## Demo

El informe se **localiza** al idioma con el que se active el skill — un idioma por ejecución, sin conmutador en tiempo de ejecución. Si lo activas en inglés → informe en inglés; en chino → informe en chino; en japonés, español, francés, etc. → ese idioma. A continuación: impresión de la primera vista (EN a la izquierda, ZH a la derecha, cada una de una ejecución distinta), seguida de los enlaces a las capturas de página completa. Actualmente solo proporcionamos capturas en inglés y chino como muestra; el skill genera el informe completo en **el idioma de esta página** (español) cuando lo activas así.

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="Informe mac-space-cleanup, primera vista, inglés" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="Informe mac-space-cleanup, primera vista, chino" /></td>
</tr>
</table>

Informe completo (Resumen de impacto · Desglose · Registro detallado · Observaciones · Detalles de ejecución · Distribución de riesgo L1–L4):
[Página completa en inglés](assets/mac-space-cleanup.full.en.png) · [Página completa en chino](assets/mac-space-cleanup.full.zh.png)

---

## Install

Cualquier harness de agente que cargue skills puede usarlo. El fragmento de abajo utiliza la ruta habitual `~/.claude/skills/`; adáptala al directorio de skills de tu harness si usas otro.

```bash
git clone git@github.com:skillx-run/mac-space-cleanup.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-cleanup" ~/.claude/skills/mac-space-cleanup
```

Recarga tu harness para que la lista de skills tome la entrada nueva (en la mayoría de los harnesses: abre una nueva sesión).

### Recommended optional dependency

```bash
brew install trash
```

Si falta el CLI `trash`, `safe_delete.py` recurre a mover al `~/.Trash` con `mv` (añadiendo un sufijo `-<timestamp>`) — funciona, pero el sufijo queda raro en Finder. El propio skill te lo recordará en la primera ejecución.

---

## Use

En tu conversación con el agente, di algo como:

| Tú dices… | El skill elige |
| --- | --- |
| «limpieza rápida», «libera espacio ya», «hazme una pasada rápida» | modo `quick` (limpia automáticamente los elementos de bajo riesgo, ~30 s) |
| «limpieza profunda», «analiza el espacio», «busca los pesos pesados» | modo `deep` (auditoría completa, pregunta ítem por ítem lo arriesgado, ~2–5 min) |
| «limpia mi Mac», «mi Mac está lleno» (ambiguo) | El skill te pregunta cuál eliges, con estimaciones de tiempo |

Para previsualizar sin tocar el sistema de archivos, añade `--dry-run` a tu mensaje:

> «haz una limpieza profunda de mi Mac pero con el modo --dry-run, sin borrar nada de verdad»

El informe indicará visiblemente `DRY-RUN — no files touched` en la parte superior (localizado al idioma con el que lo activaste) y antepondrá a cada número el equivalente en tu idioma de «se liberarían».

### Report language

El informe HTML es de **un único idioma por ejecución**, producido en el idioma con el que activaste el skill. El agente detecta el idioma de la conversación a partir del mensaje desencadenante, escribe su valor (un sub-tag BCP-47 como `en`, `zh`, `ja`, `es`, `ar`) en el workdir, y luego redacta cada nodo de lenguaje natural — título principal, razones de las acciones, observaciones, representaciones de source_label, prosa de dry-run — directamente en ese idioma. Las etiquetas estáticas (títulos de sección, textos de botones, cabeceras de columnas) vienen con una base en inglés en la plantilla; para ejecuciones no inglesas el agente las traduce una sola vez a un diccionario embebido que hidrata la página al cargar. Sin conmutador en tiempo de ejecución, sin DOM bilingüe — gana el idioma de la conversación.

Los idiomas de derecha a izquierda (árabe, hebreo, persa) reciben `<html dir="rtl">`; la inversión básica de dirección funciona, pero el ajuste fino de CSS RTL es una limitación conocida.

---

## What it touches (and never touches)

**Limpia** (con clasificación de riesgo según `references/category-rules.md`):

- Cachés de desarrollador: Xcode DerivedData, Docker build cache, Go build cache, Gradle cache, ccache, sccache.
- Cachés de gestores de paquetes: Homebrew, npm, pnpm, yarn, pip, uv, Cargo, CocoaPods, RubyGems, Bundler, Composer, Poetry, Dart pub.
- Runtimes de simuladores iOS/watchOS/tvOS (vía `xcrun simctl delete`, **nunca `rm -rf`**).
- Cachés de aplicaciones bajo `~/Library/Caches/*`, saved application state y la propia Trash.
- Logs, informes de fallos.
- Instaladores antiguos en `~/Downloads` (`.dmg / .pkg / .xip / .iso` con más de 30 días).
- Instantáneas locales de Time Machine (vía `tmutil deletelocalsnapshots`).
- **Artefactos de build de proyectos** (solo modo deep, escaneados por `scripts/scan_projects.py` para cualquier directorio con raíz `.git`):
  - L1 borrado: `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` (solo proyectos Elixir), `Pods`, `vendor` (solo proyectos Go).
  - L2 a Trash: `.venv`, `venv`, `env` (entornos virtuales de Python — los pins de wheel pueden no reproducirse; por eso la ventana de recuperación); `coverage` (informes de cobertura de tests, condicionado a `package.json` o un marker de Python).
  - Directorios de sistema / gestor de paquetes (`~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.composer`, `~/.pub-cache`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash`) se podan durante el descubrimiento de proyectos.
- **El modo deep también saca a la luz directorios bajo `~` de ≥ 2 GiB que ninguna otra regla capturó** (L3 defer, `source_label="Unclassified large directory"`), para que los verdaderos devoradores de disco huérfanos queden visibles para revisión manual.

**Barrera dura — rechaza pase lo que pase en `confirmed.json`** (ver `_BLOCKED_PATTERNS` en `scripts/safe_delete.py`):

- Directorios `.git`, `.ssh`, `.gnupg`.
- `~/Library/Keychains`, `~/Library/Mail`, `~/Library/Messages`, `~/Library/Mobile Documents` (iCloud Drive).
- Biblioteca de Photos, biblioteca de Apple Music.
- Ficheros `.env*`, claves SSH (`id_rsa`, `id_ed25519`, …).

El propio agente lee `references/cleanup-scope.md` para la whitelist/blacklist orientada al usuario — la blocklist anterior es el subconjunto que se fuerza en runtime.

---

## Architecture (one paragraph)

`SKILL.md` es el contrato del flujo de trabajo — el agente se encarga del juicio (elección de modo, clasificación, conversación, renderizado HTML). Dos scripts pequeños de Python hacen lo que el agente no debe: `scripts/safe_delete.py` es la **única** ruta por la que ocurren escrituras en el fs (seis acciones despachadas: delete / trash / archive / migrate / defer / skip; idempotente; aislamiento de errores por ítem; `actions.jsonl` solo-append); `scripts/collect_sizes.py` ejecuta `du -sk` en paralelo con un timeout de 30 s por ruta y salida JSON estructurada. Tres documentos de referencia (`references/`) son la base de conocimiento del agente. Tres plantillas de asset (`assets/`) son el esqueleto del informe que el agente rellena. Dos capas reviewer/validator en la Stage 6 atrapan filtraciones de privacidad antes de que el usuario vea el informe. El workdir por ejecución vive en `~/.cache/mac-space-cleanup/run-XXXXXX/`.

---

## Honesty contract

Toda herramienta de limpieza infla su número de «N GB liberados» contando también lo que empuja a la Trash. macOS no libera ese disco hasta que vacías `~/.Trash`. Este skill divide la métrica:

- `freed_now_bytes` — realmente fuera del disco (delete + migrate a otro volumen).
- `pending_in_trash_bytes` — dentro de `~/.Trash`; el informe muestra una línea `osascript` para vaciarla.
- `archived_source_bytes` / `archived_count` — bytes envueltos en un tar dentro del workdir.
- `reclaimed_bytes` — alias retrocompatible = `freed_now + pending_in_trash`. El texto para compartir y el titular del informe usan `freed_now_bytes`, no esto.

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # flujo principal del agente (siete etapas)
├── scripts/
│   ├── safe_delete.py            # despachador de seis acciones + blocklist de seguridad
│   ├── collect_sizes.py          # du -sk en paralelo
│   ├── scan_projects.py          # encuentra proyectos con raíz .git + enumera artefactos limpiables
│   ├── aggregate_history.py      # agregador de confianza cruzada (Stage 5 HISTORY_BY_LABEL) + GC de run-*
│   ├── validate_report.py        # check post-render (regiones / placeholders / filtraciones / marca dry-run)
│   ├── smoke.sh                  # smoke sobre fs real
│   └── dry-e2e.sh                # harness end-to-end sin LLM
├── references/
│   ├── cleanup-scope.md          # whitelist / blacklist (con referencia cruzada a la blocklist de safe_delete)
│   ├── safety-policy.md          # clasificación L1-L4 + secreto + degradación
│   ├── category-rules.md         # 10 categorías con patrones + risk_level + action
│   └── reviewer-prompts.md       # plantilla de prompt para el sub-agente revisor
├── assets/
│   ├── report-template.html      # esqueleto HTML de seis regiones con marcadores pareados
│   ├── report.css
│   └── share-card-template.svg   # tarjeta para compartir en X 1200×630
├── tests/                        # suite unittest solo biblioteca estándar
├── CHANGELOG.md
├── CLAUDE.md                     # invariantes para contribuidores
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations & non-goals (v0.10.0)

- **Sin pila de undo.** Las vías de recuperación son la Trash nativa, los tar en `archive/` del workdir y el volumen destino del migrate.
- **Sin cron / sin ejecuciones en segundo plano.** Cada ejecución la activa el usuario.
- **Sin nube / sin telemetría.** El workdir se queda en local.
- **Sin rutas protegidas por SIP**, sin desinstalar `/Applications/*.app`.
- **La identificación de raíz de proyecto usa solo `.git`.** Los checkouts de git desnudos se reconocen; los workspaces sin directorio `.git`, no. Los submódulos anidados se deduplican (no aparecen como proyectos separados).
- **El descubrimiento de artefactos no respeta `.gitignore`** — escanea por nombres fijos de subdirectorios convencionales (`node_modules`, `target`, …). Puede sacar a la luz un directorio ignorado por git o pasar por alto uno que el proyecto crea fuera de convención.
- **Validación en una única máquina.** Construido y probado sobre macOS 25.x / 26.x con cadena de herramientas de desarrollo. Los patrones aún no se han validado entre Apple Silicon e Intel, ni en versiones antiguas de macOS.

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # sanity sobre fs real
./scripts/dry-e2e.sh                        # end-to-end sin LLM
```

La CI ejecuta los tres en cada push / PR vía `.github/workflows/ci.yml` sobre `macos-latest`.

Consulta `CLAUDE.md` para los invariantes innegociables (el agente no escribe directamente en el fs, el secreto es obligatorio, etc.) y `CHANGELOG.md` para las notas de versión.

---

## License

Apache-2.0 (ver `LICENSE` y `NOTICE`).

## Credits

Diseñado e implementado por [@heyiamlin](https://x.com/heyiamlin). Si el skill te ahorró espacio, compártelo con el hashtag `#macspaceclean`.
