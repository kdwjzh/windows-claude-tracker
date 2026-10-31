"""打包用的腳本（scripts/）：版本資訊、ICO 檔、第三方授權。"""

from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest

from usage_monitor import __version__

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"scripts_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


version_info = load("version_info")


def test_reads_version_from_init() -> None:
    assert version_info.read_version() == __version__


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.8.0", (0, 8, 0, 0)), ("1.2.3-beta.1", (1, 2, 3, 0)), ("2.0", (2, 0, 0, 0))],
)
def test_numeric_version(version: str, expected: tuple[int, int, int, int]) -> None:
    assert version_info.numeric(version) == expected


def test_render_contains_versions_and_names(tmp_path: Path) -> None:
    out = tmp_path / "v.txt"
    assert version_info.main([str(out), "App", "Desc", "App.exe"]) == 0
    text = out.read_text(encoding="utf-8")
    assert f"StringStruct('FileVersion', '{__version__}')" in text
    assert "StringStruct('OriginalFilename', 'App.exe')" in text
    assert "filevers=(" in text
    assert version_info.main([]) == 2


def test_committed_icon_has_every_size() -> None:
    """assets/app.ico 是維護者提供的檔案（不由程式產生）：要含 16–256px 共 9 種尺寸。"""
    data = (SCRIPTS.parent / "assets" / "app.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, kind) == (0, 1)
    sizes: set[int] = set()
    for i in range(count):
        width, height, *_rest, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        assert width == height
        assert offset + length <= len(data)
        sizes.add(width or 256)
    assert sizes >= {16, 20, 24, 32, 40, 48, 64, 128, 256}


release_notes = load("release_notes")

CHANGELOG_SAMPLE = """# 變更紀錄

## [1.2.0] - 2026-11-01

### 新增

- 功能 A

## [1.1.0] - 2026-10-01

- 舊功能

## [1.0.0-beta.1] - 2026-09-01

- beta
"""


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.2.0", "### 新增\n\n- 功能 A"),
        ("1.1.0", "- 舊功能"),
        ("1.0.0-beta.1", "- beta"),
        ("1.0.0", None),  # 不能誤抓到 1.0.0-beta.1
        ("9.9.9", None),
    ],
)
def test_extract_notes(version: str, expected: str | None) -> None:
    assert release_notes.extract_notes(CHANGELOG_SAMPLE, version) == expected


def test_extract_notes_empty_section() -> None:
    assert release_notes.extract_notes("## [1.0.0] - x\n\n## [0.9.0] - y\n- a\n", "1.0.0") is None


@pytest.mark.parametrize(
    ("tag", "version", "pre"),
    [
        ("v1.2.0", "1.2.0", False),
        ("refs/tags/v1.2.0", "1.2.0", False),
        ("v1.2.0-beta.1", "1.2.0-beta.1", True),
        ("1.2.0", "1.2.0", False),
    ],
)
def test_tag_parsing(tag: str, version: str, pre: bool) -> None:
    assert release_notes.tag_version(tag) == version
    assert release_notes.is_prerelease(tag) is pre


def test_verify_tag_against_current_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert release_notes.main(["verify-tag", f"v{__version__}"]) == 0
    assert release_notes.main(["verify-tag", "v0.0.0-mismatch"]) == 1
    assert "不一致" in capsys.readouterr().err


def test_current_version_has_changelog_notes(tmp_path: Path) -> None:
    """發新版前一定要寫 CHANGELOG：目前的 __version__ 必須有對應段落。"""
    out = tmp_path / "notes.md"
    assert release_notes.main(["notes", f"v{__version__}", str(out)]) == 0
    assert out.read_text(encoding="utf-8").strip()


def test_notes_missing_version_and_usage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert release_notes.main(["notes", "v9.9.9", str(tmp_path / "x.md")]) == 1
    assert release_notes.main(["is-prerelease", "v1.0.0-rc.1"]) == 0
    assert capsys.readouterr().out.strip().endswith("true")
    assert release_notes.main(["bogus"]) == 2


def test_committed_icon_exists() -> None:
    icon = SCRIPTS.parent / "assets" / "app.ico"
    assert icon.read_bytes()[:4] == b"\x00\x00\x01\x00"


third_party = load("third_party_licenses")


def test_third_party_licenses_cover_bundled_packages(tmp_path: Path) -> None:
    out = tmp_path / "THIRD_PARTY_LICENSES.txt"
    assert third_party.main([str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    for name in ("PySide6", "shiboken6", "requests", "urllib3", "certifi", "cryptography"):
        assert f"- {name} " in text
    assert "- truststore " in text
    assert "pyside6_addons" not in text.lower()  # build.ps1 排除的 Qt 模組不列
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in text
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Qt-Commercial" not in text
    assert third_party.main([]) == 2


@pytest.mark.parametrize(
    ("req", "expected"),
    [
        ("idna<4,>=2.5", "idna"),
        ("cffi>=2.0; platform_python_implementation != 'PyPy'", "cffi"),
        ("pytest; extra == 'test'", None),
    ],
)
def test_third_party_requirement_parsing(req: str, expected: str | None) -> None:
    assert third_party.requirement_name(req) == expected
