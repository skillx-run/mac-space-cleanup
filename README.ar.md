# mac-space-cleanup · macOS cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · **العربية** · [Deutsch](README.de.md)

**skill** لتنظيف مساحة القرص على جهاز Mac — حذِر، صادق، متعدّد المراحل.

> يقود هذا الـ skill وحدة agent عبر عملية تنظيف من سبع مراحل (اختيار الوضع ← استكشاف البيئة ← مسح ← تصنيف ← تأكيد ← تقرير ← فتح)، مع **تصنيف مخاطر بأربعة مستويات L1–L4**، و**محاسبة صادقة لِما أُفرِغ فعلاً** (مُقسَّمة إلى `freed_now` / `pending_in_trash` / `archived`)، وعدة **طبقات أمان احتياطية** (blocklist حتمية داخل الشيفرة، وsub-agent مراجع للخصوصية، ومُحقِّق بعد العرض). بدون أي اعتمادية pip — فقط أوامر macOS ومكتبة Python القياسية.

---

## Demo

يصدر التقرير **مُترجَماً** باللغة التي شغَّلت بها الـ skill — لغة واحدة لكل تشغيلة، بلا مُبدِّل أثناء التشغيل. شغِّل بالإنجليزية ← تقرير إنجليزي، بالصينية ← تقرير صيني، باليابانية أو الإسبانية أو الفرنسية… ← بتلك اللغة. أدناه الشاشة الأولى (EN على اليسار، ZH على اليمين، من تشغيلتين منفصلتين)، ثم روابط اللقطات كاملة الصفحة. نوفِّر حالياً لقطتين تجريبيتين فقط بالإنجليزية والصينية؛ أما الـ skill نفسه فيُنتج تقريراً كاملاً **بلغة هذه الصفحة** (العربية) عند تشغيله بها.

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="تقرير mac-space-cleanup، الشاشة الأولى، بالإنجليزية" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="تقرير mac-space-cleanup، الشاشة الأولى، بالصينية" /></td>
</tr>
</table>

التقرير الكامل (ملخص الأثر · التوزيع · السجل التفصيلي · الملاحظات · تفاصيل التشغيل · توزيع المخاطر L1–L4):
[الصفحة الكاملة بالإنجليزية](assets/mac-space-cleanup.full.en.png) · [الصفحة الكاملة بالصينية](assets/mac-space-cleanup.full.zh.png)

---

## Install

يصلح هذا الـ skill لأي agent harness يَعرف تحميل الـ skills. يستخدم الأمر أدناه المسار الشائع `~/.claude/skills/`؛ إن كان harness لديك يستخدم مُجلَّد skills مختلفاً فاستبدل المسار بما يناسبه.

```bash
git clone git@github.com:skillx-run/mac-space-cleanup.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-cleanup" ~/.claude/skills/mac-space-cleanup
```

ثم أَعِد تحميل harness ليَلتقط قائمة الـ skills الإدخال الجديد (في معظم الـ harness: يكفي فتح جلسة جديدة).

### Recommended optional dependency

```bash
brew install trash
```

إن لم يكن CLI باسم `trash` مُثبَّتاً، فسيتراجع `safe_delete.py` إلى استخدام `mv` لنقل الملفات إلى `~/.Trash` (مع لاحقة `-<timestamp>`) — يعمل، لكن اللاحقة تبدو غريبة في Finder. يُنبِّهك الـ skill نفسه إلى ذلك في أول تشغيل.

---

## Use

في محادثتك مع الـ agent، قُل شيئاً من قبيل:

| أنت تقول… | الـ skill يختار |
| --- | --- |
| «تنظيف سريع»، «فرّغ مساحة بسرعة»، «نظِّف قليلاً» | وضع `quick` (ينظِّف العناصر منخفضة الخطورة آلياً، نحو 30 ثانية) |
| «تنظيف عميق»، «حلِّل المساحة»، «ابحث عن الملفات الكبيرة» | وضع `deep` (تدقيق كامل، ويسأل عن كل عنصر خَطِر على حدة، نحو 2–5 دقائق) |
| «نظِّف الماك»، «الماك ممتلئ» (غامض) | يسألك الـ skill أن تختار أحد الوضعين، مع تقدير للوقت |

