# mac-space-cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · **Español** · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

Un skill que limpia el espacio en disco de tu Mac.

> Flujo de trabajo en seis etapas: selección de modo, sondeo del entorno, escaneo, clasificación, confirmación, informe. Cada candidato se clasifica como L1-L4; todas las escrituras al sistema de archivos se enrutan a través de `safe_delete.py`, que incorpora una blocklist interna y se combina con un sub-agente revisor de privacidad y un validador post-render formando tres capas de protección. Los bytes pendientes de vaciar en la Trash se contabilizan por separado y no se incluyen en el total «liberado». Cero dependencias de pip — solo comandos de macOS y la biblioteca estándar de Python.

---

## Por qué este skill

Los limpiadores basados en reglas (CleanMyMac, OnyX) solo manejan elementos que sus reglas pueden nombrar: si un determinado `node_modules` sigue en uso, qué directorios bajo `~/Library/Caches` corresponden a preferencias activas del usuario y cuáles son residuos — estos juicios escapan a las reglas, así que estas herramientas los omiten de forma conservadora y dejan atrás un volumen considerable de espacio recuperable.

Delegar la limpieza directamente a un agente («Claude, limpia mi Mac») cubre esas zonas grises, pero sin límites estrictos un solo error de juicio puede alcanzar `.git` / `.env` / Keychains.

Este skill establece primero el límite de seguridad: la blocklist de `safe_delete.py`, el revisor de privacidad y el validador post-render forman tres barreras que rechazan en tiempo de ejecución las rutas mencionadas. Bajo esa premisa, el juicio se delega íntegramente al agente, que cubre las zonas grises a las que las herramientas basadas en reglas no llegan.

---

<!-- skillx:begin:setup-skillx -->
## Pruébalo con skillx

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

Ejecuta este skill sin instalar nada:

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Libera espacio en mi Mac."
```

Para previsualizar en lugar de ejecutar realmente, añade `--dry-run` al mensaje. El skill recorre las seis etapas, pero `safe_delete.py` no escribe nada en el sistema de archivos (solo el `actions.jsonl` del workdir).

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Libera espacio en mi Mac con --dry-run, solo vista previa, sin borrar nada de verdad."
```

