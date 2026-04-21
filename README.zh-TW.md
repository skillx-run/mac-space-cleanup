# mac-space-cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · **繁體中文** · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

[![CI](https://github.com/skillx-run/mac-space-cleanup/actions/workflows/ci.yml/badge.svg)](https://github.com/skillx-run/mac-space-cleanup/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/skillx-run/mac-space-cleanup)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/skillx-run/mac-space-cleanup?sort=semver)](https://github.com/skillx-run/mac-space-cleanup/releases)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey?logo=apple)](https://www.apple.com/macos/)
[![Python 3](https://img.shields.io/badge/python-3-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pip deps: 0](https://img.shields.io/badge/pip%20deps-0-brightgreen)](#)
[![i18n: 8 locales](https://img.shields.io/badge/i18n-8%20locales-blueviolet)](#)

一個清理 Mac 磁碟空間的 skill。

> 工作流程分六個階段：模式選擇、環境探測、掃描、分級、二次確認、報告。每個候選對象按 L1-L4 分級；所有檔案系統寫入動作統一經由 `safe_delete.py`，該指令稿內建 blocklist，並與隱私 reviewer 子 agent、渲染後驗證器共同構成三層護欄。Trash 中待清空的位元組單獨計數，不計入「已釋放」數值。零 pip 相依，僅使用 macOS 內建指令與 Python 標準函式庫。

---

## 為什麼選這個 skill

固定規則的清理工具（CleanMyMac、OnyX）只處理規則明確的條目：某個 `node_modules` 是否仍被專案使用、`~/Library/Caches` 中哪些目錄對應活躍的使用者偏好、哪些已是殘留，規則無法判斷，只能保守跳過，遺留大量本可清理的內容。

直接讓 agent 清理（「Claude，清理一下我的 Mac」）能涵蓋這些灰色地帶，但缺少硬性邊界——一次誤判就可能觸及 `.git` / `.env` / Keychains。

這個 skill 先建立安全邊界：`safe_delete.py` 的 blocklist、隱私 reviewer、渲染後驗證器三層護欄在執行時拒絕上述關鍵路徑。在此前提下，判斷權完整交給 agent，處理規則工具涵蓋不到的灰色地帶。

---

<!-- skillx:begin:setup-skillx -->
## 用 skillx 一鍵試用

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

無需安裝即可直接執行：

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "清理一下我的 Mac。"
```

如需僅預覽而不實際執行，在觸發語中加入 `--dry-run`。skill 仍會完整執行六個階段，但 `safe_delete.py` 不會寫入檔案系統（僅寫入執行目錄下的 `actions.jsonl`）。

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "幫我深度清理我的 Mac，加上 --dry-run 先預覽一下，不要真的刪除任何檔案。"
```

由 [skillx](https://skillx.run) 驅動——一條指令完成任何 agent skill 的拉取、掃描、注入與執行。
<!-- skillx:end:setup-skillx -->

---

## Demo

報告語言由觸發 skill 的對話語言決定，每次執行單一語系。下圖為首屏效果，左側英文、右側中文，取自兩次獨立執行。

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="mac-space-cleanup 報告首屏，英文" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="mac-space-cleanup 報告首屏，中文" /></td>
</tr>
</table>

整頁報告（影響總覽 · 類別分布 · 動作明細 · 觀察結論 · 執行詳情 · L1–L4 風險分布）：
[英文整頁](assets/mac-space-cleanup.full.en.png) · [中文整頁](assets/mac-space-cleanup.full.zh.png)

---

## Install

持久安裝透過 skillx 完成。若尚未安裝 skillx CLI：

```bash
curl -fsSL https://skillx.run/install.sh | sh
```

然後將此 skill 安裝到 skillx 辨識的任意 agent harness 的 skills 目錄（Claude Code 的 `~/.claude/skills/` 等）：

```bash
skillx install https://github.com/skillx-run/mac-space-cleanup
```

開啟一個新的 agent 工作階段以重新載入 skill 清單。後續更新或解除安裝使用 `skillx update mac-space-cleanup` / `skillx uninstall mac-space-cleanup`。

建議同時安裝 `trash`（`brew install trash`）。未安裝時 `safe_delete.py` 會退回為使用 `mv` 將檔案搬入 `~/.Trash`，但檔案名稱會附加時間戳記後綴。

---

## Use

在 agent 工作階段中使用類似的觸發語：

| 觸發語 | Skill 選擇 |
| --- | --- |
| "quick clean"、"馬上騰點空間"、"先清一波" | `quick` 模式（自動清理低風險項，約 30 秒） |
| "deep clean"、"深度清理"、"找大頭"、"分析空間" | `deep` 模式（完整稽核，高風險項逐項確認，約 2–5 分鐘） |
| "clean my Mac"、"Mac 空間滿了"（語意模糊） | Skill 會詢問使用哪種模式，並給出耗時估計 |

如需僅預覽而不實際修改檔案，在觸發語中加入 `--dry-run`：

> "幫我深度清理我的 Mac，加上 --dry-run 先預覽一下，不要真的刪除任何檔案。"

報告頂部會標註 dry-run 狀態，每個數字前加上「預計」前綴。阿拉伯文、希伯來文、波斯文等 RTL 語言會自動加上 `<html dir="rtl">`；精細 RTL 樣式調整是已知限制。

---

## Scope

清理對象（依 `references/category-rules.md` 的風險分級）：

- 開發者快取：Xcode DerivedData、Docker build cache、Go build cache、Gradle cache、ccache、sccache、JetBrains、Flutter SDK、VSCode 系編輯器快取（Code / Cursor / Windsurf / Zed `blob_store`）。
- 套件管理器快取：Homebrew、npm、pnpm、yarn、pip、uv、Cargo、CocoaPods、RubyGems、Bundler、Composer、Poetry、Dart pub、Bun、Deno、Swift PM、Carthage。版本管理器（nvm / fnm / pyenv / rustup）逐版本列出非活躍條目，活躍的 pin 透過讀取各專案的 `.python-version` / `.nvmrc` 自動排除。
- AI/ML 模型快取：HuggingFace（`hub/` L2 trash、`datasets/` L3 defer）、PyTorch hub、Ollama（L3 defer；deep 模式下以 `ollama:<name>:<tag>` 按模型分派，透過 blob 引用計數確保不同 tag 共享的 layer 在刪除某一 tag 時仍然保留）、LM Studio、OpenAI Whisper、Weights & Biases 全域快取。Conda / Mamba / Miniforge 的非 `base` env，涵蓋七種常見的 macOS 安裝配置。
- 前端工具鏈：Playwright 瀏覽器 + driver、Puppeteer 綁定的瀏覽器。
- iOS/watchOS/tvOS 模擬器執行環境（透過 `xcrun simctl delete`，非 `rm -rf`）。iOS `DeviceSupport/<OS>` 條目中 major.minor 與目前已配對實體裝置或可用模擬器 runtime 匹配者，將自動降級為 L3 defer。
- `~/Library/Caches/*` 下的應用程式快取、saved application state，以及 Trash 本身。創作類應用程式快取（Adobe Media Cache / Peak Files、Final Cut Pro、Logic Pro）使用具體標籤，而非通用的 `"System caches"`。
- 記錄檔、當機報告。
- `~/Downloads` 下超過 30 天的舊安裝檔（`.dmg / .pkg / .xip / .iso`）。
- Time Machine 本機快照（透過 `tmutil deletelocalsnapshots`）。
- 專案建置產物（僅 deep 模式；透過 `scripts/scan_projects.py` 掃描任何帶 `.git` 根的目錄）：
  - L1 直接刪除：`node_modules`、`target`、`build`、`dist`、`out`、`.next`、`.nuxt`、`.svelte-kit`、`.turbo`、`.parcel-cache`、`__pycache__`、`.pytest_cache`、`.tox`、`.mypy_cache`、`.ruff_cache`、`.dart_tool`、`.nyc_output`、`_build`（僅 Elixir 專案）、`Pods`、`vendor`（僅 Go 專案）。
  - L2 移入 Trash：`.venv`、`venv`、`env`（Python 虛擬環境——wheel 版本固定後可能無法完全重現，因此保留回收期）；`coverage`（測試覆蓋率報告，以 `package.json` 或 Python marker 判定）；`.dvc/cache`（DVC 的內容定址快取，以同層 `.dvc/config` marker 判定；父目錄 `.dvc/` 含使用者狀態，予以保留）。
  - 系統 / 套件管理器目錄（`~/Library`、`~/.cache`、`~/.npm`、`~/.cargo`、`~/.cocoapods`、`~/.gradle`、`~/.m2`、`~/.gem`、`~/.bundle`、`~/.composer`、`~/.pub-cache`、`~/.local`、`~/.rustup`、`~/.pnpm-store`、`~/.Trash`）在專案發現階段被剪枝。
- 孤兒大目錄掃描（僅 deep 模式）：`~` 下 ≥ 2 GiB 且未匹配任何規則的目錄標為 L3 defer（`source_label="Unclassified large directory"`）。定稿前 agent 會執行一次短暫的唯讀調查（每個候選最多 6 次命令）以細化 category 與 source_label；無論調查結果如何，L3 defer 檔位均被鎖定。

硬性兜底——無論 `confirmed.json` 中的內容如何均拒絕執行，見 `scripts/safe_delete.py` 中的 `_BLOCKED_PATTERNS`：

- `.git`、`.ssh`、`.gnupg` 目錄。
- `~/Library/Keychains`、`~/Library/Mail`、`~/Library/Messages`、`~/Library/Mobile Documents`（iCloud Drive）。
- Photos Library、Apple Music 資料庫。
- `.env*` 檔案、SSH 私鑰檔案（`id_rsa`、`id_ed25519` 等）。
- VSCode 系編輯器狀態：`{Code, Cursor, Windsurf}/{User, Backups, History}`（未儲存的編輯、git-stash 等價物、本機編輯歷程）。
- Adobe 創作類應用程式的 `Auto-Save` 目錄——未儲存的 Premiere / After Effects / Photoshop 專案檔。

---

## Architecture

`SKILL.md` 是 agent 的工作流程契約：模式選擇、分類、對話、HTML 渲染均由 agent 完成。兩個 Python 指令稿承擔 agent 不適合處理的職責——`scripts/safe_delete.py` 是檔案系統寫入動作的唯一入口，提供六種動作分派、冪等性與逐項錯誤隔離；`scripts/collect_sizes.py` 使用標準函式庫並行執行 `du -sk`。`references/` 是 agent 的知識庫，`assets/` 是報告模板。Stage 6 透過兩層 reviewer / validator 在使用者看到報告前攔截隱私洩漏。每次執行的工作目錄位於 `~/.cache/mac-space-cleanup/run-XXXXXX/`。

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # agent 主工作流程（六階段）
├── scripts/
│   ├── safe_delete.py            # 六種動作分派器 + blocklist 硬性兜底
│   ├── collect_sizes.py          # 並行 du -sk
│   ├── scan_projects.py          # 尋找 .git 根專案 + 列舉可清理產物
│   ├── aggregate_history.py      # 跨執行信心度聚合器（Stage 5 HISTORY_BY_LABEL） + run-* GC
│   ├── validate_report.py        # 渲染後驗證（region / placeholder / 洩漏 / dry-run 標記）
│   ├── smoke.sh                  # 真實檔案系統冒煙測試
│   └── dry-e2e.sh                # 非 LLM 端到端 harness
├── references/
│   ├── cleanup-scope.md          # 白名單 / 黑名單（與 safe_delete blocklist 交叉引用）
│   ├── safety-policy.md          # L1-L4 分級 + 隱私脫敏 + 降級
│   ├── category-rules.md         # 10 個類別的比對規則 + risk_level + action
│   └── reviewer-prompts.md       # 隱私 reviewer 子 agent 的 prompt 模板
├── assets/
│   ├── report-template.html      # 帶成對標記的六區塊 HTML 模板
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 X 分享卡
├── tests/                        # 純標準函式庫 unittest 套件
├── CHANGELOG.md
├── CLAUDE.md                     # 貢獻者必讀的不變量
└── .github/workflows/ci.yml      # macos-latest：tests + smoke + dry-e2e
```

---

## Limitations

- **無復原堆疊。** 復原路徑僅有：原生 Trash、執行目錄下的 `archive/` tar 檔、遷移目標卷宗。
- **不依賴 cron，不進行背景執行。** 每次執行均由使用者明確觸發。
- **不上傳雲端，不收集 telemetry。** 執行目錄僅保留於本機。
- **不觸及 SIP 保護路徑**，不解除安裝 `/Applications/*.app`。
- **專案根識別僅依賴 `.git`。** 標準 git 工作區可識別；不含 `.git` 的專案工作區無法識別。巢狀的 git submodule 會被去重，不作為獨立專案出現。
- **專案產物發現不遵循 `.gitignore`**——僅按固定慣例的子目錄名稱（`node_modules`、`target` 等）掃描。可能包含被 git 忽略的目錄，也可能遺漏專案自訂的非慣例目錄。
- **單機驗證。** 開發與測試均在 macOS 25.x / 26.x 與開發者工具鏈上完成。尚未在 Apple Silicon 與 Intel、以及更早版本的 macOS 之間完成交叉驗證。

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # 真實檔案系統 sanity 測試
./scripts/dry-e2e.sh                        # 非 LLM 端到端
```

每次 push / PR 時，CI 在 `macos-latest` 上透過 `.github/workflows/ci.yml` 執行上述三項檢查。

不可協商的不變量（agent 不直接寫入檔案系統、隱私脫敏強制執行等）詳見 `CLAUDE.md`；版本變更紀錄詳見 `CHANGELOG.md`。

---

## License

Apache-2.0（見 `LICENSE` 與 `NOTICE`）。

## Credits

由 [@heyiamlin](https://x.com/heyiamlin) 設計並實作。若此 skill 幫你釋放了磁碟空間，歡迎帶上 `#macspaceclean` 話題分享。
