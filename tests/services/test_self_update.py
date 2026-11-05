"""「立即更新」的下載與核對：用 FakeTransport 模擬 GitHub 的轉址與附件，不連網路。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from fakes import FakeTransport
from usage_monitor.core import app_info
from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.interfaces import Response
from usage_monitor.services.self_update import (
    InstallError,
    download_update,
    expected_hash,
    fetch,
)
from usage_monitor.services.update_check import UpdateState, UpdateStatus

EXE = b"MZ new version"
NAME = "ClaudeUsageTracker-v2.0.0.exe"
EXE_URL = f"{app_info.DOWNLOAD_PREFIX}v2.0.0/{NAME}"
SUMS_URL = f"{app_info.DOWNLOAD_PREFIX}v2.0.0/SHA256SUMS.txt"
CDN = "https://release-assets.githubusercontent.com/github-production-release-asset/1"


def state(**changes: object) -> UpdateState:
    values: dict[str, object] = {
        "current_version": "1.3.0",
        "status": UpdateStatus.AVAILABLE,
        "latest_version": "2.0.0",
        "exe_url": EXE_URL,
        "sums_url": SUMS_URL,
    }
    values.update(changes)
    return UpdateState(**values)  # type: ignore[arg-type]


def sums(body: bytes = EXE, name: str = NAME) -> bytes:
    return f"{hashlib.sha256(body).hexdigest()}  {name}\n".encode()


def redirect(to: str, status: int = 302) -> Response:
    return Response(status, headers={"location": to})


def transport(exe: bytes = EXE, sums_body: bytes | None = None) -> FakeTransport:
    return (
        FakeTransport()
        .add("GET", SUMS_URL, redirect(CDN + "/sums"))
        .add("GET", CDN + "/sums", Response(200, body=sums_body if sums_body else sums()))
        .add("GET", EXE_URL, redirect(CDN + "/exe"))
        .add("GET", CDN + "/exe", Response(200, body=exe))
    )


def test_downloads_verifies_and_renames(tmp_path: Path) -> None:
    t = transport()
    path = download_update(t, state(), tmp_path)
    assert path == tmp_path / NAME
    assert path.read_bytes() == EXE
    assert [p.name for p in tmp_path.iterdir()] == [NAME]  # 沒有留下暫存檔
    assert all("Authorization" not in c.headers for c in t.calls)
    assert {c.headers["User-Agent"] for c in t.calls} == {f"{app_info.REPO_NAME}/1.3.0"}


def test_checksum_mismatch_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(InstallError, match="SHA-256"):
        download_update(transport(exe=b"tampered"), state(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_sums_without_this_file(tmp_path: Path) -> None:
    t = transport(sums_body=sums(name="other.exe"))
    with pytest.raises(InstallError, match="SHA256SUMS"):
        download_update(t, state(), tmp_path)


@pytest.mark.parametrize(
    "changes", [{"exe_url": None}, {"sums_url": None}, {"latest_version": None}]
)
def test_missing_assets(tmp_path: Path, changes: dict[str, object]) -> None:
    with pytest.raises(InstallError):
        download_update(FakeTransport(), state(**changes), tmp_path)


def test_write_failure_cleans_up(tmp_path: Path) -> None:
    missing = tmp_path / "gone"  # 資料夾不存在 → 寫不進去
    with pytest.raises(InstallError, match="寫不進"):
        download_update(transport(), state(), missing)


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/x.exe",
        "http://objects.githubusercontent.com/x.exe",
        "https://githubusercontent.com.evil.example/x.exe",
    ],
)
def test_redirect_to_other_host_is_refused(target: str) -> None:
    t = FakeTransport().add("GET", EXE_URL, redirect(target))
    with pytest.raises(InstallError, match="不允許"):
        fetch(t, EXE_URL, "ua")
    assert len(t.calls) == 1  # 沒有連到轉址目標


def test_relative_redirect_and_limits() -> None:
    t = FakeTransport().add("GET", EXE_URL, redirect("/elsewhere", 307))
    t.add("GET", "https://github.com/elsewhere", Response(200, body=b"ok"))
    assert fetch(t, EXE_URL, "ua") == b"ok"

    loop = FakeTransport().add("GET", EXE_URL, *[redirect(EXE_URL)] * 10)
    with pytest.raises(InstallError, match="太多"):
        fetch(loop, EXE_URL, "ua")

    no_location = FakeTransport().add("GET", EXE_URL, Response(302))
    with pytest.raises(InstallError, match="Location"):
        fetch(no_location, EXE_URL, "ua")


@pytest.mark.parametrize(
    "result", [Response(404), Response(500), PollError(ErrKind.TRANSIENT, "斷線")]
)
def test_http_and_network_errors(result: Response | BaseException) -> None:
    with pytest.raises(InstallError):
        fetch(FakeTransport().add("GET", EXE_URL, result), EXE_URL, "ua")


def test_expected_hash_parsing() -> None:
    text = b"ABC123  a.exe\nbad line\ndef456 *b.exe\n"
    assert expected_hash(text, "a.exe") == "abc123"
    assert expected_hash(text, "b.exe") == "def456"
    assert expected_hash(text, "c.exe") is None


def test_reports_percent_of_the_exe_only(tmp_path: Path) -> None:
    percents: list[int] = []
    download_update(transport(), state(), tmp_path, on_percent=percents.append)
    assert percents == [100]  # FakeTransport 一次給完；SHA256SUMS.txt 不算進度