Con tecnología de [skillx](https://skillx.run) — un único comando para descargar, escanear, inyectar y ejecutar cualquier agent skill.
<!-- skillx:end:setup-skillx -->

---

## Demo

El idioma del informe lo determina el idioma de conversación con el que se activa el skill — un idioma por ejecución. A continuación: la primera vista, inglés a la izquierda, chino a la derecha, procedentes de ejecuciones distintas.

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

Cualquier harness de agente que cargue skills puede usarlo. El comando siguiente utiliza `~/.claude/skills/` como ruta de ejemplo; si tu harness usa un directorio de skills distinto, sustitúyelo por la ruta correspondiente.

```bash
git clone git@github.com:skillx-run/mac-space-cleanup.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-cleanup" ~/.claude/skills/mac-space-cleanup
```

A continuación, abre una nueva sesión del agente para refrescar la lista de skills.

Se recomienda instalar también `trash` (`brew install trash`). Sin él, `safe_delete.py` recurre a `mv` para mover los archivos a `~/.Trash`, y los nombres movidos llevan un sufijo de marca de tiempo.

---

## Use

En tu conversación con el agente, usa una frase de activación como:

| Frase de activación | El skill elige |
| --- | --- |
| «limpieza rápida», «libera espacio ya», «hazme una pasada rápida» | modo `quick` (limpia automáticamente los elementos de bajo riesgo, ~30 s) |
| «limpieza profunda», «analiza el espacio», «busca los pesos pesados» | modo `deep` (auditoría completa, confirmación ítem por ítem para los elementos de riesgo, ~2–5 min) |
| «limpia mi Mac», «mi Mac está lleno» (ambiguo) | El skill pregunta cuál eliges, con estimaciones de tiempo |

Para previsualizar sin tocar el sistema de archivos, añade `--dry-run` a tu mensaje:

> «Libera espacio en mi Mac con --dry-run, solo vista previa, sin borrar nada de verdad.»

El informe marca el estado de dry-run en la parte superior y antepone a cada cifra un calificador equivalente a «se liberarían». Los idiomas RTL (árabe, hebreo, persa) reciben `<html dir="rtl">` automáticamente; el ajuste fino del CSS RTL es una limitación conocida.

---

## Scope

Limpia (clasificación de riesgo según `references/category-rules.md`):

- Cachés de desarrollador: Xcode DerivedData, Docker build cache, Go build cache, Gradle cache, ccache, sccache, JetBrains, Flutter SDK, cachés de editores de la familia VSCode (Code / Cursor / Windsurf / Zed `blob_store`).
- Cachés de gestores de paquetes: Homebrew, npm, pnpm, yarn, pip, uv, Cargo, CocoaPods, RubyGems, Bundler, Composer, Poetry, Dart pub, Bun, Deno, Swift PM, Carthage. Los gestores de versiones (nvm / fnm / pyenv / rustup) muestran las entradas no activas por versión; los pins activos quedan excluidos automáticamente vía `.python-version` / `.nvmrc` de cada proyecto.
- Cachés de modelos de AI/ML: HuggingFace (`hub/` L2 trash, `datasets/` L3 defer), PyTorch hub, Ollama (L3 defer; en modo deep se despacha por modelo con `ollama:<name>:<tag>` usando conteo de referencias de blobs, de modo que las capas compartidas entre tags sobreviven al borrado de una etiqueta hermana), LM Studio, OpenAI Whisper, caché global de Weights & Biases. Envs no-`base` de Conda / Mamba / Miniforge a través de las siete layouts de instalación comunes en macOS.
- Herramientas frontend: navegadores + driver de Playwright, navegadores empaquetados de Puppeteer.
- Runtimes de simuladores iOS/watchOS/tvOS (vía `xcrun simctl delete`, no `rm -rf`). Las entradas `DeviceSupport/<OS>` de iOS cuyo major.minor coincida con un dispositivo emparejado o un runtime de simulador disponible se degradan automáticamente a L3 defer.
- Cachés de aplicaciones bajo `~/Library/Caches/*`, saved application state y la propia Trash. Las cachés de aplicaciones creativas (Adobe Media Cache / Peak Files, Final Cut Pro, Logic Pro) usan etiquetas específicas en lugar del bucket genérico `"System caches"`.
- Logs, informes de fallos.
- Instaladores antiguos en `~/Downloads` (`.dmg / .pkg / .xip / .iso` con más de 30 días).
- Instantáneas locales de Time Machine (vía `tmutil deletelocalsnapshots`).
- Artefactos de build de proyectos (solo modo deep; escaneados por `scripts/scan_projects.py` en cualquier directorio con raíz `.git`):
  - L1 borrado: `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` (solo proyectos Elixir), `Pods`, `vendor` (solo proyectos Go).
  - L2 a Trash: `.venv`, `venv`, `env` (entornos virtuales de Python — los pins de wheel pueden no reproducirse, por lo que se preserva una ventana de recuperación); `coverage` (informes de cobertura de tests, condicionado a `package.json` o un marker de Python); `.dvc/cache` (caché content-addressed de DVC, condicionada a un marker hermano `.dvc/config`; el padre `.dvc/` contiene estado del usuario y se preserva).
  - Directorios de sistema / gestor de paquetes (`~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.composer`, `~/.pub-cache`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash`) se podan durante el descubrimiento de proyectos.
- Escaneo de directorios huérfanos grandes (solo modo deep): los directorios bajo `~` ≥ 2 GiB que ninguna otra regla capturó se marcan como L3 defer (`source_label="Unclassified large directory"`). Antes de la clasificación final, el agente ejecuta una breve investigación de solo lectura (hasta 6 comandos por candidato) para refinar `category` y `source_label`; el grado L3 defer queda bloqueado independientemente del resultado.

Barrera dura — rechaza independientemente de lo que contenga `confirmed.json`; ver `_BLOCKED_PATTERNS` en `scripts/safe_delete.py`:

- Directorios `.git`, `.ssh`, `.gnupg`.
- `~/Library/Keychains`, `~/Library/Mail`, `~/Library/Messages`, `~/Library/Mobile Documents` (iCloud Drive).
- Biblioteca de Photos, biblioteca de Apple Music.
- Ficheros `.env*`, claves SSH (`id_rsa`, `id_ed25519`, …).
- Estado de editores de la familia VSCode: `{Code, Cursor, Windsurf}/{User, Backups, History}` (ediciones no guardadas, equivalentes a git-stash, historial local de ediciones).
- Carpetas `Auto-Save` de las apps creativas de Adobe — proyectos no guardados de Premiere / After Effects / Photoshop.

---

## Architecture

`SKILL.md` es el contrato de flujo de trabajo del agente: la elección de modo, la clasificación, la conversación y el renderizado HTML los realiza el agente. Dos scripts de Python asumen las responsabilidades inadecuadas para el agente — `scripts/safe_delete.py` es el único punto de entrada para las escrituras al sistema de archivos, y proporciona seis acciones despachadas, idempotencia y aislamiento de errores por ítem; `scripts/collect_sizes.py` ejecuta `du -sk` en paralelo usando la biblioteca estándar. `references/` es la base de conocimiento del agente, `assets/` contiene plantillas de informe. La Stage 6 ejecuta una capa reviewer / validator de dos niveles que intercepta filtraciones de privacidad antes de que el usuario vea el informe. El directorio de trabajo por ejecución reside en `~/.cache/mac-space-cleanup/run-XXXXXX/`.

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # flujo principal del agente (seis etapas)
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
│   ├── report-template.html      # plantilla HTML de seis regiones con marcadores pareados
│   ├── report.css
│   └── share-card-template.svg   # tarjeta para compartir en X 1200×630
├── tests/                        # suite unittest solo biblioteca estándar
├── CHANGELOG.md
├── CLAUDE.md                     # invariantes para contribuidores
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations

- **Sin pila de undo.** Las vías de recuperación son la Trash nativa, los tar en `archive/` del workdir y el volumen destino del migrate.
- **Sin cron, sin ejecuciones en segundo plano.** Cada ejecución la inicia el usuario.
- **Sin nube, sin telemetría.** El workdir se queda en local.
- **Sin rutas protegidas por SIP**, sin desinstalar `/Applications/*.app`.
- **La identificación de raíz de proyecto usa solo `.git`.** Los checkouts de git estándar se reconocen; los workspaces sin directorio `.git` no. Los submódulos anidados se deduplican y no aparecen como proyectos separados.
- **El descubrimiento de artefactos no respeta `.gitignore`** — escanea por nombres fijos de subdirectorios convencionales (`node_modules`, `target`, …). Puede incluir un directorio ignorado por git o pasar por alto uno que el proyecto crea fuera de convención.
- **Validación en una única máquina.** Construido y probado sobre macOS 25.x / 26.x con cadena de herramientas de desarrollo. Aún no validado entre Apple Silicon e Intel ni entre versiones anteriores de macOS.

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