للمعاينة دون لمس نظام الملفات، أضف `--dry-run` إلى رسالتك:

> «نظِّف الماك تنظيفاً عميقاً، لكن في وضع --dry-run بلا حذف فعلي»

سيعرض التقرير بوضوح في أعلاه `DRY-RUN — no files touched` (مُترجَماً إلى لغة التشغيل)، وسيُضاف إلى كل رقم ما يكافئ «سيتم تحريره» بلغة الهدف.

### Report language

تقرير HTML **بلغة واحدة لكل تشغيلة**، تماماً باللغة التي شغَّلت بها الـ skill. يكشف الـ agent لغة المحادثة من الرسالة المُشغِّلة، ويكتب قيمتها (سابقة BCP-47 مثل `en`، `zh`، `ja`، `es`، `ar`) في workdir، ثم يكتب كل عقدة لغوية طبيعية — العنوان الرئيسي، وأسباب الإجراءات، والملاحظات، وعرض source_label، ونصوص dry-run — مباشرة بتلك اللغة. أما التسميات الثابتة (عناوين الأقسام، نصوص الأزرار، رؤوس الأعمدة) فتأتي في القالب بخط أساس إنجليزي؛ وفي التشغيلات غير الإنجليزية يُترجِمها الـ agent دفعة واحدة إلى قاموس مضمَّن يُرطِّب الصفحة عند التحميل. لا مُبدِّل أثناء التشغيل، ولا DOM ثنائي اللغة — لغة المحادثة تحسم الأمر.

تتلقى الكتابات من اليمين إلى اليسار (العربية والعبرية والفارسية) سمة `<html dir="rtl">`؛ قلب الاتجاه الأساسي يعمل، وضبط CSS للـ RTL بدقة هو حَدٌّ معروف.

---

## What it touches (and never touches)

**يُنظِّف** (مع تصنيف مخاطر وفق `references/category-rules.md`):

- كاشات المطوِّرين: Xcode DerivedData، Docker build cache، Go build cache، Gradle cache، ccache، sccache.
- كاشات مديري الحِزَم: Homebrew، npm، pnpm، yarn، pip، uv، Cargo، CocoaPods، RubyGems، Bundler، Composer، Poetry، Dart pub.
- أزمنة تشغيل محاكيات iOS/watchOS/tvOS (عبر `xcrun simctl delete`، **لا يستخدم `rm -rf` إطلاقاً**).
- كاشات التطبيقات تحت `~/Library/Caches/*`، وsaved application state، وسلة المهملات Trash ذاتها.
- السجلات وتقارير الأعطال.
- المُثبِّتات القديمة في `~/Downloads` (`.dmg / .pkg / .xip / .iso` التي تجاوزت 30 يوماً).
- لقطات Time Machine المحلية (عبر `tmutil deletelocalsnapshots`).
- **مخرجات بناء المشاريع** (في وضع deep فقط، تُمسح بواسطة `scripts/scan_projects.py` لأي مجلَّد يملك جذراً بـ `.git`):
  - L1 حذف مباشر: `node_modules`، `target`، `build`، `dist`، `out`، `.next`، `.nuxt`، `.svelte-kit`، `.turbo`، `.parcel-cache`، `__pycache__`، `.pytest_cache`، `.tox`، `.mypy_cache`، `.ruff_cache`، `.dart_tool`، `.nyc_output`، `_build` (مشاريع Elixir فقط)، `Pods`، `vendor` (مشاريع Go فقط).
  - L2 إلى Trash: `.venv`، `venv`، `env` (بيئات Python الافتراضية — قد لا تُستنسخ wheel pins حرفياً، ولذلك نترك نافذة استرداد)؛ `coverage` (تقارير تغطية الاختبارات، مشروطة بوجود `package.json` أو marker بايثون).
  - مجلَّدات النظام / مديري الحِزَم (`~/Library`، `~/.cache`، `~/.npm`، `~/.cargo`، `~/.cocoapods`، `~/.gradle`، `~/.m2`، `~/.gem`، `~/.bundle`، `~/.composer`، `~/.pub-cache`، `~/.local`، `~/.rustup`، `~/.pnpm-store`، `~/.Trash`) يتمُّ تقليمها عند اكتشاف المشاريع.
