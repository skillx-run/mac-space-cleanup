# mac-space-cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [Español](README.es.md) · **Français** · [العربية](README.ar.md) · [Deutsch](README.de.md)

Un skill qui nettoie l'espace disque de votre Mac.

> Workflow en six étapes : choix du mode, sondage de l'environnement, scan, classification, confirmation, rapport. Chaque candidat reçoit un classement L1-L4 ; toutes les écritures dans le système de fichiers passent par `safe_delete.py`, qui embarque une blocklist interne et se combine avec un sous-agent relecteur de confidentialité et un validateur post-rendu pour former trois couches de garde-fous. Les octets en attente de vidage dans la Trash sont comptés séparément et n'entrent pas dans le total « libéré ». Zéro dépendance pip — uniquement des commandes macOS et la bibliothèque standard de Python.

---

## Pourquoi ce skill

Les nettoyeurs basés sur des règles (CleanMyMac, OnyX) ne traitent que les éléments que leurs règles savent nommer : si un `node_modules` donné est encore utilisé, quels répertoires sous `~/Library/Caches` correspondent à des préférences utilisateur actives plutôt qu'à des résidus — ces jugements échappent aux règles, donc ces outils les sautent prudemment et laissent derrière eux un volume notable d'espace récupérable.

Déléguer le nettoyage directement à un agent (« Claude, nettoie mon Mac ») couvre ces zones grises, mais sans frontière dure une seule erreur de jugement peut atteindre `.git` / `.env` / Keychains.

Ce skill établit d'abord la frontière de sécurité : la blocklist de `safe_delete.py`, le relecteur de confidentialité et le validateur post-rendu forment trois garde-fous qui refusent ces chemins clés à l'exécution. Sous cette condition, le jugement est intégralement délégué à l'agent, qui couvre les zones grises hors de portée des outils basés sur des règles.

---

<!-- skillx:begin:setup-skillx -->
## Essayez-le avec skillx

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

Exécutez ce skill sans rien installer :

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Libère de l'espace sur mon Mac."
```

Pour prévisualiser plutôt que d'exécuter réellement, ajoutez `--dry-run` au message. Le skill exécute les six étapes, mais `safe_delete.py` n'écrit rien dans le système de fichiers (uniquement le `actions.jsonl` du workdir).

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Libère de l'espace sur mon Mac avec --dry-run, juste un aperçu, sans rien supprimer pour de vrai."
```

