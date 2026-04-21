# mac-space-cleanup skill

[English](README.md) · **简体中文** · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

[![CI](https://github.com/skillx-run/mac-space-cleanup/actions/workflows/ci.yml/badge.svg)](https://github.com/skillx-run/mac-space-cleanup/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/skillx-run/mac-space-cleanup)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/skillx-run/mac-space-cleanup?sort=semver)](https://github.com/skillx-run/mac-space-cleanup/releases)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey?logo=apple)](https://www.apple.com/macos/)
[![Python 3](https://img.shields.io/badge/python-3-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pip deps: 0](https://img.shields.io/badge/pip%20deps-0-brightgreen)](#)
[![i18n: 8 locales](https://img.shields.io/badge/i18n-8%20locales-blueviolet)](#)

一个清理 Mac 磁盘空间的 skill。

> 工作流分六个阶段：模式选择、环境探测、扫描、分级、二次确认、报告。每个候选对象按 L1-L4 分级；所有文件系统写操作统一经由 `safe_delete.py`，该脚本内置 blocklist，并与隐私 reviewer 子 agent、渲染后校验器共同构成三层护栏。Trash 中待清空的字节单独计数，不计入"已释放"数值。零 pip 依赖，仅使用 macOS 自带命令与 Python 标准库。

---

## 为什么选这个 skill

固定规则的清理工具（CleanMyMac、OnyX）只处理规则明确的条目：某个 `node_modules` 是否仍被项目使用、`~/Library/Caches` 中哪些目录对应活跃的用户偏好、哪些已是残留，规则无法判断，只能保守跳过，遗留大量本可清理的内容。

直接让 agent 清理（"Claude，清理一下我的 Mac"）能覆盖这些灰色地带，但缺少硬性边界——一次误判就可能触及 `.git` / `.env` / Keychains。

这个 skill 先建立安全边界：`safe_delete.py` 的 blocklist、隐私 reviewer、渲染后校验器三层护栏在运行时拒绝上述关键路径。在此前提下，判断权完整交给 agent，处理规则工具覆盖不到的灰色地带。

---

<!-- skillx:begin:setup-skillx -->
## 用 skillx 一键试用

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

无需安装即可直接运行：

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "清理一下我的 Mac。"
```

如需仅预览而不实际执行，在触发语中加入 `--dry-run`。skill 仍会完整执行六个阶段，但 `safe_delete.py` 不会写入文件系统（仅写入运行目录下的 `actions.jsonl`）。

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "深度清理一下我的 Mac，加上 --dry-run 先预览一下，不要真的删文件。"
```

由 [skillx](https://skillx.run) 驱动——一条命令完成任何 agent skill 的拉取、扫描、注入与运行。
<!-- skillx:end:setup-skillx -->

---

## Demo

报告语言由触发 skill 的对话语言决定，每次运行单一语言。下图为首屏效果，左侧英文、右侧中文，取自两次独立运行。

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="mac-space-cleanup 报告首屏，英文" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="mac-space-cleanup 报告首屏，中文" /></td>
</tr>
</table>

整页报告（影响总览 · 类别分布 · 动作明细 · 观察结论 · 运行详情 · L1–L4 风险分布）：
[英文整页](assets/mac-space-cleanup.full.en.png) · [中文整页](assets/mac-space-cleanup.full.zh.png)

---

## Install

持久安装通过 skillx 完成。如果尚未安装 skillx CLI：

```bash
curl -fsSL https://skillx.run/install.sh | sh
```

然后将此 skill 安装到 skillx 识别的任意 agent harness 的 skills 目录（Claude Code 的 `~/.claude/skills/` 等）：

```bash
skillx install https://github.com/skillx-run/mac-space-cleanup
```

启动一个新的 agent 会话以刷新 skill 列表。后续更新或卸载使用 `skillx update mac-space-cleanup` / `skillx uninstall mac-space-cleanup`。

建议同时安装 `trash`（`brew install trash`）。未安装时 `safe_delete.py` 会回退为使用 `mv` 将文件移入 `~/.Trash`，但文件名会附加时间戳后缀。

---

## Use

在 agent 会话中使用类似的触发语：

| 触发语 | Skill 选择 |
| --- | --- |
| "quick clean"、"马上腾点空间"、"先清一波" | `quick` 模式（自动清理低风险项，约 30 秒） |
| "deep clean"、"深度清理"、"找大头"、"分析空间" | `deep` 模式（完整审计，高风险项逐项确认，约 2–5 分钟） |
| "clean my Mac"、"Mac 空间满了"（语义模糊） | Skill 会询问使用哪种模式，并给出耗时估计 |

如需仅预览而不实际修改文件，在触发语中加入 `--dry-run`：

> "深度清理一下我的 Mac，加上 --dry-run 先预览一下，不要真的删文件。"

报告顶部会标注 dry-run 状态，每个数字前加上"预计"前缀。阿拉伯语、希伯来语、波斯语等 RTL 语言会自动添加 `<html dir="rtl">`；精细 RTL 样式调整是已知限制。

---

## Scope

清理对象（按 `references/category-rules.md` 的风险分级）：

- 开发者缓存：Xcode DerivedData、Docker build cache、Go build cache、Gradle cache、ccache、sccache、JetBrains、Flutter SDK、VSCode 系编辑器缓存（Code / Cursor / Windsurf / Zed `blob_store`）。
- 包管理器缓存：Homebrew、npm、pnpm、yarn、pip、uv、Cargo、CocoaPods、RubyGems、Bundler、Composer、Poetry、Dart pub、Bun、Deno、Swift PM、Carthage。版本管理器（nvm / fnm / pyenv / rustup）逐版本列出非活跃条目，活跃的 pin 通过读取各项目的 `.python-version` / `.nvmrc` 自动排除。
- AI/ML 模型缓存：HuggingFace（`hub/` L2 trash、`datasets/` L3 defer）、PyTorch hub、Ollama（L3 defer；deep 模式下以 `ollama:<name>:<tag>` 按模型分发，通过 blob 引用计数确保不同 tag 共享的 layer 在删除某一 tag 时仍然保留）、LM Studio、OpenAI Whisper、Weights & Biases 全局缓存。Conda / Mamba / Miniforge 的非 `base` env，覆盖七种常见的 macOS 安装布局。
- 前端工具链：Playwright 浏览器 + driver、Puppeteer 捆绑的浏览器。
- iOS/watchOS/tvOS 模拟器运行时（通过 `xcrun simctl delete`，非 `rm -rf`）。iOS `DeviceSupport/<OS>` 条目中 major.minor 与当前已配对物理设备或可用模拟器 runtime 匹配者，将被自动降级为 L3 defer。
- `~/Library/Caches/*` 下的应用缓存、saved application state，以及 Trash 本身。创作类应用缓存（Adobe Media Cache / Peak Files、Final Cut Pro、Logic Pro）使用具体标签，而非通用的 `"System caches"`。
- 日志、崩溃报告。
- `~/Downloads` 下超过 30 天的老旧安装包（`.dmg / .pkg / .xip / .iso`）。
- Time Machine 本地快照（通过 `tmutil deletelocalsnapshots`）。
- 项目构建产物（仅 deep 模式；通过 `scripts/scan_projects.py` 扫描任何带 `.git` 根的目录）：
  - L1 直接删除：`node_modules`、`target`、`build`、`dist`、`out`、`.next`、`.nuxt`、`.svelte-kit`、`.turbo`、`.parcel-cache`、`__pycache__`、`.pytest_cache`、`.tox`、`.mypy_cache`、`.ruff_cache`、`.dart_tool`、`.nyc_output`、`_build`（仅 Elixir 项目）、`Pods`、`vendor`（仅 Go 项目）。
  - L2 移入 Trash：`.venv`、`venv`、`env`（Python 虚拟环境——wheel 版本固定后可能无法完全复现，因此保留回收窗口）；`coverage`（测试覆盖率报告，按 `package.json` 或 Python marker 判定）；`.dvc/cache`（DVC 的内容寻址缓存，按同级 `.dvc/config` marker 判定；父目录 `.dvc/` 含用户状态，予以保留）。
  - 系统 / 包管理器目录（`~/Library`、`~/.cache`、`~/.npm`、`~/.cargo`、`~/.cocoapods`、`~/.gradle`、`~/.m2`、`~/.gem`、`~/.bundle`、`~/.composer`、`~/.pub-cache`、`~/.local`、`~/.rustup`、`~/.pnpm-store`、`~/.Trash`）在项目发现阶段被剪枝。
- 孤儿大目录扫描（仅 deep 模式）：`~` 下 ≥ 2 GiB 且未匹配任何规则的目录标为 L3 defer（`source_label="Unclassified large directory"`）。定稿前 agent 会执行一次短暂的只读调查（每个候选最多 6 次命令）以细化 category 与 source_label；无论调查结果如何，L3 defer 档位均被锁定。

硬性兜底——无论 `confirmed.json` 中的内容如何均拒绝执行，见 `scripts/safe_delete.py` 中的 `_BLOCKED_PATTERNS`：

- `.git`、`.ssh`、`.gnupg` 目录。
- `~/Library/Keychains`、`~/Library/Mail`、`~/Library/Messages`、`~/Library/Mobile Documents`（iCloud Drive）。
- Photos Library、Apple Music 媒体库。
- `.env*` 文件、SSH 私钥文件（`id_rsa`、`id_ed25519` 等）。
- VSCode 系编辑器状态：`{Code, Cursor, Windsurf}/{User, Backups, History}`（未保存的编辑、git-stash 等价物、本地编辑历史）。
- Adobe 创作类应用的 `Auto-Save` 目录——未保存的 Premiere / After Effects / Photoshop 工程文件。

---

## Architecture

`SKILL.md` 是 agent 的工作流契约：模式选择、分类、对话、HTML 渲染均由 agent 完成。两个 Python 脚本承担 agent 不适合处理的职责——`scripts/safe_delete.py` 是文件系统写操作的唯一入口，提供六种动作分发、幂等性与逐项错误隔离；`scripts/collect_sizes.py` 使用标准库并行执行 `du -sk`。`references/` 是 agent 的知识库，`assets/` 是报告模板。Stage 6 通过两层 reviewer / validator 在用户看到报告前拦截隐私泄漏。每次运行的工作目录位于 `~/.cache/mac-space-cleanup/run-XXXXXX/`。

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # agent 主工作流（六阶段）
├── scripts/
│   ├── safe_delete.py            # 六种动作分发器 + blocklist 硬性兜底
│   ├── collect_sizes.py          # 并行 du -sk
│   ├── scan_projects.py          # 查找 .git 根项目 + 枚举可清理产物
│   ├── aggregate_history.py      # 跨运行置信度聚合器（Stage 5 HISTORY_BY_LABEL） + run-* GC
│   ├── validate_report.py        # 渲染后校验（region / placeholder / 泄漏 / dry-run 标记）
│   ├── smoke.sh                  # 真实文件系统冒烟测试
│   └── dry-e2e.sh                # 非 LLM 端到端 harness
├── references/
│   ├── cleanup-scope.md          # 白名单 / 黑名单（与 safe_delete blocklist 交叉引用）
│   ├── safety-policy.md          # L1-L4 分级 + 隐私脱敏 + 降级
│   ├── category-rules.md         # 10 个类别的匹配规则 + risk_level + action
│   └── reviewer-prompts.md       # 隐私 reviewer 子 agent 的 prompt 模板
├── assets/
│   ├── report-template.html      # 带成对标记的六区域 HTML 模板
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 X 分享卡
├── tests/                        # 纯标准库 unittest 套件
├── CHANGELOG.md
├── CLAUDE.md                     # 贡献者必读的不变量
└── .github/workflows/ci.yml      # macos-latest：tests + smoke + dry-e2e
```

---

## Limitations

- **无撤销栈。** 恢复路径仅有：原生 Trash、运行目录下的 `archive/` tar 包、迁移目标卷。
- **不依赖 cron，不进行后台运行。** 每次运行均由用户显式触发。
- **不上传云端，不收集 telemetry。** 运行目录仅保留于本地。
- **不触及 SIP 保护路径**，不卸载 `/Applications/*.app`。
- **项目根识别仅依赖 `.git`。** 标准 git 工作区可识别；不含 `.git` 的项目工作区无法识别。嵌套的 git submodule 会被去重，不作为独立项目出现。
- **项目产物发现不遵循 `.gitignore`**——仅按固定约定的子目录名（`node_modules`、`target` 等）扫描。可能包含被 git 忽略的目录，也可能遗漏项目自定义的非约定目录。
- **单机验证。** 开发与测试均在 macOS 25.x / 26.x 与开发者工具链上完成。尚未在 Apple Silicon 与 Intel、以及更早版本的 macOS 之间完成交叉验证。

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # 真实文件系统 sanity 测试
./scripts/dry-e2e.sh                        # 非 LLM 端到端
```

每次 push / PR 时，CI 在 `macos-latest` 上通过 `.github/workflows/ci.yml` 执行上述三项检查。

不可协商的不变量（agent 不直接写文件系统、隐私脱敏强制执行等）详见 `CLAUDE.md`；版本变更记录详见 `CHANGELOG.md`。

---

## License

Apache-2.0（见 `LICENSE` 与 `NOTICE`）。

## Credits

由 [@heyiamlin](https://x.com/heyiamlin) 设计并实现。若此 skill 帮你释放了磁盘空间，欢迎带上 `#macspaceclean` 话题分享。