- **وضع deep يُبرز أيضاً المجلَّدات تحت `~` التي يبلغ حجمها 2 ج.ب. فأكثر ولم تلتقطها أي قاعدة أخرى** (L3 defer، `source_label="Unclassified large directory"`)، بحيث تصبح المجلَّدات اليتيمة المُلتهمة للقرص مرئيَّةً للمراجعة اليدويَّة.

**جدار احتياطي صلب — يرفض بصرف النظر عن محتوى `confirmed.json`** (انظر `_BLOCKED_PATTERNS` في `scripts/safe_delete.py`):

- مجلَّدات `.git` و`.ssh` و`.gnupg`.
- `~/Library/Keychains`، `~/Library/Mail`، `~/Library/Messages`، `~/Library/Mobile Documents` (iCloud Drive).
- مكتبة Photos ومكتبة Apple Music.
- ملفات `.env*`، ومفاتيح SSH الخاصة (`id_rsa`، `id_ed25519`…).

يقرأ الـ agent نفسه `references/cleanup-scope.md` للاطلاع على whitelist / blacklist الموجَّهة للمستخدم — والـ blocklist أعلاه هي المجموعة الفرعية المُنفَّذة عند التشغيل.

---

## Architecture (one paragraph)

`SKILL.md` هو عقد سير العمل — يتولَّى الـ agent جانب الاجتهاد (اختيار الوضع، والتصنيف، والمحادثة، وعرض HTML). ثمة سكربتا Python صغيران يقومان بما لا يلزم أن يفعله الـ agent: `scripts/safe_delete.py` هو المسار **الوحيد** الذي تحدث من خلاله كتابات نظام الملفات (ستُّ عمليات موزَّعة: delete / trash / archive / migrate / defer / skip؛ idempotent؛ عزل أخطاء لكل عنصر؛ سجل `actions.jsonl` للإلحاق فقط)؛ و`scripts/collect_sizes.py` يُشغِّل `du -sk` بالتوازي مع مهلة 30 ثانية لكل مسار، وإخراج JSON منظَّم. ثلاث وثائق مرجعية (`references/`) هي قاعدة معرفة الـ agent. ثلاثة قوالب أصول (`assets/`) هي هيكل التقرير الذي يملؤه الـ agent. طبقتا reviewer / validator في Stage 6 تلتقطان تسريبات الخصوصية قبل أن يرى المستخدم التقرير. يقع workdir كل تشغيلة في `~/.cache/mac-space-cleanup/run-XXXXXX/`.

---

## Honesty contract

كلُّ أداة تنظيف قرص تُضخِّم رقم «أفرغت N GB» بحساب ما دفعته إلى سلة المهملات. لا يُحرِّر macOS تلك المساحة فعلاً إلا حين تُفرِغ `~/.Trash`. يُقسِّم هذا الـ skill المقياس:

