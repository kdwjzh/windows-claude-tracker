"""翻譯表：兩種語言的 key 與 {參數} 必須完全一致，缺字時不能讓畫面崩潰。"""

from __future__ import annotations

from string import Formatter

import pytest

from usage_monitor.core import i18n
from usage_monitor.core.i18n import CATALOG, LANGUAGE_CHOICES, Lang, resolve_language, t


def _params(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name}


def test_all_languages_have_the_same_keys() -> None:
    zh = set(CATALOG[Lang.ZH_TW])
    for lang, table in CATALOG.items():
        assert set(table) == zh, f"{lang.value} 缺：{zh - set(table)}，多：{set(table) - zh}"


@pytest.mark.parametrize("key", sorted(CATALOG[Lang.ZH_TW]))
def test_placeholders_match_across_languages(key: str) -> None:
    expected = _params(CATALOG[Lang.ZH_TW][key])
    for lang, table in CATALOG.items():
        assert _params(table[key]) == expected, f"{lang.value} 的 {key} 參數不一致"


@pytest.mark.parametrize("lang", list(Lang))
def test_no_empty_translations(lang: Lang) -> None:
    assert all(text.strip() for text in CATALOG[lang].values())


def test_english_table_has_no_chinese() -> None:
    for key, text in CATALOG[Lang.EN].items():
        assert not any("一" <= ch <= "鿿" for ch in text), key


def test_t_formats_and_falls_back() -> None:
    assert t(Lang.EN, "interval_choice", n=5) == "Every 5 min"
    assert t(Lang.ZH_TW, "interval_choice", n=5) == "每 5 分鐘"
    assert t(Lang.EN, "no_such_key") == "no_such_key"
    assert i18n.has("loading") and not i18n.has("no_such_key")


@pytest.mark.parametrize(
    ("choice", "ui", "expected"),
    [
        ("zh-TW", ["en-US"], Lang.ZH_TW),
        ("en", ["zh-Hant-TW"], Lang.EN),
        ("system", ["zh-Hant-TW", "en-US"], Lang.ZH_TW),
        ("system", ["zh-CN"], Lang.ZH_TW),  # 任何中文都用繁體中文
        ("system", ["ZH-tw"], Lang.ZH_TW),
        ("system", ["en-US", "zh-TW"], Lang.EN),  # 只看第一個
        ("system", ["ja-JP"], Lang.EN),
        ("system", [], Lang.EN),
        ("klingon", ["zh-TW"], Lang.ZH_TW),  # 不認得的設定值當成跟隨系統
    ],
)
def test_resolve_language(choice: str, ui: list[str], expected: Lang) -> None:
    assert resolve_language(choice, ui) is expected


def test_language_choices_match_enum() -> None:
    assert LANGUAGE_CHOICES == ("system", "zh-TW", "en")
    assert {Lang(v) for v in LANGUAGE_CHOICES[1:]} == set(Lang)
