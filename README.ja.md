# mac-space-cleanup · macOS cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · **日本語** · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

Mac のディスク容量をクリーンアップする **skill** —— 慎重・誠実・多段階。

> 本 skill は agent を 7 段階のワークフロー（モード選択 → 環境プローブ → スキャン → 分類 → 確認 → レポート → 開く）に沿って誘導し、**L1–L4 リスクグレーディング**、**正直な回収量の内訳**（`freed_now` / `pending_in_trash` / `archived` の 3 項目に分割）、そして**多層の安全ガード**（コード内蔵の決定的ブロックリスト、プライバシー監査用のサブ agent、レンダリング後のバリデータ）を提供します。pip 依存ゼロ — 純粋な macOS コマンドと Python 標準ライブラリのみ。

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

実際にファイルを触らずにプレビューしたい場合は、トリガー文に `--dry-run` を追加してください:

> 「Mac を深くクリーンアップしてください。ただし --dry-run モードで実際にはファイルを削除しないでください」

レポートの上部には `DRY-RUN — no files touched` が明示され（トリガー言語に翻訳されます）、各数値にはターゲット言語で「予定」に相当する接頭辞が付きます。

### Report language

HTML レポートは **1 回の実行につき単一言語** で生成され、skill を起動した言語がそのまま出力言語になります。Agent はトリガーメッセージから会話言語を検出し、その値（`en`、`zh`、`ja`、`es`、`ar` のような BCP-47 サブタグ）を作業ディレクトリに書き出し、すべての自然言語ノード — ヒーローキャプション、アクション理由、観察結論、source_label の表示、dry-run の文言 — をその言語で直接記述します。テンプレート内の静的ラベル（セクション見出し、ボタン文言、表ヘッダ）は英語をベースラインとして同梱され、非英語の実行では agent が一度だけ埋め込み辞書に翻訳して、ページ読み込み時に hydrate が置き換えます。ランタイムトグルなし、バイリンガル DOM なし — 会話言語が優先されます。

右から左に書く言語（アラビア語、ヘブライ語、ペルシャ語）は自動で `<html dir="rtl">` が付きます。基本的な方向切り替えは機能しますが、精緻な RTL CSS 調整は既知の制限です。

---

## What it touches (and never touches)

**対象**（`references/category-rules.md` のリスクグレーディングに従う）:

- 開発者キャッシュ: Xcode DerivedData、Docker build cache、Go build cache、Gradle cache。
- パッケージマネージャキャッシュ: Homebrew、npm、pnpm、yarn、pip、uv、Cargo、CocoaPods。
- iOS/watchOS/tvOS シミュレータランタイム（`xcrun simctl delete` 経由、**`rm -rf` は絶対に使いません**）。
- `~/Library/Caches/*` 配下のアプリキャッシュ、saved application state、Trash そのもの。
- ログ、クラッシュレポート。
- `~/Downloads` 内の 30 日以上前の古いインストーラ（`.dmg / .pkg / .xip / .iso`）。
- Time Machine ローカルスナップショット（`tmutil deletelocalsnapshots` 経由）。
- **プロジェクトのビルド成果物**（deep モードのみ。`scripts/scan_projects.py` で `.git` ルートを持つディレクトリをスキャン）:
  - L1 で直接削除: `node_modules`、`target`、`build`、`dist`、`out`、`.next`、`.nuxt`、`.svelte-kit`、`.turbo`、`.parcel-cache`、`__pycache__`、`.pytest_cache`、`.tox`、`Pods`、`vendor`（Go プロジェクトのみ）。
  - L2 で Trash へ: `.venv`、`venv`、`env`（Python 仮想環境 — wheel ピン留めだと完全に再現できない場合があるため、回収期間を設ける）。
  - システム / パッケージマネージャディレクトリ（`~/Library`、`~/.cache`、`~/.npm`、`~/.cargo`、`~/.cocoapods`、`~/.gradle`、`~/.m2`、`~/.gem`、`~/.bundle`、`~/.local`、`~/.rustup`、`~/.pnpm-store`、`~/.Trash`）はプロジェクト検出時にプルーニングされます。

**ハードブロック — `confirmed.json` がどう書かれていても拒否**（`scripts/safe_delete.py` の `_BLOCKED_PATTERNS` を参照）:

- `.git`、`.ssh`、`.gnupg` ディレクトリ。
- `~/Library/Keychains`、`~/Library/Mail`、`~/Library/Messages`、`~/Library/Mobile Documents`（iCloud Drive）。
- Photos Library、Apple Music ライブラリ。
- `.env*` ファイル、SSH 秘密鍵ファイル（`id_rsa`、`id_ed25519`…）。

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

## Limitations & non-goals (v0.9.3)

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
