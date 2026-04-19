# mac-space-cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · **日本語** · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

Mac のディスク容量をクリーンアップする **skill** —— 慎重・誠実・多段階。

> 本 skill は agent を 7 段階のワークフロー（モード選択 → 環境プローブ → スキャン → 分類 → 確認 → レポート → 開く）に沿って誘導し、**L1–L4 リスクグレーディング**、**正直な回収量の内訳**（`freed_now` / `pending_in_trash` / `archived` の 3 項目に分割）、そして**多層の安全ガード**（コード内蔵の決定的ブロックリスト、プライバシー監査用のサブ agent、レンダリング後のバリデータ）を提供します。pip 依存ゼロ — 純粋な macOS コマンドと Python 標準ライブラリのみ。

---

<!-- skillx:begin:setup-skillx -->
## skillx で試す

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

インストール不要で、この skill をすぐに実行できます：

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Mac の空き容量を増やして。"
```

先にプレビューしてみたい？ トリガー文に `ドライラン` を追加してください。skill は 7 つのステージすべてを実行しますが、`safe_delete.py` はファイルシステムに何も書き込みません（workdir の `actions.jsonl` のみ）。

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Mac をクリーンアップしてください、ドライランモードで。実際には削除しないでください。"
```

[skillx](https://skillx.run) が駆動 — 1 つのコマンドで任意の agent skill を取得・スキャン・注入・クリーンアップします。
<!-- skillx:end:setup-skillx -->

---

## Demo

レポートは skill を起動した言語に応じて自動で**ローカライズ**されます — 1 回の実行につき 1 言語のみ、ランタイム切り替えはありません。英語で起動 → 英語レポート、中国語で起動 → 中国語レポート、日本語・スペイン語・フランス語などで起動 → その言語、という具合です。以下はファーストビューの印象（左が英語、右が中国語、いずれも別々の実行から）で、下にフルページキャプチャへのリンクがあります。現在提供しているスクリーンショットは英語と中国語のみですが、skill 自体は**このページの言語**（日本語）を含むあらゆる言語で完全なレポートを出力します。

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="mac-space-cleanup レポートのファーストビュー、英語" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="mac-space-cleanup レポートのファーストビュー、中国語" /></td>
</tr>
</table>

フルレポート（影響サマリ · カテゴリ内訳 · 詳細ログ · 観察事項 · 実行詳細 · L1–L4 リスク分布）:
[英語フルページ](assets/mac-space-cleanup.full.en.png) · [中国語フルページ](assets/mac-space-cleanup.full.zh.png)

---

## なぜこの skill か

Mac の空き容量を確保する方法はすでに豊富にあります —— 専用 GUI アプリ（CleanMyMac、OnyX、DaisyDisk）、生の LLM プロンプト（「Claude、Mac を掃除して」）、または指が覚えた `rm -rf ~/Library/Caches`。この skill が存在する理由は、開発者の Mac ではこの 3 つのどれにも盲点があるからです。

| 気にしているポイント | 従来の GUI クリーナー | 素の LLM プロンプト | この skill |
| --- | --- | --- | --- |
| **書き込みの入口** | クローズドソースの専有エンジン | モデルが決めた `rm -rf` 任せ | 単一の `safe_delete.py` 収束点。ファイルシステム呼び出し**前**に決定的 blocklist（`.git`、`.ssh`、Keychains、`.env*`、Adobe `Auto-Save`、VSCode の未保存編集…）を執行 —— 指示されても拒否する |
| **リスク認識** | 通常「Safe to remove」の 1 バケット | なし —— モデルは幻覚する | 項目ごとに L1–L4 グレーディング。Quick モードは L1 のみ自動実行。Deep モードは L2/L3 を項目ごとに確認。L4 は決して自動実行しない |
| **回収数字の誠実さ** | 「40 GB 解放」に Trash に残ったバイトが混入しがち | モデルの主張次第 | `freed_now`（本当にディスクから離れた分）/ `pending_in_trash` / `archived_source` に分割。共有テキストの見出しは `freed_now` を使う |
| **マシン外に出るプライバシー** | ローカルだが不透明 | 完全なパス + ファイル名をプロバイダに送信 | レポートに出るのは `source_label` + `category` のみ。redaction reviewer サブ agent とレンダリング後 validator が HTML を見る前に漏洩を捕捉 |
| **開発者 Mac への理解** | ざっくりディレクトリスイープ | チャットだけ、スキャンなし | `.git` ルートのプロジェクト発見、モデル単位の Ollama ディスパッチャ（`ollama:<name>:<tag>`）＋ blob 参照カウント、`DeviceSupport/` のアクティブ iOS バージョン降格、nvm/pyenv のバージョン pin（`.python-version` / `.nvmrc`）除外 |
| **監査と再実行** | 通常なし | チャットログのみ | 実行ごとに append-only の `actions.jsonl`。冪等 —— 消えているパスは `skip/success` になる、同じ workdir への再実行は安全 |
| **Dry-run** | 珍しい or 有料 | モデルに「本当にはやらないで」と頼む | 一級市民 —— 全ステージ走るが `safe_delete.py` は何も書かない、レポートに `DRY-RUN` バナー |
| **オープン性** | クローズドソースの商用製品 | ソース層のガードレールなし | Apache-2.0、pip 依存ゼロ、純粋 macOS コマンド + Python stdlib |

一行でまとめると：**GUI クリーナーは安全だが不透明、しかも数字を盛る。素の LLM は柔軟だが平気で間違った `rm -rf` をやる。この skill は LLM の柔軟さを残しつつ guardrail を付け加える** —— コード内の決定的 blocklist、モデルが迂回できない redaction レイヤー、そして共有カードに載る数字が本当にディスクから離れた数字と一致する誠実な会計。

---

## Install

skill をロードできる agent harness であればどれでも使えます。以下のコマンドは `~/.claude/skills/` という一般的なパスを例にしていますが、ご利用の harness が別の skills ディレクトリを使う場合はそちらに置き換えてください。

```bash
git clone git@github.com:skillx-run/mac-space-cleanup.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-cleanup" ~/.claude/skills/mac-space-cleanup
```

そのあと harness をリロードして skill リストを反映してください（多くの harness では新しいセッションを開けば十分です）。

### Recommended optional dependency

```bash
brew install trash
```

`trash` CLI が無い場合、`safe_delete.py` は `mv` で `~/.Trash` にファイルを移動する（`-<timestamp>` サフィックス付き）フォールバックに切り替わります — 動作はしますが、Finder 上でサフィックスが少し不自然に見えます。初回実行時には skill 自身もインストールを促します。

---

## Use

お使いの agent セッションで、こんな風に言ってください:

| こう言えば… | Skill の選択 |
| --- | --- |
| 「クリーンアップして」「容量あけて」「ちょっと掃除」 | `quick` モード（低リスク項目を自動クリーンアップ、約 30 秒） |
| 「深いクリーンアップをお願い」「大きいやつを探して」「ディスク使用を分析して」 | `deep` モード（完全監査、リスクのある項目は 1 件ずつ確認、約 2–5 分） |
| 「Mac をクリーンアップして」「容量が足りない」（曖昧） | Skill がどちらのモードを選ぶか、時間見積とともに聞き返します |

実際にファイルを触らずにプレビューしたい場合は、トリガー文に `ドライラン` キーワードを追加してください:

> 「Mac をクリーンアップしてください、ドライランモードで。実際には削除しないでください。」

レポートの上部には `DRY-RUN — no files touched` が明示され（トリガー言語に翻訳されます）、各数値にはターゲット言語で「予定」に相当する接頭辞が付きます。

### Report language

HTML レポートは **1 回の実行につき単一言語** で生成され、skill を起動した言語がそのまま出力言語になります。Agent はトリガーメッセージから会話言語を検出し、その値（`en`、`zh`、`ja`、`es`、`ar` のような BCP-47 サブタグ）を作業ディレクトリに書き出し、すべての自然言語ノード — ヒーローキャプション、アクション理由、観察結論、source_label の表示、dry-run の文言 — をその言語で直接記述します。テンプレート内の静的ラベル（セクション見出し、ボタン文言、表ヘッダ）は英語をベースラインとして同梱され、非英語の実行では agent が一度だけ埋め込み辞書に翻訳して、ページ読み込み時に hydrate が置き換えます。ランタイムトグルなし、バイリンガル DOM なし — 会話言語が優先されます。

右から左に書く言語（アラビア語、ヘブライ語、ペルシャ語）は自動で `<html dir="rtl">` が付きます。基本的な方向切り替えは機能しますが、精緻な RTL CSS 調整は既知の制限です。

---

## What it touches (and never touches)

**対象**（`references/category-rules.md` のリスクグレーディングに従う）:

- 開発者キャッシュ: Xcode DerivedData、Docker build cache、Go build cache、Gradle cache、ccache、sccache、JetBrains、Flutter SDK、VSCode 系エディタキャッシュ（Code / Cursor / Windsurf / Zed `blob_store`）。
- パッケージマネージャキャッシュ: Homebrew、npm、pnpm、yarn、pip、uv、Cargo、CocoaPods、RubyGems、Bundler、Composer、Poetry、Dart pub、Bun、Deno、Swift PM、Carthage。バージョンマネージャ（nvm / fnm / pyenv / rustup）はバージョン別に非アクティブなエントリのみをサーフェスし、アクティブな pin は各プロジェクトの `.python-version` / `.nvmrc` から自動的に除外されます。
- AI/ML モデルキャッシュ: HuggingFace（`hub/` は L2 trash、`datasets/` は L3 defer）、PyTorch hub、Ollama（L3 defer；deep モードでは `ollama:<name>:<tag>` 形式でモデル単位にディスパッチされ、blob の参照カウントによって異なる tag 間で共有されたレイヤーは、ある tag の削除時にも保持される）、LM Studio、OpenAI Whisper、Weights & Biases グローバルキャッシュ。Conda / Mamba / Miniforge の非 `base` env、macOS で一般的な 7 種類のインストールレイアウトをカバー。
- フロントエンドツール: Playwright のブラウザ + driver、Puppeteer のバンドルブラウザ。
- iOS/watchOS/tvOS シミュレータランタイム（`xcrun simctl delete` 経由、**`rm -rf` は絶対に使いません**）。iOS `DeviceSupport/<OS>` エントリのうち major.minor が現在ペアリング中の実機または使用可能なシミュレータの runtime と一致するものは、自動的に L3 defer に降格されます。
- `~/Library/Caches/*` 配下のアプリキャッシュ、saved application state、Trash そのもの。クリエイティブ系アプリのキャッシュ（Adobe Media Cache / Peak Files、Final Cut Pro、Logic Pro）は、汎用の `"System caches"` ではなく固有のラベルでサーフェスされます。
- ログ、クラッシュレポート。
- `~/Downloads` 内の 30 日以上前の古いインストーラ（`.dmg / .pkg / .xip / .iso`）。
- Time Machine ローカルスナップショット（`tmutil deletelocalsnapshots` 経由）。
- **プロジェクトのビルド成果物**（deep モードのみ。`scripts/scan_projects.py` で `.git` ルートを持つディレクトリをスキャン）:
  - L1 で直接削除: `node_modules`、`target`、`build`、`dist`、`out`、`.next`、`.nuxt`、`.svelte-kit`、`.turbo`、`.parcel-cache`、`__pycache__`、`.pytest_cache`、`.tox`、`.mypy_cache`、`.ruff_cache`、`.dart_tool`、`.nyc_output`、`_build`（Elixir プロジェクトのみ）、`Pods`、`vendor`（Go プロジェクトのみ）。
  - L2 で Trash へ: `.venv`、`venv`、`env`（Python 仮想環境 — wheel ピン留めだと完全に再現できない場合があるため、回収期間を設ける）；`coverage`（テストカバレッジレポート、`package.json` または Python marker の有無で判定）；`.dvc/cache`（DVC のコンテンツアドレス指定キャッシュ。隣接する `.dvc/config` marker の有無で判定 — 親ディレクトリ `.dvc/` はユーザ状態を含むためそのまま保持）。
  - システム / パッケージマネージャディレクトリ（`~/Library`、`~/.cache`、`~/.npm`、`~/.cargo`、`~/.cocoapods`、`~/.gradle`、`~/.m2`、`~/.gem`、`~/.bundle`、`~/.composer`、`~/.pub-cache`、`~/.local`、`~/.rustup`、`~/.pnpm-store`、`~/.Trash`）はプロジェクト検出時にプルーニングされます。
- **deep モードはさらに `~` 配下で 2 GiB 以上、他のルールにマッチしないディレクトリもサーフェスします**（L3 defer、`source_label="Unclassified large directory"`）。真の孤児ディレクトリをユーザーが手動で判断できるようにします。最終確定の前に agent は短時間の読み取り専用調査（候補ごとに最大 6 コマンド）を実行して category と source_label を精緻化しますが、調査結果に関わらず L3 defer のリスクグレードはロックされます。

**ハードブロック — `confirmed.json` がどう書かれていても拒否**（`scripts/safe_delete.py` の `_BLOCKED_PATTERNS` を参照）:

- `.git`、`.ssh`、`.gnupg` ディレクトリ。
- `~/Library/Keychains`、`~/Library/Mail`、`~/Library/Messages`、`~/Library/Mobile Documents`（iCloud Drive）。
- Photos Library、Apple Music ライブラリ。
- `.env*` ファイル、SSH 秘密鍵ファイル（`id_rsa`、`id_ed25519`…）。
- VSCode 系エディタの状態: `{Code, Cursor, Windsurf}/{User, Backups, History}`（未保存の編集、git-stash 相当物、ローカル編集履歴）。
- Adobe クリエイティブ系アプリの `Auto-Save` フォルダ — 未保存の Premiere / After Effects / Photoshop プロジェクトファイル。

Agent 自身はユーザ向けのホワイトリスト / ブラックリストを `references/cleanup-scope.md` から読み込みます — 上記のブロックリストは、ランタイムで強制実行されるそのサブセットです。

---

## Architecture (one paragraph)

`SKILL.md` がワークフロー契約です — judgement 部分（モード選択、分類、会話、HTML レンダリング）はすべて agent が担当します。2 つの小さな Python スクリプトが agent の不得意な部分を担います: `scripts/safe_delete.py` はファイルシステム書き込みの**唯一**の経路（6 種のディスパッチアクション: delete / trash / archive / migrate / defer / skip；冪等；項目ごとのエラー隔離；追記専用の `actions.jsonl` 監査ログ）。`scripts/collect_sizes.py` は `du -sk` を並列実行し、パスごとに 30 秒タイムアウト、構造化 JSON で出力します。3 つの reference ドキュメント（`references/`）は agent のナレッジベースです。3 つの asset テンプレート（`assets/`）は agent が埋めていくレポート骨格です。Stage 6 の 2 層の reviewer / validator がユーザに届く前にプライバシー漏洩を捕捉します。実行ごとの作業ディレクトリは `~/.cache/mac-space-cleanup/run-XXXXXX/` に置かれます。

---

## Honesty contract

どんなディスククリーンアップツールも「N GB 解放した」という数字を、Trash に送り込んだ分まで足すことで水増ししがちです。しかし macOS は `~/.Trash` を空にするまで、その分のディスクを実際には解放しません。この skill はこの指標を分割します:

- `freed_now_bytes` — 本当にディスクから消えた分（直接削除 + 別ボリュームへの migrate）。
- `pending_in_trash_bytes` — `~/.Trash` に残っている分。空にするための 1 行 `osascript` がレポートに表示されます。
- `archived_source_bytes` / `archived_count` — 作業ディレクトリ内の tar にまとめられたバイト数 / ファイル数。
- `reclaimed_bytes` — 後方互換のエイリアスで、`freed_now + pending_in_trash` に等しい。共有テキストとレポートの見出しが使うのはこの値ではなく `freed_now_bytes` です。

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # agent メインワークフロー（7 段階）
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
│   ├── report-template.html      # ペアマーカー付き 6 リージョンの HTML 骨格
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 の X シェアカード
├── tests/                        # 標準ライブラリのみの unittest スイート
├── CHANGELOG.md
├── CLAUDE.md                     # コントリビュータ向け不変量
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations & non-goals (v0.11.0)

- **undo スタックなし。** 復旧経路は、ネイティブ Trash、作業ディレクトリの `archive/` tar、migrate 先ボリュームのみ。
- **cron なし / バックグラウンド実行なし。** すべてユーザが明示的にトリガー。
- **クラウドなし / テレメトリなし。** 作業ディレクトリはローカルに留まる。
- **SIP 保護パスには触れず**、`/Applications/*.app` のアンインストールもしません。
- **プロジェクトルートの識別は `.git` のみ。** 生の git チェックアウトは認識されますが、`.git` を持たないプロジェクトワークスペースは認識されません。ネストされた git submodule は重複排除され、個別プロジェクトとしては現れません。
- **プロジェクト成果物の発見は `.gitignore` を尊重しません** — 固定の慣習的サブディレクトリ名（`node_modules`、`target`、…）を対象にスキャンします。git で無視されたディレクトリが出てくる可能性も、慣習外のディレクトリを見逃す可能性もあります。
- **単機での検証。** 開発とテストはすべて macOS 25.x / 26.x + 開発者ツールチェーンで実施。Apple Silicon と Intel、および旧 macOS バージョン間でのクロス検証はまだです。

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
