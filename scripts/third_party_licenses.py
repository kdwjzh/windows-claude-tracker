"""產生 THIRD_PARTY_LICENSES.txt：打包進 exe 的第三方元件與它們的授權（CLAUDE.md §3.9）。

    python scripts/third_party_licenses.py dist/THIRD_PARTY_LICENSES.txt

內容取自目前環境已安裝套件的 metadata 與授權檔，所以版本號一定跟打包時用的一致。
PySide6／Qt 的 wheel 沒附 LGPL 全文，改用 assets/licenses/ 裡從 gnu.org 下載的版本。
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LICENSES = ROOT / "assets" / "licenses"

RUNTIME = ("PySide6", "requests", "truststore", "cryptography")
"""pyproject.toml 的執行期依賴；它們的依賴會自動一起列出。"""
NOT_BUNDLED = frozenset({"pyside6-addons", "pyside6-webengine", "pyside6-pdf"})
"""build.ps1 排除了這些 Qt 模組（只保留 QtCore／QtGui／QtWidgets），不在 exe 裡。"""
QT_DISTS = frozenset({"pyside6", "pyside6-essentials", "shiboken6"})
_LICENSE_FILE = re.compile(r"(licen[cs]e|copying|notice)", re.IGNORECASE)
_RULE = "=" * 78

QT_NOTICE = """\
PySide6 / Qt for Python 與 Qt 6（QtCore、QtGui、QtWidgets）
Copyright (C) The Qt Company Ltd. and other contributors.

本程式以 GNU Lesser General Public License v3（LGPL-3.0）使用 PySide6 與 Qt，
未修改其原始碼。Qt 以動態連結函式庫的形式包在 exe 內，執行時解壓到暫存資料夾；
使用者可以自行替換成相容版本的 Qt／PySide6 函式庫。

原始碼取得：
  PySide6：https://code.qt.io/cgit/pyside/pyside-setup.git/
  Qt 6：   https://download.qt.io/official_releases/qt/
Qt 本身內含的第三方元件授權：https://doc.qt.io/qt-6/licenses-used-in-qt.html

LGPL-3.0 與它引用的 GPL-3.0 全文附在本檔最後。
"""


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(req: str) -> str | None:
    """'idna<4,>=2.5' → 'idna'；只給 extra 用的依賴回傳 None。"""
    if "extra ==" in req:
        return None
    return re.split(r"[\s;<>=!~\[(]", req, maxsplit=1)[0]


def collect(roots: Iterable[str] = RUNTIME) -> list[Distribution]:
    """執行期依賴＋它們的依賴（不含 NOT_BUNDLED），依名稱排序。"""
    seen: dict[str, Distribution] = {}
    todo = list(roots)
    while todo:
        name = todo.pop()
        key = _normalize(name)
        if key in seen or key in NOT_BUNDLED:
            continue
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue  # 這個平台不需要的條件式依賴
        seen[key] = dist
        for req in dist.requires or []:
            dep = requirement_name(req)
            if dep is not None:
                todo.append(dep)
    return sorted(seen.values(), key=lambda d: _normalize(d.metadata["Name"]))


def license_name(dist: Distribution) -> str:
    meta = dist.metadata
    expr = meta.get("License-Expression")
    if expr:
        return expr
    text = (meta.get("License") or "").strip()
    if text and "\n" not in text and len(text) < 80:
        return text
    classifiers = [
        c.rsplit(" :: ", 1)[-1]
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    return ", ".join(classifiers) or "見下方授權全文"


def license_texts(dist: Distribution) -> list[tuple[str, str]]:
    """套件 dist-info 裡附的授權檔（Qt 的商業授權檔不列，我們用的是 LGPL）。"""
    result: list[tuple[str, str]] = []
    for file in dist.files or []:
        name = file.name
        if not _LICENSE_FILE.search(name) or "Commercial" in name:
            continue
        text = file.read_text(encoding="utf-8")
        if text and text.strip():
            result.append((name, text.strip()))
    return result


def _section(title: str, body: str) -> str:
    return f"{_RULE}\n{title}\n{_RULE}\n\n{body.rstrip()}\n\n"


def render(
    dists: Iterable[Distribution], python_license: Path | None, licenses_dir: Path = LICENSES
) -> str:
    dists = list(dists)
    out = [
        "Claude Usage Tracker — 第三方元件授權（Third-party licenses）\n\n"
        "本程式的 exe 內含下列第三方元件，各依其授權條款使用與散佈。\n"
        "This executable bundles the following third-party components.\n\n"
    ]
    py_version = ".".join(map(str, sys.version_info[:3]))
    out.append(f"- Python {py_version}（PSF-2.0）\n")
    for dist in dists:
        out.append(f"- {dist.metadata['Name']} {dist.version}（{license_name(dist)}）\n")
    out.append("\n")

    if python_license is not None and python_license.is_file():
        out.append(_section(f"Python {py_version}", python_license.read_text(encoding="utf-8")))
    qt = [d for d in dists if _normalize(d.metadata["Name"]) in QT_DISTS]
    if qt:
        out.append(_section("PySide6 / Qt", QT_NOTICE))
    for dist in dists:
        if _normalize(dist.metadata["Name"]) in QT_DISTS:
            continue
        for file_name, text in license_texts(dist):
            out.append(_section(f"{dist.metadata['Name']} {dist.version} — {file_name}", text))
    if qt:
        for name in ("LGPL-3.0.txt", "GPL-3.0.txt"):
            out.append(
                _section(
                    name.removesuffix(".txt"), (licenses_dir / name).read_text(encoding="utf-8")
                )
            )
    return "".join(out).rstrip() + "\n"


def python_license_file() -> Path | None:
    for name in ("LICENSE.txt", "LICENSE"):
        path = Path(sys.base_prefix) / name
        if path.is_file():
            return path
    return None


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("用法：python scripts/third_party_licenses.py <輸出檔>", file=sys.stderr)
        return 2
    out = Path(args[0])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(collect(), python_license_file()), encoding="utf-8", newline="\n")
    print(f"已產生 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
