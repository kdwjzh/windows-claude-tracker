"""產生 PyInstaller 的 Windows 版本資訊檔（exe 內容→詳細資料看到的版本），版本取自 __version__。

python scripts/version_info.py <輸出檔> <內部名稱> <檔案描述> <原始檔名>
python scripts/version_info.py --print-version
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "src" / "usage_monitor" / "__init__.py"
PRODUCT = "Claude Usage Tracker"


def read_version() -> str:
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', INIT.read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit(f"{INIT} 找不到 __version__")
    return m[1]


def numeric(version: str) -> tuple[int, int, int, int]:
    """ "1.2.3-beta.1" → (1, 2, 3, 0)；Windows 的檔案版本只能是四個數字。"""
    parts = [int(x) for x in re.findall(r"\d+", version.split("-")[0])][:3]
    parts += [0] * (4 - len(parts))
    return parts[0], parts[1], parts[2], parts[3]


def render(version: str, internal: str, description: str, filename: str) -> str:
    v = numeric(version)
    return f"""# 由 scripts/version_info.py 產生，不要手動修改
VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{PRODUCT}'),
      StringStruct('FileDescription', '{description}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{internal}'),
      StringStruct('OriginalFilename', '{filename}'),
      StringStruct('ProductName', '{PRODUCT}'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main(argv: list[str]) -> int:
    if argv == ["--print-version"]:
        print(read_version())
        return 0
    if len(argv) != 4:
        print(__doc__)
        return 2
    out, internal, description, filename = argv
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(render(read_version(), internal, description, filename), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
