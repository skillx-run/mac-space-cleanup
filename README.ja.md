# mac-space-cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · **日本語** · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

Mac のディスク容量をクリーンアップする skill。

> 6 段階のワークフロー: モード選択、環境プローブ、スキャン、分類、確認、レポート。各候補は L1-L4 でグレーディングされ、すべてのファイルシステム書き込みは `safe_delete.py` を経由します。同スクリプトは内部 blocklist を持ち、プライバシー redaction のサブ agent とレンダリング後のバリデータと組み合わさって 3 層のガードレールを構成します。Trash 内で空にされるのを待つバイトは別カウントとなり、「解放済み」の合計には含まれません。pip 依存ゼロ — 純粋な macOS コマンドと Python 標準ライブラリのみ。

---

## なぜこの skill か

ルールベースのクリーナー（CleanMyMac、OnyX）はルールで名指しできる項目しか扱いません。ある `node_modules` がまだ使われているか、`~/Library/Caches` のどのディレクトリがアクティブなユーザ設定でどれが残骸か — こうした判断はルールの範疇を超えており、これらのツールは安全側に倒してスキップし、回収可能な領域をかなり残したままにします。

agent に直接クリーンアップを任せる（「Claude、Mac を掃除して」）とそのグレーゾーンも扱えますが、堅いバウンダリがなければ一度の判断ミスで `.git` / `.env` / Keychains に手が及びかねません。

この skill はまず安全境界を確立します。`safe_delete.py` の blocklist、プライバシー reviewer、レンダリング後のバリデータの 3 層ガードレールが、上記のパスを実行時に拒否します。その前提のもと、判断はすべて agent に委譲され、ルールベースのツールでは届かないグレーゾーンを扱います。

---

<!-- skillx:begin:setup-skillx -->
## skillx で試す

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

インストール不要で、この skill をそのまま実行できます:

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Mac の空き容量を増やして。"
```

実際に実行せずプレビューしたい場合は、トリガー文に `--dry-run` を追加してください。skill は 6 段階をすべて実行しますが、`safe_delete.py` はファイルシステムに何も書き込みません（workdir の `actions.jsonl` のみ）。

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Mac をクリーンアップしてください、--dry-run でプレビューのみ、実際には削除しないでください。"
```

