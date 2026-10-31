from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from usage_monitor.services.settings.migrations import (
    FutureVersionError,
    migrate,
    version_of,
)
from usage_monitor.services.settings.schema import (
    CURRENT_VERSION,
    Settings,
    WidgetSettings,
    settings_from_dict,
)
from usage_monitor.services.settings.store import SettingsStore, write_atomic

# ---------------------------------------------------------------- schema


def test_defaults_match_spec() -> None:
    s = Settings()
    assert s.to_dict() == {
        "schema_version": 2,
        "interval_minutes": 5,
        "providers": ["claude"],
        "allow_cli_refresh": False,
        "language": "system",
        "widget": {
            "visible": True,
            "locked": False,
            "opacity": 0.9,
            "screen": None,
            "pos": None,
            "hide_on_fullscreen": True,
            "hotkey": "Ctrl+Alt+U",
            "theme": "system",
        },
        "update_check": {
            "enabled": True,  # CLAUDE.md §7 第 9 題：預設開啟
            "skipped_version": None,
            "last_checked_at": None,
            "notified_version": None,
        },
    }


def test_round_trip() -> None:
    s = Settings(
        interval_minutes=10,
        providers=("claude", "codex"),
        allow_cli_refresh=True,
        widget=WidgetSettings(
            visible=False, locked=True, opacity=0.6, screen=r"\\.\DISPLAY2", pos=(10, -20)
        ),
    )
    parsed, warnings = settings_from_dict(s.to_dict())
    assert parsed == s
    assert warnings == []


def test_missing_fields_use_defaults_without_warnings() -> None:
    parsed, warnings = settings_from_dict({"schema_version": 1})
    assert parsed == Settings()
    assert warnings == []


def test_unknown_fields_ignored() -> None:
    parsed, warnings = settings_from_dict({"future_flag": True, "widget": {"x": 1}})
    assert parsed == Settings()
    assert warnings == []


@pytest.mark.parametrize(
    ("raw", "check"),
    [
        ({"interval_minutes": "5"}, lambda s: s.interval_minutes == 5),
        ({"interval_minutes": 2.5}, lambda s: s.interval_minutes == 5),
        ({"interval_minutes": True}, lambda s: s.interval_minutes == 5),
        ({"providers": "claude"}, lambda s: s.providers == ("claude",)),
        ({"providers": ["claude", 3]}, lambda s: s.providers == ("claude",)),
        ({"allow_cli_refresh": "yes"}, lambda s: s.allow_cli_refresh is False),
        ({"widget": []}, lambda s: s.widget == WidgetSettings()),
        ({"widget": {"visible": 1}}, lambda s: s.widget.visible is True),
        ({"widget": {"opacity": "high"}}, lambda s: s.widget.opacity == 0.9),
        ({"widget": {"pos": [1]}}, lambda s: s.widget.pos is None),
        ({"widget": {"pos": ["a", "b"]}}, lambda s: s.widget.pos is None),
        ({"widget": {"screen": ""}}, lambda s: s.widget.screen is None),
        ({"widget": {"hotkey": ""}}, lambda s: s.widget.hotkey == "Ctrl+Alt+U"),
        ({"widget": {"theme": "pink"}}, lambda s: s.widget.theme == "system"),
        ({"language": "fr"}, lambda s: s.language == "system"),
    ],
)
def test_bad_field_falls_back_with_warning(raw: dict[str, object], check: object) -> None:
    parsed, warnings = settings_from_dict(raw)
    assert check(parsed)  # type: ignore[operator]
    assert len(warnings) == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"interval_minutes": 0}, 1),
        ({"interval_minutes": -3}, 1),
        ({"interval_minutes": 99999}, 1440),
    ],
)
def test_interval_is_clamped(raw: dict[str, object], expected: int) -> None:
    parsed, warnings = settings_from_dict(raw)
    assert parsed.interval_minutes == expected
    assert "超出範圍" in warnings[0]


def test_opacity_is_clamped() -> None:
    parsed, _ = settings_from_dict({"widget": {"opacity": 5}})
    assert parsed.widget.opacity == 1.0
    parsed, _ = settings_from_dict({"widget": {"opacity": 0}})
    assert parsed.widget.opacity == 0.3


def test_providers_deduplicated_and_empty_allowed() -> None:
    parsed, _ = settings_from_dict({"providers": ["codex", " claude ", "codex"]})
    assert parsed.providers == ("codex", "claude")
    parsed, warnings = settings_from_dict({"providers": []})
    assert parsed.providers == ()
    assert warnings == []


def test_pos_accepts_numbers_and_screen_text() -> None:
    parsed, _ = settings_from_dict({"widget": {"pos": [1520.7, 380], "screen": " DISPLAY1 "}})
    assert parsed.widget.pos == (1520, 380)
    assert parsed.widget.screen == "DISPLAY1"


# ---------------------------------------------------------------- migrations


def test_version_of() -> None:
    assert version_of({}) == 0
    assert version_of({"schema_version": 3}) == 3
    assert version_of({"schema_version": "1"}) == 0
    assert version_of({"schema_version": True}) == 0
    assert version_of({"schema_version": -1}) == 0


