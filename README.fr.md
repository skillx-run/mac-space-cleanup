# mac-space-cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [Español](README.es.md) · **Français** · [العربية](README.ar.md) · [Deutsch](README.de.md)

Un **skill** qui nettoie l'espace disque de votre Mac — prudent, honnête, multi-étapes.

> Le skill guide l'agent à travers un nettoyage en sept étapes (mode → sondage → scan → classification → confirmation → rapport → ouverture) avec un **classement de risque L1–L4**, une **comptabilité honnête de l'espace récupéré** (scindée en `freed_now` / `pending_in_trash` / `archived`) et **plusieurs garde-fous de sécurité** (une blocklist déterministe dans le code, un sous-agent relecteur de confidentialité et un validateur post-rendu). Zéro dépendance pip — uniquement des commandes macOS et la bibliothèque standard de Python.

---

<!-- skillx:begin:setup-skillx -->
## Essayez-le avec skillx

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

Exécutez ce skill sans rien installer :

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Libère de l'espace sur mon Mac."
```

Envie d'une prévisualisation ? Ajoutez `essai à blanc` à votre message. Le skill parcourt les sept étapes mais `safe_delete.py` n'écrit rien dans le système de fichiers (uniquement le `actions.jsonl` du workdir).

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Libère de l'espace sur mon Mac, mais en essai à blanc, sans rien supprimer pour de vrai."
```

