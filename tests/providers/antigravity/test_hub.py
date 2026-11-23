from __future__ import annotations

import json
import os
from pathlib import Path

from usage_monitor.providers.antigravity.hub import Hub, HubSource


def write(directory: Path, name: str, data: object, mtime: int) -> Path:
    path = directory / name
    path.write_text(json.dumps(data), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def hub(pid: int, port: int, token: str = "csrf") -> dict[str, object]:
    return {"pid": pid, "httpsPort": port - 1, "httpPort": port, "lsVersion": "2.34.0",
            "csrfToken": token}  # fmt: skip


def test_reads_newest_hub_whose_process_is_running(tmp_path: Path) -> None:
    write(tmp_path, "hub_1.json", hub(10, 1001), 1000)
    write(tmp_path, "hub_2.json", hub(20, 2002), 3000)  # 最新但程序已結束（當掉留下的）
    write(tmp_path, "hub_3.json", hub(30, 3003), 2000)
    write(tmp_path, "other.json", hub(40, 4004), 9000)
    source = HubSource(tmp_path, is_running=lambda pid: pid != 20)
    assert source.read() == Hub(30, 3003, "csrf")


def test_token_not_in_repr() -> None:
    assert "secret" not in repr(Hub(1, 2, "secret"))


def test_invalid_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "hub_bad.json").write_text("{", encoding="utf-8")
    write(tmp_path, "hub_list.json", [], 1)
    write(tmp_path, "hub_no_token.json", {**hub(1, 1001), "csrfToken": " "}, 1)
    write(tmp_path, "hub_bad_port.json", hub(1, 70000), 1)
    write(tmp_path, "hub_no_pid.json", {"httpPort": 1001, "csrfToken": "x"}, 1)
    assert HubSource(tmp_path, is_running=lambda _: True).read() is None


def test_missing_directory(tmp_path: Path) -> None:
    source = HubSource(tmp_path / "nope", is_running=lambda _: True)
    assert source.read() is None
    assert source.signature().endswith("|missing")


def test_signature_changes_when_hub_is_rewritten(tmp_path: Path) -> None:
    source = HubSource(tmp_path, is_running=lambda _: True)
    empty = source.signature()
    path = write(tmp_path, "hub_1.json", hub(1, 1001), 1000)
    first = source.signature()
    write(tmp_path, "hub_1.json", hub(2, 1002, "other-token"), 2000)
    assert len({empty, first, source.signature()}) == 3
    assert "csrf" not in first and path.name in first