def test_v0_to_v1_keeps_fields() -> None:
    data = {"interval_minutes": 7, "providers": ["claude"]}
    assert migrate(data, target=1) == {**data, "schema_version": 1}
    assert "schema_version" not in data  # 不修改輸入


def test_v1_to_v2_adds_update_check() -> None:
    migrated = migrate({"schema_version": 1, "interval_minutes": 7})
    assert migrated["schema_version"] == 2
    assert migrated["update_check"] == {
        "enabled": True,
        "skipped_version": None,
        "last_checked_at": None,
        "notified_version": None,
    }
    assert migrated["interval_minutes"] == 7


def test_v1_to_v2_keeps_existing_update_check() -> None:
    custom = {"enabled": False}
    assert migrate({"schema_version": 1, "update_check": custom})["update_check"] == custom


def test_update_check_fields_parse_and_fall_back() -> None:
    parsed, warnings = settings_from_dict(
        {"update_check": {"enabled": False, "skipped_version": "1.2.0", "notified_version": 5}}
    )
    assert parsed.update_check.enabled is False
    assert parsed.update_check.skipped_version == "1.2.0"
    assert parsed.update_check.notified_version is None
    assert len(warnings) == 1
    parsed, warnings = settings_from_dict({"update_check": "on"})
    assert parsed.update_check.enabled is True and len(warnings) == 1


def test_migration_chain_runs_in_order() -> None:
    steps = {
        0: lambda d: {**d, "a": 1},
        1: lambda d: {**d, "b": d["a"] + 1},
    }
    assert migrate({}, target=2, migrations=steps) == {"a": 1, "b": 2, "schema_version": 2}


def test_future_version_raises() -> None:
    with pytest.raises(FutureVersionError):
        migrate({"schema_version": CURRENT_VERSION + 1})


# ---------------------------------------------------------------- store


def read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_missing_file_writes_defaults(tmp_path: Path) -> None:
    path = tmp_path / "app" / "settings.json"
    store = SettingsStore(path)
    assert store.load() == Settings()
    assert read(path) == Settings().to_dict()


def test_broken_json_uses_defaults_and_keeps_backup(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ broken", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert SettingsStore(path).load() == Settings()
    assert "格式錯誤" in caplog.text
    assert path.read_text(encoding="utf-8") == "{ broken"  # 不直接覆蓋
    assert (tmp_path / "settings.json.broken").read_text(encoding="utf-8") == "{ broken"


def test_non_object_json_is_broken(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert SettingsStore(path).load() == Settings()
    assert (tmp_path / "settings.json.broken").exists()


def test_bad_fields_logged_and_kept_on_disk(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"schema_version": CURRENT_VERSION, "interval_minutes": "x"}), encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        assert SettingsStore(path).load().interval_minutes == 5
    assert "interval_minutes" in caplog.text
    assert read(path)["interval_minutes"] == "x"  # 版本相同就不改寫使用者的檔案


def test_old_version_is_migrated_and_written_back(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"interval_minutes": 7, "providers": ["claude"]}), encoding="utf-8")
    settings = SettingsStore(path).load()
    assert settings.interval_minutes == 7
    assert read(path)["schema_version"] == CURRENT_VERSION
    assert read(path)["update_check"] == Settings().to_dict()["update_check"]
    assert read(path)["widget"] == Settings().to_dict()["widget"]


def test_future_version_is_read_but_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    original = json.dumps({"schema_version": 99, "interval_minutes": 9, "new_thing": 1})
    path.write_text(original, encoding="utf-8")
    assert SettingsStore(path).load().interval_minutes == 9
    assert path.read_text(encoding="utf-8") == original


def test_update_saves_and_notifies(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.load()
    seen: list[Settings] = []
    unsubscribe = store.subscribe(seen.append)

    new = store.update(lambda s: replace(s, interval_minutes=15))
    assert new.interval_minutes == 15
    assert store.current is new
    assert read(path)["interval_minutes"] == 15
    assert seen == [new]

    unsubscribe()
    store.save(replace(new, allow_cli_refresh=True))
    assert len(seen) == 1
    assert read(path)["allow_cli_refresh"] is True


def test_save_failure_keeps_memory_unchanged(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    store = SettingsStore(blocker / "settings.json")  # 父路徑是檔案，寫不進去
    with pytest.raises(OSError):
        store.update(lambda s: replace(s, interval_minutes=30))
    assert store.current == Settings()


def test_unwritable_location_still_loads_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = SettingsStore(tmp_path / "settings.json")

    def fail(_: Settings) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(store, "_write", fail)
    with caplog.at_level(logging.WARNING):
        assert store.load() == Settings()
    assert "寫不進去" in caplog.text


def test_unreadable_file_uses_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.mkdir()  # 資料夾不能當檔案讀
    assert SettingsStore(path).load() == Settings()


def test_write_atomic_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    write_atomic(path, "one")
    write_atomic(path, "two")
    assert path.read_text(encoding="utf-8") == "two"
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_write_atomic_cleans_up_on_failure(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    target.mkdir()  # 不能用檔案取代資料夾
    with pytest.raises(OSError):
        write_atomic(target, "x")
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]
