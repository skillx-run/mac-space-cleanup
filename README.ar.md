# mac-space-cleanup skill

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · **العربية** · [Deutsch](README.de.md)

[![CI](https://github.com/skillx-run/mac-space-cleanup/actions/workflows/ci.yml/badge.svg)](https://github.com/skillx-run/mac-space-cleanup/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/skillx-run/mac-space-cleanup)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/skillx-run/mac-space-cleanup?sort=semver)](https://github.com/skillx-run/mac-space-cleanup/releases)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey?logo=apple)](https://www.apple.com/macos/)
[![Python 3](https://img.shields.io/badge/python-3-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pip deps: 0](https://img.shields.io/badge/pip%20deps-0-brightgreen)](#)
[![i18n: 8 locales](https://img.shields.io/badge/i18n-8%20locales-blueviolet)](#)

skill لتنظيف مساحة القرص على جهاز Mac.

> سير عمل من ست مراحل: اختيار الوضع، استكشاف البيئة، المسح، التصنيف، التأكيد، التقرير. يُصنَّف كل مرشَّح إلى L1-L4؛ وتمرُّ كل عمليات الكتابة في نظام الملفات عبر `safe_delete.py`، الذي يحمل blocklist داخلية ويقترن بـ sub-agent مُراجِع للخصوصية ومُحقِّق بعد العرض، فيُكوِّن ثلاث طبقات من الـ guardrails. تُحسَب البايتات التي تنتظر تفريغها في الـ Trash بصورة منفصلة، ولا تُدرَج في إجمالي «المُحرَّر». بدون أي اعتمادية pip — فقط أوامر macOS ومكتبة Python القياسية.

---

## لماذا هذا الـ skill

أدوات التنظيف القائمة على القواعد (CleanMyMac، OnyX) لا تعالج إلا الإدخالات التي تُسمِّيها قواعدها: هل لا يزال `node_modules` معيَّن قيد الاستخدام، وأي المجلَّدات تحت `~/Library/Caches` تُمثِّل تفضيلات مستخدم نشطة وأيها رواسب — هذا حكم يقع خارج نطاق القواعد، فتتجاوزه هذه الأدوات بحذر وتترك حجماً معتبراً من المساحة القابلة للاسترداد دون لمس.

تفويض التنظيف لِـ agent مباشرة («Claude، نظِّف جهاز Mac») يُغطّي هذه المناطق الرمادية، لكن من دون حدود صارمة قد يُصيب خطأ تقدير واحد `.git` أو `.env` أو Keychains.

يُرسي هذا الـ skill حدَّ الأمان أولاً: تُشكِّل blocklist في `safe_delete.py` ومُراجِع الخصوصية ومُحقِّق ما بعد العرض ثلاث طبقات من الـ guardrails ترفض المسارات الحَرِجة المذكورة عند التشغيل. ضمن هذا الإطار يُفوَّض الحكم بالكامل إلى الـ agent ليتولى المناطق الرمادية التي لا تصل إليها الأدوات القائمة على القواعد.

---

<!-- skillx:begin:setup-skillx -->
## جرّبه عبر skillx

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

شغّل هذا الـ skill دون أي تثبيت:

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "نظّف جهاز Mac."
```

للمعاينة بدلاً من التنفيذ الفعلي، أَضِف `--dry-run` إلى رسالتك. يَمرُّ الـ skill بالمراحل الست كاملة، لكن `safe_delete.py` لا يكتب شيئاً إلى نظام الملفات (سوى `actions.jsonl` في workdir).

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "نظّف جهاز Mac مع --dry-run، معاينة فقط، دون حذف أي شيء فعلياً."
```

مدعوم بـ [skillx](https://skillx.run) — أمر واحد لجلب أي agent skill وفحصه وحقنه وتشغيله.
<!-- skillx:end:setup-skillx -->

---

## Demo

تُحدِّد لغة المحادثة التي تُشغِّل بها الـ skill لغةَ التقرير — لغة واحدة لكل تشغيلة. أدناه: الشاشة الأولى، الإنجليزية على اليسار والصينية على اليمين، من تشغيلتين منفصلتين.

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

التثبيت الدائم يَتمُّ عبر skillx. إذا لم يكن CLI الخاص بـ skillx مُثبَّتاً لديك بعد:

```bash
curl -fsSL https://skillx.run/install.sh | sh
```

ثمَّ ثبِّت هذا الـ skill في مُجلَّد الـ skills لأي agent harness يَعرفه skillx (مثل `~/.claude/skills/` لِـ Claude Code):

```bash
skillx install https://github.com/skillx-run/mac-space-cleanup
```

افتح جلسة agent جديدة لتحديث قائمة الـ skills. للتحديث أو إزالة التثبيت لاحقاً استخدم `skillx update mac-space-cleanup` / `skillx uninstall mac-space-cleanup`.

يُوصى بتثبيت `trash` معه (`brew install trash`). من دونه يَتراجع `safe_delete.py` إلى استخدام `mv` لنقل الملفات إلى `~/.Trash`، وتحمل أسماء الملفات المنقولة لاحقة طابع زمني.

---

## Use

في محادثتك مع الـ agent، استخدم عبارة تشغيل من قبيل:

| عبارة التشغيل | الـ skill يختار |
| --- | --- |
| «تنظيف سريع»، «فرّغ مساحة بسرعة»، «نظِّف قليلاً» | وضع `quick` (يُنظِّف العناصر منخفضة الخطورة آلياً، نحو 30 ثانية) |
| «تنظيف عميق»، «حلِّل المساحة»، «ابحث عن الملفات الكبيرة» | وضع `deep` (تدقيق كامل، تأكيد لكل عنصر خطر على حِدة، نحو 2–5 دقائق) |
| «نظِّف الماك»، «الماك ممتلئ» (غامض) | يَسألك الـ skill أن تختار، مع تقدير للوقت |

للمعاينة دون لمس نظام الملفات، أَضِف `--dry-run` إلى رسالتك:

> «نظّف جهاز Mac مع --dry-run، معاينة فقط، دون حذف أي شيء فعلياً.»

يُؤشِّر التقرير في أعلاه على حالة dry-run، ويَسبق كل رقم ما يُكافئ «سيُحرَّر». تتلقى الكتابات من اليمين إلى اليسار (العربية والعبرية والفارسية) سمة `<html dir="rtl">` تلقائياً؛ ضبط CSS الدقيق لـ RTL هو حدٌّ معروف.

---

## Scope

يُنظِّف (تصنيف المخاطر وفق `references/category-rules.md`):

- كاشات المطوِّرين: Xcode DerivedData، Docker build cache، Go build cache، Gradle cache، ccache، sccache، JetBrains، Flutter SDK، كاشات المحرِّرات من عائلة VSCode (Code / Cursor / Windsurf / Zed `blob_store`).
- كاشات مديري الحِزَم: Homebrew، npm، pnpm، yarn، pip، uv، Cargo، CocoaPods، RubyGems، Bundler، Composer، Poetry، Dart pub، Bun، Deno، Swift PM، Carthage. مديرو الإصدارات (nvm / fnm / pyenv / rustup) يُبرزون الإصدارات غير النشطة لكلٍّ منهم؛ وتُستثنى الـ pins النشطة تلقائياً عبر قراءة `.python-version` / `.nvmrc` لكل مشروع.
- كاشات نماذج AI/ML: HuggingFace (`hub/` بـ L2 trash، و`datasets/` بـ L3 defer)، PyTorch hub، Ollama (L3 defer؛ في وضع deep يتمُّ التوزيع لكلِّ نموذج بصيغة `ollama:<name>:<tag>` مع احتساب مراجع الـ blob بحيث تَبقى الطبقات المشتركة بين الوسوم على قيد الحياة عند حذف وسمٍ شقيق)، LM Studio، OpenAI Whisper، كاش Weights & Biases العام. بيئات Conda / Mamba / Miniforge غير `base` عبر سبعة تخطيطات تثبيت شائعة على macOS.
- أدوات الواجهة الأمامية: متصفِّحات Playwright + driver، والمتصفِّحات المُرفَقة مع Puppeteer.
- أزمنة تشغيل محاكيات iOS/watchOS/tvOS (عبر `xcrun simctl delete`، لا `rm -rf`). بنود `DeviceSupport/<OS>` في iOS التي يُطابق major.minor فيها جهازاً مُقترِناً حالياً أو runtime محاكاةٍ متاحة تُخفَّض تلقائياً إلى L3 defer.
- كاشات التطبيقات تحت `~/Library/Caches/*`، وsaved application state، وسلة المهملات Trash نفسها. تَستخدم كاشات تطبيقات الإبداع (Adobe Media Cache / Peak Files، Final Cut Pro، Logic Pro) وسوماً مُحدَّدة بدلاً من تصنيف `"System caches"` العام.
- السجلات وتقارير الأعطال.
- المُثبِّتات القديمة في `~/Downloads` (`.dmg / .pkg / .xip / .iso` التي تَجاوزت 30 يوماً).
- لقطات Time Machine المحلية (عبر `tmutil deletelocalsnapshots`).
- مخرجات بناء المشاريع (في وضع deep فقط؛ تُمسح بواسطة `scripts/scan_projects.py` لأي مجلَّد يَملك جذراً بـ `.git`):
  - L1 حذف مباشر: `node_modules`، `target`، `build`، `dist`، `out`، `.next`، `.nuxt`، `.svelte-kit`، `.turbo`، `.parcel-cache`، `__pycache__`، `.pytest_cache`، `.tox`، `.mypy_cache`، `.ruff_cache`، `.dart_tool`، `.nyc_output`، `_build` (مشاريع Elixir فقط)، `Pods`، `vendor` (مشاريع Go فقط).
  - L2 إلى Trash: `.venv`، `venv`، `env` (بيئات Python الافتراضية — قد لا تُستنسخ wheel pins حرفياً، لذلك تُحفَظ نافذة استرداد)؛ `coverage` (تقارير تغطية الاختبارات، مشروطة بوجود `package.json` أو marker بايثون)؛ `.dvc/cache` (كاش DVC المُعنون بالمحتوى، مشروط بوجود marker شقيق `.dvc/config`؛ المجلَّد الأب `.dvc/` يحتوي حالة المستخدم ويُحفَظ).
  - مجلَّدات النظام / مديري الحِزَم (`~/Library`، `~/.cache`، `~/.npm`، `~/.cargo`، `~/.cocoapods`، `~/.gradle`، `~/.m2`، `~/.gem`، `~/.bundle`، `~/.composer`، `~/.pub-cache`، `~/.local`، `~/.rustup`، `~/.pnpm-store`، `~/.Trash`) تُقلَّم عند اكتشاف المشاريع.
- مسح المجلَّدات اليتيمة الكبيرة (في وضع deep فقط): المجلَّدات تحت `~` التي يبلغ حجمها 2 GiB فأكثر ولم تَلتقطها أي قاعدة أخرى تُؤشَّر كـ L3 defer (`source_label="Unclassified large directory"`). قبل الإقرار النهائي يُجري الـ agent تحقيقاً قصيراً للقراءة فقط (بحدٍّ أقصى 6 أوامر لكل مرشَّح) لتحسين `category` و`source_label`؛ تَبقى مرتبة L3 defer مُقفَلة بصرف النظر عن النتيجة.

جدار احتياطي صلب — يَرفض بصرف النظر عن محتوى `confirmed.json`؛ انظر `_BLOCKED_PATTERNS` في `scripts/safe_delete.py`:

- مجلَّدات `.git` و`.ssh` و`.gnupg`.
- `~/Library/Keychains`، `~/Library/Mail`، `~/Library/Messages`، `~/Library/Mobile Documents` (iCloud Drive).
- مكتبة Photos ومكتبة Apple Music.
- ملفات `.env*`، ومفاتيح SSH الخاصة (`id_rsa`، `id_ed25519`، …).
- حالة محرِّرات عائلة VSCode: `{Code, Cursor, Windsurf}/{User, Backups, History}` (تعديلات غير محفوظة، ومكافئات git-stash، وسجل محلي للتعديلات).
- مجلَّدات `Auto-Save` لتطبيقات Adobe الإبداعية — مشاريع Premiere / After Effects / Photoshop غير المحفوظة.

---

## Architecture

`SKILL.md` هو عقد سير عمل الـ agent: اختيار الوضع، التصنيف، المحادثة، وعرض HTML تتمُّ كلها بواسطة الـ agent. يَتولَّى سكربتا Python ما لا يُناسب الـ agent — `scripts/safe_delete.py` هو نقطة الدخول الوحيدة لكتابات نظام الملفات، ويُوفِّر ست عمليات موزَّعة، وidempotency، وعزل أخطاء لكل عنصر؛ و`scripts/collect_sizes.py` يُشغِّل `du -sk` بالتوازي عبر المكتبة القياسية. `references/` هي قاعدة معرفة الـ agent، و`assets/` تَحمل قوالب التقرير. تُجري Stage 6 طبقة reviewer / validator مزدوجة تَلتقط تسريبات الخصوصية قبل أن يَرى المستخدم التقرير. يَقع مُجلَّد العمل لكل تشغيلة في `~/.cache/mac-space-cleanup/run-XXXXXX/`.

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # سير عمل agent الرئيسي (ست مراحل)
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
│   ├── category-rules.md         # 10 فئات بأنماط + risk_level + action
│   └── reviewer-prompts.md       # قالب الـ prompt لِـ sub-agent المراجَعَة
├── assets/
│   ├── report-template.html      # قالب HTML بست مناطق وعلامات مزدوجة
│   ├── report.css
│   └── share-card-template.svg   # بطاقة مشاركة X مقاس 1200×630
├── tests/                        # مجموعة unittest قياسية الاعتماديات
├── CHANGELOG.md
├── CLAUDE.md                     # ثوابت للمساهمين
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations

- **لا مكدِّس للتراجع undo.** مسارات الاسترداد هي: سلة المهملات الأصلية، وملفات tar داخل `archive/` في workdir، ومُجلَّد الوجهة في migrate.
- **لا cron ولا تشغيل في الخلفية.** كلُّ تشغيلة يُطلِقها المستخدم.
- **لا سحابة ولا telemetry.** يَبقى workdir محلياً.
- **لا يَمسُّ المسارات المحمية بـ SIP**، ولا يُزيل تطبيقات `/Applications/*.app`.
- **تعرُّف جذر المشروع يَعتمد على `.git` حصراً.** يُتعرَّف على checkouts القياسية لـ git، ولا يُتعرَّف على مساحات العمل بلا مُجلَّد `.git`. تُزال تكرارات submodules المتداخلة، ولا تَظهر كمشاريع منفصلة.
- **اكتشاف مخرجات المشاريع لا يَحترم `.gitignore`** — يَمسح أسماء مُجلَّدات فرعية اصطلاحية ثابتة (`node_modules`، `target`، …). قد يُظهِر مُجلَّداً يَتجاهله git، وقد يُفوِّت مُجلَّداً يُنشئه المشروع خارج العُرف.
- **تحقُّق على جهاز واحد.** طُوِّر واخْتُبِر على macOS 25.x / 26.x مع سلسلة أدوات مطوِّر. لم يُجرَ بعدُ تحقُّق متقاطع بين Apple Silicon وIntel، ولا عبر إصدارات macOS الأقدم.

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # sanity على نظام ملفات حقيقي
./scripts/dry-e2e.sh                        # من طرف إلى طرف دون LLM
```

تُشغِّل CI الثلاثة عند كل push / PR عبر `.github/workflows/ci.yml` على `macos-latest`.

للاطلاع على الثوابت غير القابلة للتفاوض (الـ agent لا يَكتب على fs مباشرةً، إخفاء الخصوصية إلزامي، إلخ) راجع `CLAUDE.md`، وملاحظات الإصدار في `CHANGELOG.md`.

---

## License

Apache-2.0 (انظر `LICENSE` و`NOTICE`).

## Credits

من تصميم وتنفيذ [@heyiamlin](https://x.com/heyiamlin). إن وفَّر لك هذا الـ skill مساحة، شارِكه بوسم `#macspaceclean`.
