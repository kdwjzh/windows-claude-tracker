"""診斷工具：每一步失敗都要指出原因，且輸出絕不含完整 token 或帳號 ID。"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from desktop_fixtures import KEY_PREFIX, encrypt_entries, entry, identity, make_dir
from fakes import FakeClock, FakeProvider
from usage_monitor import diagnose
from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.models import Usage, Window
from usage_monitor.providers.claude.credentials.cli import CliCredentialSource

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)
LONG_TOKEN = "sk-ant-oat01-" + "S" * 40 + "WXYZ"
USAGE = Usage(
    Window(True, 37, NOW + timedelta(hours=1, minutes=47), "5h"),
    Window(True, 25, None, "7d"),
    NOW,
)


def run(
    tmp_path: Path,
    dirs: list[Path],
    *,
    provider: FakeProvider | None = None,
    unprotect: Callable[[bytes], bytes] = identity,
) -> tuple[bool, str, diagnose.Report]:
    report = diagnose.Report()
    ok = diagnose.run(
        report,
        clock=FakeClock(NOW),
        cli=CliCredentialSource(tmp_path / "cli" / ".credentials.json"),
        dirs=dirs,
        unprotect=unprotect,
        provider=provider,
    )
    return ok, report.text(), report


# ---------------------------------------------------------------- 遮罩


def test_mask_long_token_keeps_only_ends() -> None:
    masked = diagnose.mask(LONG_TOKEN)
    assert masked == "sk-ant-oat01-S…WXYZ"
    assert "S" * 10 not in masked


@pytest.mark.parametrize("token", ["short", "x" * 23])
def test_mask_short_token_hides_everything(token: str) -> None:
    assert diagnose.mask(token) == f"***（{len(token)} 字元）"


def test_describe_expiry() -> None:
    assert diagnose.describe_expiry(None, NOW) == "沒有到期時間"
    assert "還有 2時00分" in diagnose.describe_expiry(NOW + timedelta(hours=2), NOW)
    assert "已過期 3 小時" in diagnose.describe_expiry(NOW - timedelta(hours=3), NOW)


# ---------------------------------------------------------------- 整體流程


def test_healthy_desktop_with_api(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "claude_pzs8sxrjxfjjc", entry(LONG_TOKEN, NOW + timedelta(hours=1)))
    ok, text, report = run(tmp_path, [d], provider=FakeProvider("claude", [USAGE]))
    assert ok
    assert "✓ DPAPI 解金鑰成功（32 bytes）" in text
    assert "[oauth:tokenCacheV2] 解密成功，1 筆" in text
    assert "→ scopes=user:inference user:profile  token=sk-ant-oat01-S…WXYZ" in text
    assert "37.0%" in text
    assert "✓ 可以正常取得用量" in text
    assert report.problems == []


def test_output_never_contains_full_token_or_account_ids(tmp_path: Path) -> None:
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    (cli_dir / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": LONG_TOKEN + "CLI"}}), encoding="utf-8"
    )
    d = make_dir(tmp_path / "a", entry(LONG_TOKEN, NOW + timedelta(hours=1)))
    _, text, _ = run(tmp_path, [d], provider=FakeProvider("claude", [USAGE]))
    assert LONG_TOKEN not in text
    assert "S" * 10 not in text
    assert KEY_PREFIX not in text
    assert "inst:user" not in text


def test_no_api_without_problems(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", entry(LONG_TOKEN, NOW + timedelta(hours=1)))
    ok, text, _ = run(tmp_path, [d])
    assert ok
    assert "沒有呼叫 API" in text


# ---------------------------------------------------------------- → 標記


def _arrows(text: str) -> list[str]:
    return [
        line.split("token=")[1].split()[0]
        for line in text.splitlines()
        if "→" in line and "token=" in line
    ]


def test_arrow_marks_only_first_cache_in_dir(tmp_path: Path) -> None:
    v2_token, v1_token = "V2" + LONG_TOKEN, "V1" + LONG_TOKEN[:-4] + "V1V1"
    d = make_dir(tmp_path / "a", entry(v2_token, NOW + timedelta(hours=1)))
    # 同一個資料夾再加一份舊版 cache（同一把金鑰）
    key = (d / "Local State").read_text()
    raw_key = diagnose.oscrypt.unwrap_key(json.loads(key)["os_crypt"]["encrypted_key"], identity)
    config = json.loads((d / "config.json").read_text())
    config["oauth:tokenCache"] = encrypt_entries(
        entry(v1_token, NOW + timedelta(days=300)), raw_key
    )
    (d / "config.json").write_text(json.dumps(config))

    _, text, _ = run(tmp_path, [d])
    assert _arrows(text) == [diagnose.mask(v2_token)]


def test_arrow_moves_to_next_dir_when_first_is_expired(tmp_path: Path) -> None:
    expired = make_dir(tmp_path / "a", entry("A" + LONG_TOKEN, NOW - timedelta(hours=1)))
    valid = make_dir(
        tmp_path / "b", entry("B" + LONG_TOKEN[:-4] + "BBBB", NOW + timedelta(hours=1))
    )
    later = make_dir(tmp_path / "c", entry("C" + LONG_TOKEN[:-4] + "CCCC", NOW + timedelta(days=9)))
    _, text, _ = run(tmp_path, [expired, valid, later])
    assert _arrows(text) == ["Bsk-ant-oat01-…BBBB"]


# ---------------------------------------------------------------- 卡在哪一步


def test_no_desktop_data(tmp_path: Path) -> None:
    ok, text, report = run(tmp_path, [tmp_path / "missing", tmp_path])
    assert not ok
    assert "資料夾不存在" in text
    assert "config.json：沒有｜Local State：沒有" in text
    assert any("找不到 Claude 桌面版的資料" in p for p in report.problems)


def test_dpapi_failure(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", entry(LONG_TOKEN, NOW + timedelta(hours=1)))

    def failing(_: bytes) -> bytes:
        raise OSError("存取被拒")

    ok, text, report = run(tmp_path, [d], unprotect=failing)
    assert not ok
    assert "✗ DPAPI 解金鑰失敗：存取被拒" in text
    assert any("同一個使用者" in p for p in report.problems)


def test_decrypt_failure_wrong_key(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", entry(LONG_TOKEN, NOW + timedelta(hours=1)))
    other = make_dir(tmp_path / "b")
    (d / "Local State").write_bytes((other / "Local State").read_bytes())
    ok, text, report = run(tmp_path, [d])
    assert not ok
    assert "[oauth:tokenCacheV2] 解密失敗" in text
    assert any("不是同一組" in p for p in report.problems)


def test_only_expired_tokens(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", entry(LONG_TOKEN, NOW - timedelta(hours=3)))
    ok, text, report = run(tmp_path, [d])
    assert not ok
    assert "已過期 3 小時" in text
    assert any("都已過期" in p for p in report.problems)


def test_logged_out_desktop(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", {f"{KEY_PREFIX}:user:inference": {"token": ""}})
    ok, text, report = run(tmp_path, [d])
    assert not ok
    assert "token=（空）" in text
    assert any("沒有任何登入 token" in p for p in report.problems)


def test_empty_cache_keys_are_reported(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", extra={"oauth:tokenCacheV2": "", "oauth:tokenCache": ""})
    _, text, _ = run(tmp_path, [d])
    assert "token cache：沒有（空值略過：oauth:tokenCacheV2, oauth:tokenCache）" in text


@pytest.mark.parametrize(
    ("state", "message"),
    [("{}", "Local State 沒有 os_crypt.encrypted_key"), ("nope", "JSONDecodeError")],
)
def test_bad_local_state(tmp_path: Path, state: str, message: str) -> None:
    d = make_dir(tmp_path / "a", entry(LONG_TOKEN, NOW + timedelta(hours=1)))
    (d / "Local State").write_text(state, encoding="utf-8")
    _, text, _ = run(tmp_path, [d])
    assert message in text


def test_bad_config_json(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", entry(LONG_TOKEN, NOW + timedelta(hours=1)))
    (d / "config.json").write_text("[]", encoding="utf-8")
    _, text, _ = run(tmp_path, [d])
    assert "config.json 讀取失敗：不是 JSON 物件" in text


def test_moved_markers(tmp_path: Path) -> None:
    legacy = tmp_path / "Roaming" / "Claude"
    legacy.mkdir(parents=True)
    (legacy / ".user-data-left.claude_pzs8sxrjxfjjc").write_text("")
    _, text, _ = run(tmp_path, [legacy])
    assert ".user-data-left.claude_pzs8sxrjxfjjc（資料已搬到新路徑）" in text


@pytest.mark.parametrize(
    ("error", "hint"),
    [
        (PollError(ErrKind.AUTH, "登入被拒絕", status=401), "登入資訊無效"),
        (PollError(ErrKind.TRANSIENT, "連線逾時"), "網路或伺服器"),
        (PollError(ErrKind.UNSUPPORTED, "不支援", status=404), "回報"),
    ],
)
def test_api_failure_gives_hint(tmp_path: Path, error: PollError, hint: str) -> None:
    d = make_dir(tmp_path / "a", entry(LONG_TOKEN, NOW + timedelta(hours=1)))
    ok, text, report = run(tmp_path, [d], provider=FakeProvider("claude", [error]))
    assert not ok
    assert f"✗ 失敗（{error.kind.name}" in text
    assert any(hint in p for p in report.problems)


# ---------------------------------------------------------------- CLI


def test_cli_states(tmp_path: Path) -> None:
    _, text, _ = run(tmp_path, [])
    assert "不存在（沒有用 CLI 登入，可忽略）" in text

    cli_file = tmp_path / "cli" / ".credentials.json"
    cli_file.parent.mkdir()
    cli_file.write_text("{}", encoding="utf-8")
    _, text, _ = run(tmp_path, [])
    assert "存在但讀不到 accessToken" in text

    expired_ms = int((NOW - timedelta(hours=1)).timestamp() * 1000)
    cli_file.write_text(
        json.dumps({"claudeAiOauth": {"accessToken": LONG_TOKEN, "expiresAt": expired_ms}}),
        encoding="utf-8",
    )
    _, text, _ = run(tmp_path, [])
    assert "token sk-ant-oat01-S…WXYZ" in text
    assert "CLI token 已過期，會改用桌面版" in text


# ---------------------------------------------------------------- 進入點


def test_poll_only_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert diagnose.poll_only(FakeProvider("claude", [USAGE]), FakeClock(NOW)) == 0
    assert "37.0%" in capsys.readouterr().out


def test_poll_only_failure(capsys: pytest.CaptureFixture[str]) -> None:
    provider = FakeProvider("claude", [PollError(ErrKind.AUTH, "找不到")])
    assert diagnose.poll_only(provider, FakeClock(NOW)) == 1
    assert "登入資訊無效" in capsys.readouterr().out


def test_main_no_api_with_empty_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for var in ("USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(tmp_path / var))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert diagnose.main(["--no-api"]) == 1
    out = capsys.readouterr().out
    assert "找不到 Claude 桌面版的資料" in out
    assert "實際呼叫" not in out