- `freed_now_bytes` — تحرَّر من القرص فعلياً (delete + migrate إلى مُجلَّد آخر).
- `pending_in_trash_bytes` — قابع في `~/.Trash`؛ يَعرض التقرير سطر `osascript` واحداً لتفريغها.
- `archived_source_bytes` / `archived_count` — بايتات مُغلَّفة داخل tar في workdir.
- `reclaimed_bytes` — اسم مستعار للتوافق الخلفي = `freed_now + pending_in_trash`. نصُّ المشاركة وعنوان التقرير الرئيسي يستخدمان `freed_now_bytes`، لا هذا.

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # سير عمل agent الرئيسي (سبع مراحل)
├── scripts/
│   ├── safe_delete.py            # مُوزِّع العمليات الست + blocklist الاحتياطية
│   ├── collect_sizes.py          # du -sk بالتوازي
│   ├── scan_projects.py          # إيجاد المشاريع ذات جذر .git + سرد المخرجات القابلة للتنظيف
│   ├── aggregate_history.py      # مُجمِّع الثقة عبر التشغيلات (Stage 5 HISTORY_BY_LABEL) + GC لـ run-*
│   ├── validate_report.py        # فحص بعد العرض (المناطق / placeholder / التسريبات / وسم dry-run)
│   ├── smoke.sh                  # اختبار دخان على نظام ملفات حقيقي
│   └── dry-e2e.sh                # harness من طرف إلى طرف دون LLM
├── references/
│   ├── cleanup-scope.md          # whitelist / blacklist (مع إحالة متقاطعة إلى blocklist في safe_delete)
│   ├── safety-policy.md          # تصنيف L1-L4 + إخفاء الخصوصية + التدرُّج
│   ├── category-rules.md         # 10 فئات ببشبهات + risk_level + action
│   └── reviewer-prompts.md       # قالب الـ prompt لِـ sub-agent المراجَعَة
├── assets/
│   ├── report-template.html      # هيكل HTML بست مناطق وعلامات مزدوجة
│   ├── report.css
│   └── share-card-template.svg   # بطاقة مشاركة X مقاس 1200×630
├── tests/                        # مجموعة unittest قياسية الاعتماديات
├── CHANGELOG.md
├── CLAUDE.md                     # ثوابت للمساهمين
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations & non-goals (v0.10.0)

- **لا مكدِّس للتراجع undo.** مسارات الاسترداد هي: سلة المهملات الأصلية، وملفات tar داخل `archive/` في workdir، ومُجلَّد الوجهة في migrate.
- **لا cron ولا تشغيل في الخلفية.** كلُّ تشغيلة يُطلِقها المستخدم صراحةً.
- **لا سحابة ولا telemetry.** يبقى workdir محلياً.
- **لا يمسُّ المسارات المحمية بـ SIP**، ولا يُزيل تطبيقات `/Applications/*.app`.
- **تعرُّف جذر المشروع يعتمد على `.git` حصراً.** يُتعرَّف على checkouts المجرَّدة، ولا يُتعرَّف على مساحات العمل بلا مُجلَّد `.git`. submodules المتداخلة تُزال تكراراتها (لا تظهر كمشاريع منفصلة).
- **اكتشاف مخرجات المشاريع لا يحترم `.gitignore`** — يمسح أسماء مُجلَّدات فرعية اصطلاحية ثابتة (`node_modules`، `target`، …). قد يُظهِر مُجلَّداً يتجاهله git، وقد يُفوِّت مُجلَّداً ينشئه المشروع خارج العُرف.
- **تحقُّق على جهاز واحد.** طُوِّر واخْتُبِر على macOS 25.x / 26.x مع سلسلة أدوات مطوِّر. لم تُدقَّق الأنماط بعدُ بين Apple Silicon وIntel، ولا عبر إصدارات macOS الأقدم.

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # sanity على نظام ملفات حقيقي
./scripts/dry-e2e.sh                        # من طرف إلى طرف دون LLM
```

تُشغِّل CI الثلاثة عند كل push / PR عبر `.github/workflows/ci.yml` على `macos-latest`.

للاطلاع على الثوابت غير القابلة للتفاوض (الـ agent لا يكتب على fs مباشرةً، إخفاء الخصوصية إلزامي، إلخ) راجع `CLAUDE.md`، وملاحظات الإصدار في `CHANGELOG.md`.

---

## License

Apache-2.0 (انظر `LICENSE` و`NOTICE`).

## Credits

من تصميم وتنفيذ [@heyiamlin](https://x.com/heyiamlin). إن وفَّر لك هذا الـ skill مساحة، شاركه مع وسم `#macspaceclean`.
