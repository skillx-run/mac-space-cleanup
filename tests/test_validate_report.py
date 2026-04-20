"""Tests for scripts/validate_report.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import validate_report  # noqa: E402
from _helpers import run_script  # noqa: E402


# The rendered template ships the dict container empty; English runs
# leave it like this (baseline text inside data-i18n spans renders
# directly), non-English runs replace the body with a populated object.
_MIN_I18N_DICT = (
    '<script type="application/json" id="i18n-dict">{}</script>'
)


def _well_formed_html(
    extra: str = "",
    i18n_dict: str | None = None,
    data_i18n_attrs: str = "",
) -> str:
    """A minimal report.html that fills every region and carries a
    validator-clean empty i18n dict.

    Override ``i18n_dict`` to test dict violations (pass a full `<script
    id="i18n-dict">…</script>` block, or an empty string to omit the
    container entirely). Pass ``data_i18n_attrs`` to include a snippet
    of extra markup that carries data-i18n attributes — useful for
    tests that exercise the dict-keys-⊆-template-keys rule.
    """
    parts = [
        f"<!-- region:{r}:start --><p>filled {r}</p><!-- region:{r}:end -->"
        for r in validate_report.REGIONS
    ]
    dict_block = _MIN_I18N_DICT if i18n_dict is None else i18n_dict
    return (
        f"<html><body>{dict_block}{data_i18n_attrs}{''.join(parts)}{extra}</body></html>"
    )


def _run(report: Path) -> tuple[int, dict, str]:
    return run_script(validate_report, ["--report", str(report)], None)


class TestValidateReport(unittest.TestCase):
    def setUp(self):
        # All but one test want runtime forbidden list empty (so we don't
        # depend on whoever is running the suite). The one test that needs
        # runtime values overrides this in its own body.
        patcher = mock.patch.object(validate_report, "_runtime_forbidden",
                                    return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- happy paths ----------

    def test_well_formed_passes(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html())
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])
        self.assertEqual(out["violations"], [])

    def test_all_good_nextstep_does_not_false_positive(self):
        """When pending_in_trash_bytes==0 the agent replaces the nextstep
        placeholder with `<p class="all-good">All freed bytes are
        immediately reclaimed — no follow-up needed.</p>`. That literal
        must not trigger placeholder_left or empty_region."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html().replace(
                "<!-- region:nextstep:start --><p>filled nextstep</p><!-- region:nextstep:end -->",
                (
                    "<!-- region:nextstep:start -->"
                    '<p class="all-good">All freed bytes are immediately reclaimed'
                    " \u2014 no follow-up needed.</p>"
                    "<!-- region:nextstep:end -->"
                ),
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    # ---------- structural violations ----------

    def test_missing_region_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html().replace(
                "<!-- region:share:start --><p>filled share</p><!-- region:share:end -->",
                "",
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("missing_region", kinds)
        regions = [v.get("region") for v in out["violations"]
                   if v["kind"] == "missing_region"]
        self.assertIn("share", regions)

    def test_empty_region_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html().replace(
                "<!-- region:hero:start --><p>filled hero</p><!-- region:hero:end -->",
                "<!-- region:hero:start -->   <!-- region:hero:end -->",
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        empties = [v for v in out["violations"] if v["kind"] == "empty_region"]
        self.assertEqual(len(empties), 1)
        self.assertEqual(empties[0]["region"], "hero")

    # ---------- placeholder ----------

    def test_placeholder_marker_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra='<div data-placeholder="hero">Agent fills this block</div>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("placeholder_left", kinds)

    def test_placeholder_impact_flagged(self):
        """A surviving impact placeholder is caught — impact is a new
        region introduced in this redesign."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra='<div data-placeholder="impact">TODO</div>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "placeholder_left"]
        self.assertTrue(any('data-placeholder="impact"' in v["detail"]
                            for v in leaks))

    # ---------- redaction ----------

    def test_leaked_path_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(extra="<p>/Users/alice/Projects/secret</p>")
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("/Users/" in v["detail"] for v in leaks))

    def test_leaked_credential_hint_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(extra="<code>id_rsa</code>")
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("id_rsa" in v["detail"] for v in leaks))

    def test_runtime_username_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(extra="<p>user is alice today</p>")
            report.write_text(html)
            with mock.patch.object(validate_report, "_runtime_forbidden",
                                   return_value=["alice", "/Users/alice"]):
                code, out, _ = _run(report)
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("alice" in v["detail"] for v in leaks))

    # ---------- input handling ----------

    def test_missing_file_returns_violation(self):
        code, out, _ = _run(Path("/tmp/definitely-not-here-xyz123.html"))
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertEqual(out["violations"][0]["kind"], "missing_file")

    # ---------- dry-run marking: structural checks ----------

    def test_real_run_does_not_require_dry_run_markers(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(extra="<p>12.5 GB freed</p>"))
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    def test_dry_run_without_banner_and_prefix_fails(self):
        """A dry-run without either structural signal raises both
        dry_run_unmarked variants."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(extra="<p>12.5 GB</p>"))
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertEqual(kinds.count("dry_run_unmarked"), 2)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("dry-banner", details)
        self.assertIn("dryrun-prefix", details)

    def test_dry_run_requires_banner_data_dryrun_attribute(self):
        """A .dry-banner that is missing data-dryrun=\"true\" must fail —
        the attribute is what makes the marker language-agnostic."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner">DRY-RUN</div>'
                    '<p><span class="dryrun-prefix">would be </span>12.5 GB</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("dry_run_unmarked", kinds)
        details = " ".join(
            v["detail"] for v in out["violations"]
            if v["kind"] == "dry_run_unmarked"
        )
        self.assertIn("dry-banner", details)

    def test_dry_run_requires_number_prefix_span(self):
        """Banner is correct but no .dryrun-prefix anywhere — fails."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner" data-dryrun="true">DRY-RUN</div>'
                    '<p>12.5 GB</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 1)
        details = " ".join(v["detail"] for v in out["violations"]
                           if v["kind"] == "dry_run_unmarked")
        self.assertIn("dryrun-prefix", details)

    def test_dry_run_with_banner_and_prefix_passes(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner" data-dryrun="true">DRY-RUN</div>'
                    '<p><span class="dryrun-prefix">would be </span>12.5 GB</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    def test_dry_run_banner_accepts_any_language_prose(self):
        """Banner prose in Japanese, prefix span in Arabic — structural
        check is language-agnostic, both markers present → passes."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner" data-dryrun="true">'
                    'ドライラン — ファイルに変更はありません'
                    '</div>'
                    '<p><span class="dryrun-prefix">تقديريًا </span>12.5 GB</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    def test_dry_run_banner_attribute_accepts_alternate_order(self):
        """data-dryrun may sit before the class attribute on the element —
        the regex must not require a specific attribute order."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div data-dryrun="true" class="dry-banner">DRY-RUN</div>'
                    '<p><span class="dryrun-prefix">would be </span>12.5 GB</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    # ---------- i18n: dict structure ----------

    def test_i18n_dict_empty_object_passes(self):
        """Empty {} is the default English-run shape; spans render from
        their data-i18n baseline text and need no dict."""
        # _well_formed_html already uses {} by default.
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html())
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    def test_i18n_dict_populated_with_canonical_keys_passes(self):
        """A populated dict whose keys all appear in strings.json AND as
        data-i18n attrs in the rendered HTML passes."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict=(
                    '<script type="application/json" id="i18n-dict">'
                    '{"brand.by":"作者","hero.unit":"已释放"}'
                    '</script>'
                ),
                data_i18n_attrs=(
                    '<span data-i18n="brand.by">by</span>'
                    '<span data-i18n="hero.unit">freed</span>'
                ),
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    def test_i18n_dict_missing_container_fails(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(i18n_dict=""))
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("missing", details)

    def test_i18n_dict_invalid_json_fails(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict='<script id="i18n-dict">{not valid json}</script>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("JSON parse error", details)

    def test_i18n_dict_non_string_value_fails(self):
        """Every dict value must be a string (the hydration script calls
        textContent assignment which expects a string)."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict=(
                    '<script id="i18n-dict">'
                    '{"brand.by": 42}'
                    '</script>'
                ),
                data_i18n_attrs='<span data-i18n="brand.by">by</span>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)

    def test_i18n_dict_key_not_in_template_fails(self):
        """A dict carrying a key that the template does not reference
        (via data-i18n) is stale — flag it so agents catch typos and
        removed keys."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict=(
                    '<script id="i18n-dict">'
                    '{"brand.by":"作者","ghost.key":"幽灵"}'
                    '</script>'
                ),
                data_i18n_attrs='<span data-i18n="brand.by">by</span>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("ghost.key", details)

    def test_template_data_i18n_key_not_in_strings_json_fails(self):
        """A template that references a data-i18n key absent from the
        canonical strings.json means the project has an orphan label —
        flag it so the canonical source stays authoritative."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                data_i18n_attrs='<span data-i18n="nonexistent.canonical.key">x</span>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("template_key_missing_from_strings", kinds)
        details = " ".join(
            v["detail"] for v in out["violations"]
            if v["kind"] == "template_key_missing_from_strings"
        )
        self.assertIn("nonexistent.canonical.key", details)


def _well_formed_html_with_classes(classes: str) -> str:
    """Extend `_well_formed_html` with a region whose inner element
    carries a given class attribute. The target region (`impact`) is
    chosen because the helper always emits every region as a tiny
    `<p>filled X</p>` block; replacing impact's block with one that
    carries our class attribute keeps every other region intact."""
    base = _well_formed_html()
    return base.replace(
        "<!-- region:impact:start --><p>filled impact</p><!-- region:impact:end -->",
        f'<!-- region:impact:start --><p class="{classes}">filled impact</p><!-- region:impact:end -->',
    )


class TestClassAllowlist(unittest.TestCase):
    """Cover the class allowlist lint from both sides: the HTML-side
    recognition of known vs unknown classes, and the CSS-side parser's
    ability to weather comments, quoted literals, grouped / multi-line /
    media-nested selectors."""

    def setUp(self):
        # Mirror the root test class: empty runtime forbidden list so
        # tests don't pick up the current user's home / username.
        patcher = mock.patch.object(
            validate_report, "_runtime_forbidden", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run_with_css(self, html: str, css: str):
        with tempfile.TemporaryDirectory() as td:
            css_path = Path(td) / "report.css"
            css_path.write_text(css)
            report = Path(td) / "report.html"
            report.write_text(html)
            with mock.patch.object(
                    validate_report, "_REPORT_CSS_PATH", css_path):
                return _run(report)

    # ---------- HTML recognition ----------

    def test_known_classes_pass(self):
        """A class attribute listing only CSS-defined tokens passes the
        lint. We reuse live `report.css` so the test also doubles as a
        smoke check that it has not gone stale."""
        html = _well_formed_html_with_classes("hero-body stack-bar seg-1")
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertNotIn("undefined_class", kinds)

    def test_unknown_class_flags(self):
        """An improvised class (no CSS rule) produces one
        `undefined_class` violation with the class name quoted in
        detail."""
        html = _well_formed_html_with_classes("legend-item")
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        details = [v["detail"] for v in out["violations"]
                   if v["kind"] == "undefined_class"]
        self.assertTrue(
            any("'legend-item'" in d for d in details),
            msg=f"expected 'legend-item' mention in {details}",
        )

    def test_multiple_unknown_classes_each_reported(self):
        """Three improvised classes in one attribute flag three times;
        the alphabetical sort keeps output stable across platforms."""
        html = _well_formed_html_with_classes("zeta alpha gamma")
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        undef = [v["detail"] for v in out["violations"]
                 if v["kind"] == "undefined_class"]
        self.assertEqual(len(undef), 3)
        # Alphabetical order -> alpha, gamma, zeta.
        self.assertIn("'alpha'", undef[0])
        self.assertIn("'gamma'", undef[1])
        self.assertIn("'zeta'", undef[2])

    def test_mixed_known_unknown_class_attr(self):
        """When one class in the attr is known and another is not,
        only the unknown one is flagged."""
        html = _well_formed_html_with_classes("seg-1 legend-item")
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        undef = [v["detail"] for v in out["violations"]
                 if v["kind"] == "undefined_class"]
        self.assertEqual(len(undef), 1)
        self.assertIn("'legend-item'", undef[0])

    def test_whitespace_normalized_in_class_attr(self):
        """Leading, trailing, and extra internal whitespace between
        class tokens does not produce phantom empty-string classes."""
        html = _well_formed_html_with_classes("  seg-1   seg-2  ")
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertNotIn("undefined_class", kinds)

    def test_css_load_failure_reports_violation(self):
        """If `report.css` can't be read, the lint emits a single
        `css_load_failed` violation and fails overall rather than
        crashing or silently passing."""
        html = _well_formed_html_with_classes("seg-1")
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(html)
            missing_css = Path(td) / "does-not-exist.css"
            with mock.patch.object(
                    validate_report, "_REPORT_CSS_PATH", missing_css):
                code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("css_load_failed", kinds)

    # ---------- CSS parsing boundaries ----------

    def test_css_block_comment_ignored(self):
        """A class name appearing only inside a /* … */ block comment
        is not considered defined — the real class still is."""
        css = "/* .legacy-class does nothing */ .real-class { color: red; }"
        html = _well_formed_html_with_classes("legacy-class")
        code, out, _ = self._run_with_css(html, css)
        self.assertEqual(code, 1)
        undef = [v["detail"] for v in out["violations"]
                 if v["kind"] == "undefined_class"]
        self.assertTrue(any("'legacy-class'" in d for d in undef))

    def test_css_quoted_literal_ignored(self):
        """A `.foo` fragment inside a quoted attribute selector (e.g.
        `[style*=".foo"]`) does not leak into the allowed set."""
        css = '.seg-a[style*=".foo"] { background: red; }'
        html = _well_formed_html_with_classes("foo")
        code, out, _ = self._run_with_css(html, css)
        self.assertEqual(code, 1)
        undef = [v["detail"] for v in out["violations"]
                 if v["kind"] == "undefined_class"]
        self.assertTrue(any("'foo'" in d for d in undef))

    def test_css_grouped_selector_all_classes_counted(self):
        """Every class in a comma-separated selector group is
        independently added to the allowed set."""
        css = ".a, .b, .c { color: red; }"
        html = _well_formed_html_with_classes("a b c")
        code, out, _ = self._run_with_css(html, css)
        self.assertEqual(code, 0, msg=out)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertNotIn("undefined_class", kinds)

    def test_css_multiline_selector_counted(self):
        """Selector lists that span multiple lines with whitespace
        still have each class parsed — the regex is line-agnostic."""
        css = ".foo,\n  .bar {\n  color: red;\n}"
        html = _well_formed_html_with_classes("foo bar")
        code, out, _ = self._run_with_css(html, css)
        self.assertEqual(code, 0, msg=out)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertNotIn("undefined_class", kinds)

    def test_css_media_query_nested_class_counted(self):
        """Classes inside an @media block are discovered identically
        to classes at the top level — the parser is unaware of
        nesting, which is what we want for a pure allowlist check."""
        css = "@media (max-width: 600px) { .mobile-only { display: block; } }"
        html = _well_formed_html_with_classes("mobile-only")
        code, out, _ = self._run_with_css(html, css)
        self.assertEqual(code, 0, msg=out)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertNotIn("undefined_class", kinds)

    def test_lint_and_i18n_both_reported(self):
        """When an HTML triggers both `undefined_class` and an i18n
        dict violation, the validator surfaces both rather than
        short-circuiting on the first."""
        # Dict has a key that the template never references — stray.
        stray_dict = (
            '<script type="application/json" id="i18n-dict">'
            '{"doc.title":"x"}'
            '</script>'
        )
        base = _well_formed_html(i18n_dict=stray_dict)
        # Inject an unknown class into the impact region.
        html = base.replace(
            "<!-- region:impact:start --><p>filled impact</p><!-- region:impact:end -->",
            '<!-- region:impact:start --><p class="nonexistent-class">filled impact</p><!-- region:impact:end -->',
        )
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = {v["kind"] for v in out["violations"]}
        self.assertIn("undefined_class", kinds)
        self.assertIn("i18n_dict_malformed", kinds)


if __name__ == "__main__":
    unittest.main()