[skillx](https://skillx.run) が駆動 — 任意の agent skill の取得・スキャン・注入・実行を 1 つのコマンドで。
<!-- skillx:end:setup-skillx -->

---

## Demo

レポートの言語は skill を起動した会話の言語で決まり、1 回の実行につき単一言語となります。以下はファーストビューで、左が英語、右が中国語、それぞれ別々の実行によるものです。

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="mac-space-cleanup レポートのファーストビュー、英語" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="mac-space-cleanup レポートのファーストビュー、中国語" /></td>
</tr>
</table>

フルレポート（影響サマリ · カテゴリ内訳 · 詳細ログ · 観察事項 · 実行詳細 · L1–L4 リスク分布）:
[英語フルページ](assets/mac-space-cleanup.full.en.png) · [中国語フルページ](assets/mac-space-cleanup.full.zh.png)

---

## Install

skill をロードできる agent harness であればどれでも使えます。以下のコマンドは `~/.claude/skills/` を例のパスとして使用しています。ご利用の harness が別の skills ディレクトリを使う場合はそちらに置き換えてください。

```bash
git clone git@github.com:skillx-run/mac-space-cleanup.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-cleanup" ~/.claude/skills/mac-space-cleanup
```

続いて新しい agent セッションを開いて skill リストを更新してください。

`trash` も併せてインストールすることを推奨します（`brew install trash`）。未インストール時は `safe_delete.py` が `mv` で `~/.Trash` に退避するフォールバックとなり、ファイル名にタイムスタンプのサフィックスが付加されます。

---

## Use

agent の会話で、以下のようなトリガー文を使ってください:

| トリガー | Skill の選択 |
| --- | --- |
| 「クリーンアップして」「容量あけて」「ちょっと掃除」 | `quick` モード（低リスク項目を自動クリーンアップ、約 30 秒） |
| 「深いクリーンアップをお願い」「大きいやつを探して」「ディスク使用を分析して」 | `deep` モード（完全監査、リスクのある項目は 1 件ずつ確認、約 2–5 分） |
| 「Mac をクリーンアップして」「容量が足りない」（曖昧） | Skill がどちらのモードを選ぶか、時間見積とともに尋ねます |

ファイルに触れずプレビューしたい場合は、トリガー文に `--dry-run` を追加してください:

> 「Mac をクリーンアップしてください、--dry-run でプレビューのみ、実際には削除しないでください。」

レポート上部に dry-run 状態が表示され、各数値には「予定」相当の接頭辞が付加されます。RTL 言語（アラビア語、ヘブライ語、ペルシャ語）には `<html dir="rtl">` が自動で付きます。精緻な RTL スタイル調整は既知の制限です。

---

## Scope

クリーンアップ対象（`references/category-rules.md` のリスクグレーディングに従う）:

- 開発者キャッシュ: Xcode DerivedData、Docker build cache、Go build cache、Gradle cache、ccache、sccache、JetBrains、Flutter SDK、VSCode 系エディタキャッシュ（Code / Cursor / Windsurf / Zed `blob_store`）。
- パッケージマネージャキャッシュ: Homebrew、npm、pnpm、yarn、pip、uv、Cargo、CocoaPods、RubyGems、Bundler、Composer、Poetry、Dart pub、Bun、Deno、Swift PM、Carthage。バージョンマネージャ（nvm / fnm / pyenv / rustup）はバージョン別に非アクティブなエントリのみをサーフェスし、アクティブな pin は各プロジェクトの `.python-version` / `.nvmrc` から自動的に除外されます。
- AI/ML モデルキャッシュ: HuggingFace（`hub/` は L2 trash、`datasets/` は L3 defer）、PyTorch hub、Ollama（L3 defer；deep モードでは `ollama:<name>:<tag>` 形式でモデル単位にディスパッチされ、blob の参照カウントによって異なる tag 間で共有されたレイヤーは、ある tag の削除時にも保持されます）、LM Studio、OpenAI Whisper、Weights & Biases グローバルキャッシュ。Conda / Mamba / Miniforge の非 `base` env、macOS で一般的な 7 種類のインストールレイアウトをカバー。
- フロントエンドツール: Playwright のブラウザ + driver、Puppeteer のバンドルブラウザ。
- iOS/watchOS/tvOS シミュレータランタイム（`xcrun simctl delete` 経由、`rm -rf` は使いません）。iOS `DeviceSupport/<OS>` エントリのうち major.minor が現在ペアリング中の実機または使用可能なシミュレータの runtime と一致するものは、自動的に L3 defer に降格されます。
- `~/Library/Caches/*` 配下のアプリキャッシュ、saved application state、Trash そのもの。クリエイティブ系アプリのキャッシュ（Adobe Media Cache / Peak Files、Final Cut Pro、Logic Pro）は、汎用の `"System caches"` ではなく固有のラベルで表示されます。
- ログ、クラッシュレポート。
- `~/Downloads` 配下で 30 日以上前の古いインストーラ（`.dmg / .pkg / .xip / .iso`）。
- Time Machine ローカルスナップショット（`tmutil deletelocalsnapshots` 経由）。
- プロジェクトのビルド成果物（deep モードのみ；`scripts/scan_projects.py` で `.git` ルートを持つディレクトリをスキャン）:
  - L1 で直接削除: `node_modules`、`target`、`build`、`dist`、`out`、`.next`、`.nuxt`、`.svelte-kit`、`.turbo`、`.parcel-cache`、`__pycache__`、`.pytest_cache`、`.tox`、`.mypy_cache`、`.ruff_cache`、`.dart_tool`、`.nyc_output`、`_build`（Elixir プロジェクトのみ）、`Pods`、`vendor`（Go プロジェクトのみ）。
  - L2 で Trash へ: `.venv`、`venv`、`env`（Python 仮想環境 — wheel ピン留めでは完全に再現できない場合があるため、回収期間を設ける）；`coverage`（テストカバレッジレポート、`package.json` または Python marker の有無で判定）；`.dvc/cache`（DVC のコンテンツアドレス指定キャッシュ、隣接する `.dvc/config` marker で判定；親ディレクトリ `.dvc/` はユーザ状態を含むため保持）。
  - システム / パッケージマネージャディレクトリ（`~/Library`、`~/.cache`、`~/.npm`、`~/.cargo`、`~/.cocoapods`、`~/.gradle`、`~/.m2`、`~/.gem`、`~/.bundle`、`~/.composer`、`~/.pub-cache`、`~/.local`、`~/.rustup`、`~/.pnpm-store`、`~/.Trash`）はプロジェクト検出時にプルーニングされます。
- 孤児の大ディレクトリスキャン（deep モードのみ）: `~` 配下で 2 GiB 以上かつ他のどのルールにもマッチしないディレクトリは L3 defer としてマークされます（`source_label="Unclassified large directory"`）。最終確定の前に agent は短時間の読み取り専用調査（候補ごとに最大 6 コマンド）を行い `category` と `source_label` を精緻化しますが、調査結果に関わらず L3 defer グレードはロックされます。

ハードバックストップ — `confirmed.json` の内容に関わらず拒否。`scripts/safe_delete.py` の `_BLOCKED_PATTERNS` を参照:

- `.git`、`.ssh`、`.gnupg` ディレクトリ。
- `~/Library/Keychains`、`~/Library/Mail`、`~/Library/Messages`、`~/Library/Mobile Documents`（iCloud Drive）。
- Photos Library、Apple Music ライブラリ。
- `.env*` ファイル、SSH 秘密鍵ファイル（`id_rsa`、`id_ed25519` など）。
- VSCode 系エディタの状態: `{Code, Cursor, Windsurf}/{User, Backups, History}`（未保存の編集、git-stash 相当物、ローカル編集履歴）。
- Adobe クリエイティブ系アプリの `Auto-Save` フォルダ — 未保存の Premiere / After Effects / Photoshop プロジェクトファイル。

---

## Architecture

`SKILL.md` は agent のワークフロー契約です。モード選択、分類、会話、HTML レンダリングはすべて agent が担当します。agent に向かないタスクは 2 つの Python スクリプトが担います — `scripts/safe_delete.py` はファイルシステム書き込みの唯一の入り口で、6 種のアクションディスパッチ、冪等性、項目ごとのエラー隔離を提供します。`scripts/collect_sizes.py` は標準ライブラリを使って `du -sk` を並列実行します。`references/` は agent のナレッジベース、`assets/` はレポートテンプレートです。Stage 6 の 2 層の reviewer / validator が、ユーザに届く前にプライバシー漏洩を捕捉します。実行ごとの作業ディレクトリは `~/.cache/mac-space-cleanup/run-XXXXXX/` にあります。

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # agent メインワークフロー（6 段階）
├── scripts/
│   ├── safe_delete.py            # 6 アクションディスパッチャ + blocklist ハードガード
│   ├── collect_sizes.py          # 並列 du -sk
│   ├── scan_projects.py          # .git ルート探索 + クリーン可能成果物の列挙
│   ├── aggregate_history.py      # クロス実行確信度アグリゲータ（Stage 5 HISTORY_BY_LABEL） + run-* GC
│   ├── validate_report.py        # レンダリング後チェック（region / placeholder / 漏洩 / dry-run マーク）
│   ├── smoke.sh                  # 実ファイルシステム スモーク
│   └── dry-e2e.sh                # 非 LLM エンドツーエンド harness
├── references/
│   ├── cleanup-scope.md          # ホワイトリスト / ブラックリスト（safe_delete blocklist への相互参照付き）
│   ├── safety-policy.md          # L1-L4 グレーディング + プライバシー秘匿 + 劣化ポリシー
│   ├── category-rules.md         # 10 カテゴリのパターン + risk_level + action
│   └── reviewer-prompts.md       # プライバシーレビュー用サブ agent の prompt テンプレート
├── assets/
│   ├── report-template.html      # ペアマーカー付き 6 リージョンの HTML テンプレート
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 の X シェアカード
├── tests/                        # 標準ライブラリのみの unittest スイート
├── CHANGELOG.md
├── CLAUDE.md                     # コントリビュータ向け不変量
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations

- **undo スタックなし。** 復旧経路は、ネイティブ Trash、作業ディレクトリの `archive/` tar、migrate 先ボリュームのみ。
- **cron なし、バックグラウンド実行なし。** すべてユーザが明示的にトリガーします。
- **クラウドなし、テレメトリなし。** 作業ディレクトリはローカルに留まります。
- **SIP 保護パスには触れず**、`/Applications/*.app` のアンインストールもしません。
- **プロジェクトルートの識別は `.git` のみ。** 標準的な git チェックアウトは認識されますが、`.git` を持たないプロジェクトワークスペースは認識されません。ネストされた git submodule は重複排除され、個別プロジェクトとしては現れません。
- **プロジェクト成果物の発見は `.gitignore` に従いません** — 固定の慣習的サブディレクトリ名（`node_modules`、`target` など）を対象にスキャンします。git で無視されたディレクトリが含まれる可能性も、慣習外のディレクトリを見逃す可能性もあります。
- **単機での検証。** 開発とテストはすべて macOS 25.x / 26.x + 開発者ツールチェーンで実施。Apple Silicon と Intel、および旧 macOS バージョン間でのクロス検証は未完了です。

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # 実ファイルシステムの正常性
./scripts/dry-e2e.sh                        # 非 LLM エンドツーエンド
```

push / PR のたびに、CI が `macos-latest` 上で `.github/workflows/ci.yml` 経由で上記 3 つを実行します。

非交渉不変量（agent は直接ファイルシステムに書かない、プライバシー秘匿は必須、など）については `CLAUDE.md` を、リリースノートについては `CHANGELOG.md` を参照してください。

---

## License

Apache-2.0（`LICENSE` と `NOTICE` を参照）。

## Credits

設計・実装: [@heyiamlin](https://x.com/heyiamlin)。この skill で容量が空いたら、`#macspaceclean` ハッシュタグで共有してください。