Propulsé par [skillx](https://skillx.run) — récupère, scanne, injecte et nettoie n'importe quel agent skill en une seule commande.
<!-- skillx:end:setup-skillx -->

---

## Demo

Le rapport est **localisé** dans la langue avec laquelle vous avez déclenché le skill — une langue par exécution, pas de bascule à l'exécution. Déclenché en anglais → rapport anglais ; en chinois → rapport chinois ; en japonais, espagnol, français, etc. → cette langue. Ci-dessous : aperçu de la première vue (EN à gauche, ZH à droite, issus de deux exécutions distinctes), suivi des liens vers les captures pleine page. Actuellement nous ne fournissons que des captures en anglais et en chinois à titre d'illustration ; le skill produit bien le rapport complet dans **la langue de cette page** (français) lorsqu'il est déclenché ainsi.

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="Rapport mac-space-cleanup, première vue, anglais" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="Rapport mac-space-cleanup, première vue, chinois" /></td>
</tr>
</table>

Rapport complet (Résumé d'impact · Répartition · Journal détaillé · Observations · Détails d'exécution · Distribution de risque L1–L4) :
[Page complète en anglais](assets/mac-space-cleanup.full.en.png) · [Page complète en chinois](assets/mac-space-cleanup.full.zh.png)

---

## Pourquoi ce skill

Il ne manque pas de façons de libérer du disque —— apps GUI dédiées (CleanMyMac, OnyX, DaisyDisk), un prompt LLM brut (« hey Claude, nettoie mon Mac »), ou votre mémoire musculaire avec `rm -rf ~/Library/Caches`. Ce skill existe parce que les trois laissent des trous qui comptent sur un Mac de développeur.

| Ce qui vous importe | Nettoyeur GUI classique | Prompt LLM brut | Ce skill |
| --- | --- | --- | --- |
| **Où se font les écritures** | Moteur propriétaire, code fermé | Le `rm -rf` que le modèle choisit | Point de passage unique `safe_delete.py` avec une blocklist déterministe (`.git`, `.ssh`, Keychains, `.env*`, Adobe `Auto-Save`, éditions VSCode non sauvegardées, …) appliquée **avant** l'appel au système de fichiers —— refuse même si vous lui demandez de procéder |
| **Conscience du risque** | Habituellement un seul seau « Safe to remove » | Aucune —— les modèles hallucinent | Gradation L1–L4 par élément. Le mode Quick exécute automatiquement uniquement L1. Le mode Deep demande élément par élément pour L2/L3. L4 n'est jamais exécuté automatiquement |
| **Honnêteté du chiffre** | « 40 Go libérés » compte souvent des octets encore dans la Corbeille | Ce que le modèle prétend | Séparé en `freed_now` (vraiment sorti du disque) / `pending_in_trash` / `archived_source`. Le titre du texte de partage utilise `freed_now` |
| **Confidentialité sortant de la machine** | Local mais opaque | Chemins + noms de fichiers complets envoyés au fournisseur | Seuls `source_label` + `category` atteignent le rapport. Un sous-agent redaction reviewer plus un validator post-rendu attrapent les fuites avant que vous ne voyiez le HTML |
| **Conscience du Mac de développeur** | Balayages génériques de répertoires | Chat uniquement, pas de scan | Découverte de projets enracinés dans `.git` ; dispatcher Ollama par modèle (`ollama:<name>:<tag>`) avec comptage de références aux blobs ; rétrogradation de version iOS active pour `DeviceSupport/` ; exclusion de version-pin (`.python-version` / `.nvmrc`) pour nvm/pyenv |
| **Audit et ré-exécution** | Habituellement aucun | Transcript du chat seulement | `actions.jsonl` append-only par exécution. Idempotent —— les chemins déjà absents deviennent `skip/success`, réexécuter sur le même workdir est sûr |
| **Dry-run** | Rare ou payant | Demander au modèle « ne le fais pas vraiment » | Citoyen de première classe —— toutes les étapes s'exécutent, `safe_delete.py` n'écrit rien, le rapport affiche un bandeau `DRY-RUN` |
| **Ouverture** | Produit commercial à code fermé | Pas de guardrails au niveau du code | Apache-2.0, zéro dépendance pip, commandes macOS pures + Python stdlib |

Version courte : **les nettoyeurs GUI sont sûrs mais opaques et gonflent le chiffre. Un LLM brut est flexible mais fera volontiers un `rm -rf` au mauvais endroit. Ce skill garde la flexibilité du LLM et ajoute les guardrails** —— blocklist déterministe dans le code, une couche de redaction que le modèle ne peut pas contourner, et comptabilité honnête pour que le nombre sur la carte de partage soit le nombre qui est vraiment sorti du disque.

---

## Install

N'importe quel harness d'agent capable de charger des skills peut s'en servir. Le snippet ci-dessous utilise le chemin courant `~/.claude/skills/` ; adaptez-le au répertoire de skills de votre harness si vous en utilisez un autre.

```bash
git clone git@github.com:skillx-run/mac-space-cleanup.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-cleanup" ~/.claude/skills/mac-space-cleanup
```

Rechargez votre harness pour que la liste des skills prenne en compte la nouvelle entrée (pour la plupart des harness : ouvrez une nouvelle session).

### Recommended optional dependency

```bash
brew install trash
```

Si le CLI `trash` est absent, `safe_delete.py` se rabat sur `mv` vers `~/.Trash` (avec un suffixe `-<timestamp>`) — ça marche, mais le suffixe paraît bizarre dans Finder. Le skill lui-même vous le rappelle au premier lancement.

---

## Use

Dans votre conversation avec l'agent, dites quelque chose comme :

| Vous dites… | Le skill choisit |
| --- | --- |
| « nettoyage rapide », « libère de la place », « fais un petit coup de balai » | mode `quick` (nettoie automatiquement les éléments à faible risque, ~30 s) |
| « nettoyage profond », « analyse l'espace », « trouve les gros morceaux » | mode `deep` (audit complet, demande élément par élément pour le risqué, ~2–5 min) |
| « nettoie mon Mac », « mon Mac est plein » (ambigu) | Le skill vous demande de choisir, avec des estimations de temps |

Pour prévisualiser sans toucher au système de fichiers, ajoutez le mot-clé `essai à blanc` à votre message :

> « Libère de l'espace sur mon Mac, mais en essai à blanc, sans rien supprimer pour de vrai. »

Le rapport affichera visiblement `DRY-RUN — no files touched` en haut (traduit dans la langue de déclenchement) et préfixera chaque nombre avec l'équivalent de « seraient libérés » dans la langue cible.

### Report language

Le rapport HTML est en **une seule langue par exécution**, produit dans la langue avec laquelle vous avez déclenché le skill. L'agent détecte la langue de la conversation à partir du message déclencheur, écrit sa valeur (un sous-tag BCP-47 comme `en`, `zh`, `ja`, `es`, `ar`) dans le workdir, puis écrit chaque nœud de langage naturel — titre principal, raisons des actions, observations, rendus de source_label, prose dry-run — directement dans cette langue. Les libellés statiques (titres de section, libellés de boutons, en-têtes de colonnes) sont livrés avec une base en anglais dans le template ; pour les exécutions non anglaises, l'agent les traduit en une seule passe dans un dictionnaire embarqué qui hydrate la page au chargement. Pas de bascule à l'exécution, pas de DOM bilingue — la langue de la conversation l'emporte.

Les écritures de droite à gauche (arabe, hébreu, persan) reçoivent `<html dir="rtl">` ; l'inversion de direction de base fonctionne, les ajustements fins de CSS RTL sont une limitation connue.

---

## What it touches (and never touches)

**Nettoie** (avec un classement de risque selon `references/category-rules.md`) :

- Caches développeur : Xcode DerivedData, Docker build cache, Go build cache, Gradle cache, ccache, sccache, JetBrains, Flutter SDK, caches des éditeurs de la famille VSCode (Code / Cursor / Windsurf / Zed `blob_store`).
- Caches de gestionnaires de paquets : Homebrew, npm, pnpm, yarn, pip, uv, Cargo, CocoaPods, RubyGems, Bundler, Composer, Poetry, Dart pub, Bun, Deno, Swift PM, Carthage. Les gestionnaires de versions (nvm / fnm / pyenv / rustup) font remonter les entrées non actives par version, les pins actifs étant lus depuis les `.python-version` / `.nvmrc` de chaque projet.
- Caches de modèles AI/ML : HuggingFace (`hub/` en L2 trash, `datasets/` en L3 defer), PyTorch hub, Ollama (L3 defer ; en mode deep, dispatch par modèle via `ollama:<name>:<tag>` avec comptage de références de blobs, de sorte que les couches partagées entre tags survivent à la suppression d'un tag frère), LM Studio, OpenAI Whisper, cache global Weights & Biases. Envs non `base` de Conda / Mamba / Miniforge sur les sept layouts d'installation courants sous macOS.
- Outils frontend : navigateurs + driver de Playwright, navigateurs embarqués de Puppeteer.
- Runtimes des simulateurs iOS/watchOS/tvOS (via `xcrun simctl delete`, **jamais `rm -rf`**). Les entrées `DeviceSupport/<OS>` d'iOS dont le major.minor correspond à un appareil appairé ou à un runtime de simulateur disponible sont automatiquement rétrogradées en L3 defer.
- Caches d'applications sous `~/Library/Caches/*`, saved application state et la Trash elle-même. Les caches des applications créatives (Adobe Media Cache / Peak Files, Final Cut Pro, Logic Pro) remontent sous des étiquettes spécifiques plutôt que sous le bucket générique `"System caches"`.
- Journaux, rapports de crash.
- Anciens installateurs dans `~/Downloads` (`.dmg / .pkg / .xip / .iso` de plus de 30 jours).
- Instantanés locaux Time Machine (via `tmutil deletelocalsnapshots`).
- **Artéfacts de build de projets** (mode deep uniquement, scannés par `scripts/scan_projects.py` pour tout répertoire ayant une racine `.git`) :
  - L1 suppression : `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` (projets Elixir uniquement), `Pods`, `vendor` (projets Go uniquement).
  - L2 vers Trash : `.venv`, `venv`, `env` (venvs Python — les pins de wheels peuvent ne pas se reproduire ; d'où la fenêtre de récupération) ; `coverage` (rapports de couverture de tests, conditionnés à `package.json` ou un marker Python) ; `.dvc/cache` (cache content-addressed de DVC, conditionné à un marker frère `.dvc/config` — le parent `.dvc/` contient l'état utilisateur et est préservé).
  - Répertoires système / gestionnaires de paquets (`~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.composer`, `~/.pub-cache`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash`) sont élagués lors de la découverte de projets.
- **Le mode deep remonte aussi les répertoires sous `~` ≥ 2 Gio qu'aucune autre règle n'a capturés** (L3 defer, `source_label="Unclassified large directory"`), pour que les véritables gros répertoires orphelins deviennent visibles pour une revue manuelle. Avant la classification finale, l'agent lance une brève investigation en lecture seule (au plus 6 commandes par candidat) pour affiner `category` et `source_label` ; le niveau de risque L3 defer est verrouillé quel que soit le résultat.

**Garde-fou dur — refuse peu importe ce que dit `confirmed.json`** (voir `_BLOCKED_PATTERNS` dans `scripts/safe_delete.py`) :

- Répertoires `.git`, `.ssh`, `.gnupg`.
- `~/Library/Keychains`, `~/Library/Mail`, `~/Library/Messages`, `~/Library/Mobile Documents` (iCloud Drive).
- Bibliothèque Photos, bibliothèque Apple Music.
- Fichiers `.env*`, clés SSH (`id_rsa`, `id_ed25519`, …).
- État des éditeurs de la famille VSCode : `{Code, Cursor, Windsurf}/{User, Backups, History}` (éditions non sauvegardées, équivalents de git-stash, historique local d'édition).
- Dossiers `Auto-Save` des apps créatives d'Adobe — projets non sauvegardés de Premiere / After Effects / Photoshop.

L'agent lui-même lit `references/cleanup-scope.md` pour la whitelist / blacklist orientée utilisateur — la blocklist ci-dessus en est le sous-ensemble appliqué à l'exécution.

---

## Architecture (one paragraph)

`SKILL.md` est le contrat du workflow — l'agent s'occupe du jugement (choix du mode, classification, conversation, rendu HTML). Deux petits scripts Python font ce que l'agent ne devrait pas faire : `scripts/safe_delete.py` est le **seul** chemin par lequel passent les écritures sur le fs (six actions dispatchées : delete / trash / archive / migrate / defer / skip ; idempotent ; isolation des erreurs par élément ; `actions.jsonl` en append-only) ; `scripts/collect_sizes.py` exécute `du -sk` en parallèle avec un timeout de 30 s par chemin et une sortie JSON structurée. Trois documents de référence (`references/`) constituent la base de connaissances de l'agent. Trois templates d'asset (`assets/`) sont le squelette du rapport que l'agent remplit. Deux couches reviewer / validator en Stage 6 attrapent les fuites de confidentialité avant que l'utilisateur ne voie le rapport. Le workdir par exécution vit dans `~/.cache/mac-space-cleanup/run-XXXXXX/`.

---

## Honesty contract

Chaque outil de nettoyage gonfle son chiffre « N Go libérés » en comptant ce qu'il a poussé dans la Trash. macOS ne libère pas ce disque tant que vous ne videz pas `~/.Trash`. Ce skill scinde la métrique :

- `freed_now_bytes` — réellement hors du disque (delete + migrate vers un autre volume).
- `pending_in_trash_bytes` — resté dans `~/.Trash` ; le rapport propose une ligne `osascript` pour la vider.
- `archived_source_bytes` / `archived_count` — octets emballés dans un tar du workdir.
- `reclaimed_bytes` — alias rétro-compatible = `freed_now + pending_in_trash`. Le texte de partage et l'entête du rapport utilisent `freed_now_bytes`, pas celui-ci.

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # workflow principal de l'agent (sept étapes)
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
│   ├── report-template.html      # squelette HTML à six régions avec marqueurs appariés
│   ├── report.css
│   └── share-card-template.svg   # carte de partage X 1200×630
├── tests/                        # suite unittest standard-library pure
├── CHANGELOG.md
├── CLAUDE.md                     # invariants pour les contributeurs
└── .github/workflows/ci.yml      # macos-latest : tests + smoke + dry-e2e
```

---

## Limitations & non-goals (v0.11.0)

- **Pas de pile d'undo.** Les voies de récupération sont la Trash native, les tars dans `archive/` du workdir et le volume cible du migrate.
- **Pas de cron / pas d'exécution en arrière-plan.** Chaque run est déclenchée par l'utilisateur.
- **Pas de cloud / pas de télémétrie.** Le workdir reste local.
- **Pas de chemins protégés par SIP**, pas de désinstallation de `/Applications/*.app`.
- **L'identification de la racine de projet utilise uniquement `.git`.** Les checkouts git nus sont reconnus ; les workspaces sans répertoire `.git` ne le sont pas. Les submodules git imbriqués sont dédoublonnés (pas de projet séparé).
- **La découverte d'artefacts ne respecte pas `.gitignore`** — elle scanne des noms de sous-répertoires conventionnels fixes (`node_modules`, `target`, …). Peut faire remonter un répertoire ignoré par git, peut rater un répertoire non conventionnel du projet.
- **Validation sur une seule machine.** Construit et testé sur macOS 25.x / 26.x avec une toolchain de développement. Les patterns n'ont pas encore été validés entre Apple Silicon et Intel, ni sur d'anciennes versions de macOS.

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