Propulsé par [skillx](https://skillx.run) — une seule commande pour récupérer, scanner, injecter et exécuter n'importe quel agent skill.
<!-- skillx:end:setup-skillx -->

---

## Demo

La langue du rapport est déterminée par la langue de conversation utilisée pour déclencher le skill — une langue par exécution. Ci-dessous : la première vue, anglais à gauche, chinois à droite, issues d'exécutions distinctes.

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="Rapport mac-space-cleanup, première vue, anglais" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="Rapport mac-space-cleanup, première vue, chinois" /></td>
</tr>
</table>

Rapport complet (Résumé d'impact · Répartition · Journal détaillé · Observations · Détails d'exécution · Distribution de risque L1–L4) :
[Page complète en anglais](assets/mac-space-cleanup.full.en.png) · [Page complète en chinois](assets/mac-space-cleanup.full.zh.png)

---

## Install

L'installation persistante passe par skillx. Si vous n'avez pas encore le CLI skillx :

```bash
curl -fsSL https://skillx.run/install.sh | sh
```

Installez ensuite ce skill dans le répertoire de skills de n'importe quel harness d'agent reconnu par skillx (`~/.claude/skills/` pour Claude Code, etc.) :

```bash
skillx install https://github.com/skillx-run/mac-space-cleanup
```

Ouvrez une nouvelle session de l'agent pour rafraîchir la liste des skills. Pour mettre à jour ou désinstaller par la suite : `skillx update mac-space-cleanup` / `skillx uninstall mac-space-cleanup`.

L'installation de `trash` est recommandée en parallèle (`brew install trash`). Sans lui, `safe_delete.py` se rabat sur `mv` vers `~/.Trash`, et les noms des fichiers déplacés portent un suffixe d'horodatage.

---

## Use

Dans votre conversation avec l'agent, utilisez une phrase déclenchante telle que :

| Phrase déclenchante | Le skill choisit |
| --- | --- |
| « nettoyage rapide », « libère de la place », « fais un petit coup de balai » | mode `quick` (nettoie automatiquement les éléments à faible risque, ~30 s) |
| « nettoyage profond », « analyse l'espace », « trouve les gros morceaux » | mode `deep` (audit complet, confirmation élément par élément pour le risqué, ~2–5 min) |
| « nettoie mon Mac », « mon Mac est plein » (ambigu) | Le skill vous demande de choisir, avec des estimations de temps |

Pour prévisualiser sans toucher au système de fichiers, ajoutez `--dry-run` à votre message :

> « Libère de l'espace sur mon Mac avec --dry-run, juste un aperçu, sans rien supprimer pour de vrai. »

Le rapport indique l'état dry-run en haut et préfixe chaque chiffre par un équivalent de « seraient libérés ». Les langues RTL (arabe, hébreu, persan) reçoivent automatiquement `<html dir="rtl">` ; l'ajustement fin du CSS RTL est une limitation connue.

---

## Scope

Nettoie (classement de risque selon `references/category-rules.md`) :

- Caches développeur : Xcode DerivedData, Docker build cache, Go build cache, Gradle cache, ccache, sccache, JetBrains, Flutter SDK, caches des éditeurs de la famille VSCode (Code / Cursor / Windsurf / Zed `blob_store`).
- Caches de gestionnaires de paquets : Homebrew, npm, pnpm, yarn, pip, uv, Cargo, CocoaPods, RubyGems, Bundler, Composer, Poetry, Dart pub, Bun, Deno, Swift PM, Carthage. Les gestionnaires de versions (nvm / fnm / pyenv / rustup) font remonter les entrées non actives par version ; les pins actifs sont automatiquement exclus via les `.python-version` / `.nvmrc` de chaque projet.
- Caches de modèles AI/ML : HuggingFace (`hub/` en L2 trash, `datasets/` en L3 defer), PyTorch hub, Ollama (L3 defer ; en mode deep, dispatch par modèle via `ollama:<name>:<tag>` avec comptage de références de blobs, de sorte que les couches partagées entre tags survivent à la suppression d'un tag frère), LM Studio, OpenAI Whisper, cache global Weights & Biases. Envs non `base` de Conda / Mamba / Miniforge sur les sept layouts d'installation courants sous macOS.
- Outils frontend : navigateurs + driver de Playwright, navigateurs embarqués de Puppeteer.
- Runtimes des simulateurs iOS/watchOS/tvOS (via `xcrun simctl delete`, et non `rm -rf`). Les entrées `DeviceSupport/<OS>` d'iOS dont le major.minor correspond à un appareil appairé ou à un runtime de simulateur disponible sont automatiquement rétrogradées en L3 defer.
- Caches d'applications sous `~/Library/Caches/*`, saved application state et la Trash elle-même. Les caches des applications créatives (Adobe Media Cache / Peak Files, Final Cut Pro, Logic Pro) utilisent des étiquettes spécifiques plutôt que le bucket générique `"System caches"`.
- Journaux, rapports de crash.
- Anciens installateurs dans `~/Downloads` (`.dmg / .pkg / .xip / .iso` de plus de 30 jours).
- Instantanés locaux Time Machine (via `tmutil deletelocalsnapshots`).
- Artéfacts de build de projets (mode deep uniquement ; scannés par `scripts/scan_projects.py` pour tout répertoire ayant une racine `.git`) :
  - L1 suppression : `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` (projets Elixir uniquement), `Pods`, `vendor` (projets Go uniquement).
  - L2 vers Trash : `.venv`, `venv`, `env` (venvs Python — les pins de wheels peuvent ne pas se reproduire ; d'où la fenêtre de récupération) ; `coverage` (rapports de couverture de tests, conditionnés à `package.json` ou un marker Python) ; `.dvc/cache` (cache content-addressed de DVC, conditionné à un marker frère `.dvc/config` ; le parent `.dvc/` contient l'état utilisateur et est préservé).
  - Répertoires système / gestionnaires de paquets (`~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.composer`, `~/.pub-cache`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash`) sont élagués lors de la découverte de projets.
- Scan des grands répertoires orphelins (mode deep uniquement) : les répertoires sous `~` ≥ 2 Gio qu'aucune autre règle n'a capturés sont marqués L3 defer (`source_label="Unclassified large directory"`). Avant la classification finale, l'agent lance une brève investigation en lecture seule (au plus 6 commandes par candidat) pour affiner `category` et `source_label` ; le niveau L3 defer reste verrouillé quel que soit le résultat.

Garde-fou dur — refuse quel que soit le contenu de `confirmed.json` ; voir `_BLOCKED_PATTERNS` dans `scripts/safe_delete.py` :

- Répertoires `.git`, `.ssh`, `.gnupg`.
- `~/Library/Keychains`, `~/Library/Mail`, `~/Library/Messages`, `~/Library/Mobile Documents` (iCloud Drive).
- Bibliothèque Photos, bibliothèque Apple Music.
- Fichiers `.env*`, clés SSH (`id_rsa`, `id_ed25519`, …).
- État des éditeurs de la famille VSCode : `{Code, Cursor, Windsurf}/{User, Backups, History}` (éditions non sauvegardées, équivalents de git-stash, historique local d'édition).
- Dossiers `Auto-Save` des apps créatives d'Adobe — projets non sauvegardés de Premiere / After Effects / Photoshop.

---

## Architecture

`SKILL.md` est le contrat de workflow de l'agent : choix du mode, classification, conversation et rendu HTML sont exécutés par l'agent. Deux scripts Python prennent en charge les responsabilités peu adaptées à l'agent — `scripts/safe_delete.py` est l'unique point d'entrée des écritures sur le système de fichiers, fournissant six actions dispatchées, l'idempotence et l'isolation des erreurs par élément ; `scripts/collect_sizes.py` exécute `du -sk` en parallèle via la bibliothèque standard. `references/` est la base de connaissances de l'agent, `assets/` contient les modèles de rapport. La Stage 6 fait tourner une couche reviewer / validator à deux niveaux qui intercepte les fuites de confidentialité avant que l'utilisateur ne voie le rapport. Le répertoire de travail par exécution se trouve dans `~/.cache/mac-space-cleanup/run-XXXXXX/`.

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # workflow principal de l'agent (six étapes)
├── scripts/
│   ├── safe_delete.py            # dispatcher six actions + blocklist de secours
│   ├── collect_sizes.py          # du -sk en parallèle
│   ├── scan_projects.py          # trouve les projets à racine .git + énumère les artefacts nettoyables
│   ├── aggregate_history.py      # agrégateur de confiance inter-exécutions (Stage 5 HISTORY_BY_LABEL) + GC run-*
│   ├── validate_report.py        # vérification post-rendu (régions / placeholders / fuites / marquage dry-run)
│   ├── smoke.sh                  # smoke sur fs réel
│   └── dry-e2e.sh                # harness end-to-end sans LLM
├── references/
│   ├── cleanup-scope.md          # whitelist / blacklist (avec renvoi croisé vers la blocklist safe_delete)
│   ├── safety-policy.md          # classement L1-L4 + caviardage + dégradation
│   ├── category-rules.md         # 10 catégories avec patterns + risk_level + action
│   └── reviewer-prompts.md       # template de prompt pour le sous-agent relecteur
├── assets/
│   ├── report-template.html      # modèle HTML à six régions avec marqueurs appariés
│   ├── report.css
│   └── share-card-template.svg   # carte de partage X 1200×630
├── tests/                        # suite unittest standard-library pure
├── CHANGELOG.md
├── CLAUDE.md                     # invariants pour les contributeurs
└── .github/workflows/ci.yml      # macos-latest : tests + smoke + dry-e2e
```

---

## Limitations

- **Pas de pile d'undo.** Les voies de récupération sont la Trash native, les tars dans `archive/` du workdir et le volume cible du migrate.
- **Pas de cron, pas d'exécution en arrière-plan.** Chaque run est déclenchée par l'utilisateur.
- **Pas de cloud, pas de télémétrie.** Le workdir reste local.
- **Pas de chemins protégés par SIP**, pas de désinstallation de `/Applications/*.app`.
- **L'identification de la racine de projet utilise uniquement `.git`.** Les checkouts git standards sont reconnus ; les workspaces sans répertoire `.git` ne le sont pas. Les submodules git imbriqués sont dédoublonnés et n'apparaissent pas comme des projets séparés.
- **La découverte d'artefacts ne respecte pas `.gitignore`** — elle scanne des noms fixes de sous-répertoires conventionnels (`node_modules`, `target`, …). Peut faire remonter un répertoire ignoré par git, peut rater un répertoire non conventionnel du projet.
- **Validation sur une seule machine.** Construit et testé sur macOS 25.x / 26.x avec une toolchain de développement. Pas encore validé entre Apple Silicon et Intel, ni sur d'anciennes versions de macOS.

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # sanity fs réel
./scripts/dry-e2e.sh                        # end-to-end sans LLM
```

La CI exécute les trois à chaque push / PR via `.github/workflows/ci.yml` sur `macos-latest`.

Voir `CLAUDE.md` pour les invariants non négociables (l'agent n'écrit pas directement sur le fs, le caviardage est obligatoire, etc.) et `CHANGELOG.md` pour les notes de version.

---

## License

Apache-2.0 (voir `LICENSE` et `NOTICE`).

## Credits

Conçu et construit par [@heyiamlin](https://x.com/heyiamlin). Si le skill vous a fait gagner de la place, partagez-le avec le hashtag `#macspaceclean`.
