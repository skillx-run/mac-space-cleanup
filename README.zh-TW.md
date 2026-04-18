# mac-space-cleanup

[English](README.md) · [简体中文](README.zh-CN.md) · **繁體中文** · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

一個**由 agent 驅動**的 macOS 磁碟空間清理工作流程，以 agent skill 形式交付。作者 [@heyiamlin](https://x.com/heyiamlin)。

> 本 skill 透過六階段工作流程（模式選擇 → 環境探測 → 掃描 → 分級 → 二次確認 → 報告）驅動 agent 完成清理，具備 **L1–L4 風險分級**、**誠實的回收量統計**（拆分為 `freed_now` / `pending_in_trash` / `archived` 三項）和**多重安全兜底**（程式碼內建的確定性封鎖清單、一個負責隱私脫敏的 reviewer 子 agent，以及渲染後驗證器）。零 pip 相依——純 macOS 指令加 Python 標準函式庫。

---

## Demo

報告會根據你觸發 skill 時所使用的語言自動**在地化**——每次執行單一語系，無執行時切換。用英文觸發即輸出英文報告；用中文觸發即輸出中文報告；用日文、西班牙文、法文等觸發，就是那種語言。下圖為首屏印象（左英、右中，來自兩次獨立執行），下方附整頁截圖連結。

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

任何支援載入 skill 的 agent harness 都可以用這個 skill。下面的指令採用 `~/.claude/skills/` 這個常見路徑；若你的 harness 使用其他 skills 目錄，替換成對應路徑即可。

```bash
git clone git@github.com:skillx-run/mac-space-cleanup.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-cleanup" ~/.claude/skills/mac-space-cleanup
```

然後重新載入你的 harness，讓 skill 清單刷新（多數 harness 重新開啟一個工作階段即可）。

### Recommended optional dependency

```bash
brew install trash
```

缺少 `trash` CLI 時，`safe_delete.py` 會退回到用 `mv` 把檔案搬到 `~/.Trash`（並追加 `-<timestamp>` 後綴）——功能可用，但後綴在 Finder 裡看著有點怪。首次執行時 skill 本身也會提醒你安裝一下。

---

## Use

在你的 agent 工作階段裡說類似這樣的話：

| 你說… | Skill 選擇 |
| --- | --- |
| "quick clean"、"馬上騰點空間"、"先清一波" | `quick` 模式（自動清理低風險項，約 30 秒） |
| "deep clean"、"深度清理"、"找大頭"、"分析空間" | `deep` 模式（完整稽核，高風險項逐項確認，約 2–5 分鐘） |
| "clean my Mac"、"Mac 空間滿了"（語意模糊） | Skill 會反問你選哪種模式，並給出耗時估計 |

想預演一遍但不真的改檔案，在你的觸發語裡加 `--dry-run`：

> "深度清理一下我的 Mac，但請用 --dry-run 模式不真的刪任何檔案"

報告頂部會明顯標出 `DRY-RUN — no files touched`（會翻譯為你觸發語言的對應文案），並在每個數字前加上目標語言的「預計」前綴。

### Report language

HTML 報告是**每次執行單一語系**，用哪種語言觸發就輸出哪種。Agent 從你的觸發訊息裡偵測工作階段語言，把結果（形如 `en`、`zh`、`ja`、`es`、`ar` 的 BCP-47 語言子標籤）寫入執行目錄，然後把所有自然語言節點——首屏標語、操作原因、觀察結論、source_label 呈現、dry-run 文案——都直接用那種語言撰寫。模板裡的靜態標籤（章節標題、按鈕文字、表頭）以英文作為基線；非英文執行時 agent 一次把它們翻譯到一個內嵌字典裡，頁面載入時 hydrate 替換。無執行時切換、無雙語 DOM——工作階段語言說了算。

從右至左書寫的語言（阿拉伯文、希伯來文、波斯文）會自動帶上 `<html dir="rtl">`；基礎方向翻轉可用，精細 RTL CSS 調整是已知限制。

---

## What it touches (and never touches)

**清理對象**（依 `references/category-rules.md` 的風險分級）：

- 開發者快取：Xcode DerivedData、Docker build cache、Go build cache、Gradle cache。
- 套件管理器快取：Homebrew、npm、pnpm、yarn、pip、uv、Cargo、CocoaPods。
- iOS/watchOS/tvOS 模擬器執行環境（透過 `xcrun simctl delete`，**絕不使用 `rm -rf`**）。
- `~/Library/Caches/*` 下的應用程式快取、saved application state、以及 Trash 本身。
- 記錄檔、當機報告。
- `~/Downloads` 下超過 30 天的舊安裝檔（`.dmg / .pkg / .xip / .iso`）。
- Time Machine 本機快照（透過 `tmutil deletelocalsnapshots`）。
- **專案建置產物**（僅 deep 模式；透過 `scripts/scan_projects.py` 掃描任何帶 `.git` 根的目錄）：
  - L1 直接刪除：`node_modules`、`target`、`build`、`dist`、`out`、`.next`、`.nuxt`、`.svelte-kit`、`.turbo`、`.parcel-cache`、`__pycache__`、`.pytest_cache`、`.tox`、`Pods`、`vendor`（僅 Go 專案）。
  - L2 移入 Trash：`.venv`、`venv`、`env`（Python 虛擬環境——wheel 版本固定後可能無法完全重現，所以留個回收期）。
  - 系統 / 套件管理器目錄（`~/Library`、`~/.cache`、`~/.npm`、`~/.cargo`、`~/.cocoapods`、`~/.gradle`、`~/.m2`、`~/.gem`、`~/.bundle`、`~/.local`、`~/.rustup`、`~/.pnpm-store`、`~/.Trash`）會在專案發現階段被剪枝。

**硬性兜底 —— 無論 `confirmed.json` 寫了什麼都會拒絕執行**（見 `scripts/safe_delete.py` 裡的 `_BLOCKED_PATTERNS`）：

- `.git`、`.ssh`、`.gnupg` 目錄。
- `~/Library/Keychains`、`~/Library/Mail`、`~/Library/Messages`、`~/Library/Mobile Documents`（iCloud Drive）。
- Photos Library、Apple Music 資料庫。
- `.env*` 檔案、SSH 私鑰檔案（`id_rsa`、`id_ed25519`……）。

Agent 本身會讀 `references/cleanup-scope.md` 取得面向使用者的白名單 / 黑名單——上面的 blocklist 是在執行時強制實施的子集。

---

## Architecture (one paragraph)

`SKILL.md` 是工作流程契約——judgement 部分（模式選擇、分類、對話、HTML 渲染）全由 agent 完成。兩個小 Python 指令稿負責 agent 不適合做的事：`scripts/safe_delete.py` 是檔案系統寫入動作的**唯一**通路（六種分派動作：delete / trash / archive / migrate / defer / skip；冪等；逐項錯誤隔離；追加式 `actions.jsonl` 稽核日誌）；`scripts/collect_sizes.py` 並行執行 `du -sk`，每條路徑 30 秒逾時，結構化 JSON 輸出。三份 reference 文件（`references/`）是 agent 的知識庫。三份 asset 模板（`assets/`）是 agent 填空的報告骨架。Stage 6 裡的兩層 reviewer / validator 會在使用者看到報告前抓出隱私洩漏。每次執行的執行目錄位於 `~/.cache/mac-space-cleanup/run-XXXXXX/`。

---

## Honesty contract

所有磁碟清理工具都喜歡把「釋放了 N GB」的數字往大了吹——把推進 Trash 的部分也算進去。但 macOS 在你清空 `~/.Trash` 之前，根本不會真正釋放那部分磁碟空間。本 skill 把這項指標拆開：

- `freed_now_bytes` —— 真正從磁碟下來的（直接刪除 + 遷移到其他卷宗）。
- `pending_in_trash_bytes` —— 躺在 `~/.Trash` 裡的；報告裡會給一條 `osascript` 一行指令供你清空。
- `archived_source_bytes` / `archived_count` —— 被打包進執行目錄下 tar 裡的位元組數 / 檔案數。
- `reclaimed_bytes` —— 向後相容別名，等於 `freed_now + pending_in_trash`。分享文案和報告標題用的是 `freed_now_bytes`，不是這個。

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # agent 主工作流程（六階段）
├── scripts/
│   ├── safe_delete.py            # 六種動作分派器 + blocklist 硬性兜底
│   ├── collect_sizes.py          # 並行 du -sk
│   ├── scan_projects.py          # 尋找 .git 根專案 + 列舉可清產物
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
│   ├── report-template.html      # 帶成對標記的六區塊 HTML 骨架
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 X 分享卡
├── tests/                        # 純標準函式庫 unittest 套件
├── docs/                         # README 截圖
├── CHANGELOG.md
├── CLAUDE.md                     # 貢獻者必讀的不變量
└── .github/workflows/ci.yml      # macos-latest：tests + smoke + dry-e2e
```

---

## Limitations & non-goals (v0.7)

- **沒有復原堆疊。** 復原路徑只有：原生 Trash、執行目錄下的 `archive/` tar 檔、遷移目標卷宗。
- **不跑 cron，不做背景執行。** 每次執行都由使用者明確觸發。
- **不上雲，不做 telemetry。** 執行目錄只留在本機。
- **不碰 SIP 保護路徑**，不解除安裝 `/Applications/*.app`。
- **專案根識別僅依賴 `.git`。** 純淨的 git 工作區能識別；沒有 `.git` 的專案工作區識別不到。巢狀的 git submodule 會去重，不會作為獨立專案出現。
- **專案產物發現不遵守 `.gitignore`**——只按固定慣例的子目錄名稱（`node_modules`、`target`、……）掃描。可能掃出被 git 忽略的目錄，也可能漏掉專案自創非慣例目錄。
- **單機驗證。** 開發和測試均在 macOS 25.x / 26.x + 開發者工具鏈上完成。尚未在 Apple Silicon / Intel、或更早的 macOS 版本之間做交叉驗證。

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # 真實檔案系統 sanity 測試
./scripts/dry-e2e.sh                        # 非 LLM 端到端
```

每次 push / PR 時，CI 在 `macos-latest` 上透過 `.github/workflows/ci.yml` 跑完以上三項。

不可協商的不變量（agent 不直接寫檔案系統、隱私脫敏強制執行等）見 `CLAUDE.md`；版本變更紀錄見 `CHANGELOG.md`。

---

## License

Apache-2.0（見 `LICENSE` 和 `NOTICE`）。

## Credits

由 [@heyiamlin](https://x.com/heyiamlin) 設計並實作。如果這個 skill 幫你空出了磁碟空間，歡迎帶上 `#macspaceclean` 話題分享。
