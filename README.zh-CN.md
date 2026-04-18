# mac-space-cleanup

[English](README.md) · **简体中文** · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

一个**由 agent 驱动**的 macOS 磁盘空间清理工作流，以 agent skill 形式交付。作者 [@heyiamlin](https://x.com/heyiamlin)。

> 本 skill 通过六阶段工作流（模式选择 → 环境探测 → 扫描 → 分级 → 二次确认 → 报告）驱动 agent 完成清理，带有 **L1–L4 风险分级**、**真实回收量统计**（拆分为 `freed_now` / `pending_in_trash` / `archived` 三项）和**多重安全兜底**（代码内置的确定性阻断清单、一个负责隐私脱敏的 reviewer 子 agent、以及渲染后校验器）。零 pip 依赖——纯 macOS 命令加 Python 标准库。

---

## Demo

报告会根据你触发 skill 时使用的语言自动**本地化**——每次运行单一语言，无运行时切换。用英文触发即输出英文报告；用中文触发即输出中文报告；用日语、西班牙语、法语等触发，就是那种语言。下图为首屏印象（左英、右中，来自两次独立运行），下方附整页截图链接。

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

任何支持加载 skill 的 agent harness 都可以用这个 skill。下面的命令采用 `~/.claude/skills/` 这一常见路径；如果你的 harness 另用别的 skills 目录，换成对应路径即可。

```bash
git clone git@github.com:skillx-run/mac-space-cleanup.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-cleanup" ~/.claude/skills/mac-space-cleanup
```

然后重新加载你的 harness，让 skill 列表刷新（大多数 harness 新开一个会话即可）。

### Recommended optional dependency

```bash
brew install trash
```

缺少 `trash` CLI 时，`safe_delete.py` 会回退到用 `mv` 把文件移入 `~/.Trash`（并追加 `-<timestamp>` 后缀）——功能可用，但后缀在 Finder 里看着有点怪。首次运行时 skill 本身也会提醒你装一下。

---

## Use

在你的 agent 会话里说类似这样的话：

| 你说… | Skill 选择 |
| --- | --- |
| "quick clean"、"马上腾点空间"、"先清一波" | `quick` 模式（自动清理低风险项，约 30 秒） |
| "deep clean"、"深度清理"、"找大头"、"分析空间" | `deep` 模式（完整审计，高风险项逐项确认，约 2–5 分钟） |
| "clean my Mac"、"Mac 空间满了"（语义模糊） | Skill 会反问你选哪种模式，并给出耗时估计 |

想预演一遍但不真的改文件，在你的触发语里加 `--dry-run`：

> "深度清理一下我的 Mac，但请用 --dry-run 模式不真的删任何文件"

报告顶部会明显标出 `DRY-RUN — no files touched`（会翻译为你触发语言的对应文案），并在每个数字前加上目标语言的"预计"前缀。

### Report language

HTML 报告是**每次运行单一语言**，用哪种语言触发就输出哪种。Agent 从你的触发消息里检测会话语言，把结果（形如 `en`、`zh`、`ja`、`es`、`ar` 的 BCP-47 语言子标签）写入运行目录，然后把所有自然语言节点——首屏标语、操作原因、观察结论、source_label 呈现、dry-run 文案——都直接用那种语言写。模板里的静态标签（章节标题、按钮文本、表头）以英文作为基线；非英文运行时 agent 一次性把它们翻译到一个内嵌词典里，页面加载时 hydrate 替换。无运行时切换、无双语 DOM——会话语言说了算。

右到左书写的语言（阿拉伯语、希伯来语、波斯语）会自动带上 `<html dir="rtl">`；基础方向翻转可用，精细 RTL CSS 调整是已知限制。

---

## What it touches (and never touches)

**清理对象**（按 `references/category-rules.md` 的风险分级）：

- 开发者缓存：Xcode DerivedData、Docker build cache、Go build cache、Gradle cache。
- 包管理器缓存：Homebrew、npm、pnpm、yarn、pip、uv、Cargo、CocoaPods。
- iOS/watchOS/tvOS 模拟器运行时（通过 `xcrun simctl delete`，**绝不使用 `rm -rf`**）。
- `~/Library/Caches/*` 下的应用缓存、saved application state、以及 Trash 本身。
- 日志、崩溃报告。
- `~/Downloads` 下超过 30 天的老安装包（`.dmg / .pkg / .xip / .iso`）。
- Time Machine 本地快照（通过 `tmutil deletelocalsnapshots`）。
- **项目构建产物**（仅 deep 模式；通过 `scripts/scan_projects.py` 扫描任何带 `.git` 根的目录）：
  - L1 直接删除：`node_modules`、`target`、`build`、`dist`、`out`、`.next`、`.nuxt`、`.svelte-kit`、`.turbo`、`.parcel-cache`、`__pycache__`、`.pytest_cache`、`.tox`、`Pods`、`vendor`（仅 Go 项目）。
  - L2 移入 Trash：`.venv`、`venv`、`env`（Python 虚拟环境——wheel 版本钉住后可能无法完全复现，所以留个回收窗口）。
  - 系统 / 包管理器目录（`~/Library`、`~/.cache`、`~/.npm`、`~/.cargo`、`~/.cocoapods`、`~/.gradle`、`~/.m2`、`~/.gem`、`~/.bundle`、`~/.local`、`~/.rustup`、`~/.pnpm-store`、`~/.Trash`）在项目发现阶段会被剪枝。

**硬性兜底 —— 无论 `confirmed.json` 写了什么都会拒绝执行**（见 `scripts/safe_delete.py` 里的 `_BLOCKED_PATTERNS`）：

- `.git`、`.ssh`、`.gnupg` 目录。
- `~/Library/Keychains`、`~/Library/Mail`、`~/Library/Messages`、`~/Library/Mobile Documents`（iCloud Drive）。
- Photos Library、Apple Music 媒体库。
- `.env*` 文件、SSH 私钥文件（`id_rsa`、`id_ed25519`……）。

Agent 本身会读 `references/cleanup-scope.md` 获取面向用户的白名单 / 黑名单——上面的 blocklist 是在运行时强制执行的子集。

---

## Architecture (one paragraph)

`SKILL.md` 是工作流契约——judgement 部分（模式选择、分类、对话、HTML 渲染）都由 agent 完成。两个小 Python 脚本负责 agent 不适合做的事：`scripts/safe_delete.py` 是文件系统写操作的**唯一**通路（六种分发动作：delete / trash / archive / migrate / defer / skip；幂等；逐项错误隔离；追加式 `actions.jsonl` 审计日志）；`scripts/collect_sizes.py` 并行执行 `du -sk`，每条路径 30 秒超时，结构化 JSON 输出。三份 reference 文档（`references/`）是 agent 的知识库。三份 asset 模板（`assets/`）是 agent 填空的报告骨架。Stage 6 里的两层 reviewer / validator 会在用户看到报告前抓出隐私泄漏。每次运行的运行目录位于 `~/.cache/mac-space-cleanup/run-XXXXXX/`。

---

## Honesty contract

所有磁盘清理工具都喜欢把"释放了 N GB"的数字往大了吹——把推进 Trash 的部分也算进去。但 macOS 在你清空 `~/.Trash` 之前，根本不会真正释放那部分磁盘。本 skill 把这项指标拆开：

- `freed_now_bytes` —— 真正从磁盘下来的（直接删除 + 迁移到其他卷）。
- `pending_in_trash_bytes` —— 躺在 `~/.Trash` 里的；报告里会给一条 `osascript` 一行命令供你清空。
- `archived_source_bytes` / `archived_count` —— 被打包进运行目录下的 tar 里的字节数 / 文件数。
- `reclaimed_bytes` —— 向后兼容别名，等于 `freed_now + pending_in_trash`。分享文案和报告标题用的是 `freed_now_bytes`，不是这个。

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # agent 主工作流（六阶段）
├── scripts/
│   ├── safe_delete.py            # 六种动作分发器 + blocklist 硬性兜底
│   ├── collect_sizes.py          # 并行 du -sk
│   ├── scan_projects.py          # 查找 .git 根项目 + 枚举可清产物
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
│   ├── report-template.html      # 带成对标记的六区域 HTML 骨架
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 X 分享卡
├── tests/                        # 纯标准库 unittest 套件
├── docs/                         # README 截图
├── CHANGELOG.md
├── CLAUDE.md                     # 贡献者必读的不变量
└── .github/workflows/ci.yml      # macos-latest：tests + smoke + dry-e2e
```

---

## Limitations & non-goals (v0.7)

- **没有撤销栈。** 恢复路径只有：原生 Trash、运行目录下的 `archive/` tar 包、迁移目标卷。
- **不跑 cron，不做后台运行。** 每次运行都由用户显式触发。
- **不上云，不做 telemetry。** 运行目录只留在本地。
- **不碰 SIP 保护路径**，不卸载 `/Applications/*.app`。
- **项目根识别仅依赖 `.git`。** 纯净 git 工作区能识别；没有 `.git` 的项目工作区识别不了。嵌套的 git submodule 会去重，不会作为独立项目出现。
- **项目产物发现不尊重 `.gitignore`**——只按固定约定的子目录名（`node_modules`、`target`、……）扫描。可能扫出被 git 忽略的目录，也可能漏掉项目自创非约定目录。
- **单机验证。** 开发和测试均在 macOS 25.x / 26.x + 开发者工具链上完成。尚未在 Apple Silicon / Intel、更老的 macOS 版本之间做交叉验证。

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # 真实文件系统 sanity 测试
./scripts/dry-e2e.sh                        # 非 LLM 端到端
```

每次 push / PR 时，CI 在 `macos-latest` 上通过 `.github/workflows/ci.yml` 跑完以上三项。

非可协商的不变量（agent 不直接写文件系统、隐私脱敏强制执行，等等）见 `CLAUDE.md`；版本变更记录见 `CHANGELOG.md`。

---

## License

Apache-2.0（见 `LICENSE` 和 `NOTICE`）。

## Credits

由 [@heyiamlin](https://x.com/heyiamlin) 设计并实现。如果这个 skill 帮你省出了磁盘空间，欢迎带上 `#macspaceclean` 话题分享。
