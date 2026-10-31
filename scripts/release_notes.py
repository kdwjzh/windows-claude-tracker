"""發佈用（.github/workflows/release.yml）：核對標籤與 __version__、取出 CHANGELOG 的版本說明。

python scripts/release_notes.py verify-tag v1.2.0        # 不一致時結束代碼 1
python scripts/release_notes.py notes 1.2.0 notes.md     # 找不到該版本段落時結束代碼 1
python scripts/release_notes.py is-prerelease v1.2.0-beta.1   # 印出 true／false
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from version_info import read_version

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"


def tag_version(tag: str) -> str:
    """ "v1.2.0" → "1.2.0"；也接受 "refs/tags/v1.2.0"。"""
    return tag.rsplit("/", 1)[-1].removeprefix("v")


def is_prerelease(tag: str) -> bool:
    return "-" in tag_version(tag)


def extract_notes(changelog: str, version: str) -> str | None:
    """`## [1.2.0] - 日期` 到下一個 `## [` 之間的內容（不含標題）。"""
    lines = changelog.splitlines()
    heading = re.compile(rf"^## \[{re.escape(version)}\](\s|$)")
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))
    body = "\n".join(lines[start + 1 : end]).strip()
    return body or None


def main(argv: list[str]) -> int:
    match argv:
        case ["verify-tag", tag]:
            expected = read_version()
            if tag_version(tag) != expected:
                print(f"標籤 {tag} 與 __version__ {expected} 不一致", file=sys.stderr)
                return 1
            print(f"標籤 {tag} 與 __version__ 一致")
            return 0
        case ["notes", version, out]:
            notes = extract_notes(CHANGELOG.read_text(encoding="utf-8"), tag_version(version))
            if notes is None:
                print(f"CHANGELOG.md 沒有 {version} 的段落", file=sys.stderr)
                return 1
            Path(out).write_text(notes + "\n", encoding="utf-8")
            return 0
        case ["is-prerelease", tag]:
            print("true" if is_prerelease(tag) else "false")
            return 0
        case _:
            print(__doc__, file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
