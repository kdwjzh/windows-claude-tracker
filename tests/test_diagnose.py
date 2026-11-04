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
from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.i18n import Lang
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
    empty_profile(monkeypatch, tmp_path)
    assert diagnose.main(["--no-api", "--lang", "zh-TW"]) == 1
    out = capsys.readouterr().out
    assert "找不到 Claude 桌面版的資料" in out
    assert "實際呼叫" not in out


def empty_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(tmp_path / var))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    # 不依賴這台機器的 Windows 語言（CI runner 是英文）
    monkeypatch.setattr(diagnose, "system_ui_languages", lambda: ["zh-TW"])


# ---------------------------------------------------------------- 語言（ROADMAP 第 10 項）


def test_main_language_follows_settings_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty_profile(monkeypatch, tmp_path)
    assert diagnose.main(["--no-api"]) == 1
    assert "找不到 Claude 桌面版的資料" in capsys.readouterr().out  # "system" → Windows 語言
    settings = tmp_path / "APPDATA" / "MyUsageMonitor" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"language": "en"}), encoding="utf-8")
    assert diagnose.main(["--no-api"]) == 1
    out = capsys.readouterr().out
    assert "No Claude desktop app data found" in out
    assert "== Summary ==" in out
    assert diagnose.main(["--no-api", "--lang", "zh-TW"]) == 1  # --lang 優先
    assert "== 結論 ==" in capsys.readouterr().out
    assert settings.read_text(encoding="utf-8") == '{"language": "en"}'  # 只讀不寫


@pytest.mark.parametrize(
    ("content", "expected"),
    [('{"language": "en"}', "en"), ('{"language": "fr"}', "system"), ("{bad", "system"),
     ("[]", "system")],
)  # fmt: skip
def test_settings_language(tmp_path: Path, content: str, expected: str) -> None:
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")
    assert diagnose.settings_language(path) == expected
    assert diagnose.settings_language(tmp_path / "missing.json") == "system"


def test_english_report(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "claude_pzs8sxrjxfjjc", entry(LONG_TOKEN, NOW + timedelta(hours=1)))
    report = diagnose.Report(lang=Lang.EN)
    ok = diagnose.run(
        report,
        clock=FakeClock(NOW),
        cli=CliCredentialSource(tmp_path / "cli" / ".credentials.json"),
        dirs=[d],
        unprotect=identity,
        provider=FakeProvider("claude", [USAGE], source="desktop"),
    )
    text = report.text()
    assert "token source: Desktop app" in text
    assert ok
    assert "✓ DPAPI decrypted the key (32 bytes)" in text
    assert "resets in 1h 47m" in text
    assert "✓ Usage can be fetched normally" in text
    assert not any("一" <= ch <= "鿿" for ch in text)  # 沒有任何中文字


def test_english_api_failure_uses_reason_text(capsys: pytest.CaptureFixture[str]) -> None:
    error = PollError(ErrKind.AUTH, "HTTP 401：被拒絕", status=401, reason=ErrReason.REJECTED)
    assert diagnose.poll_only(FakeProvider("claude", [error]), FakeClock(NOW), Lang.EN) == 1
    out = capsys.readouterr().out
    assert "Failed (AUTH, HTTP 401)" in out
    assert "The sign-in is invalid or was rejected" in out
    assert "被拒絕" not in out


def test_english_expiry_and_mask() -> None:
    assert diagnose.mask("short", Lang.EN) == "*** (5 chars)"
    assert "(2h 0m left)" in diagnose.describe_expiry(NOW + timedelta(hours=2), NOW, Lang.EN)
    assert "(expired 3 hr ago)" in diagnose.describe_expiry(NOW - timedelta(hours=3), NOW, Lang.EN)


def test_report_text_for_the_app_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """主程式的診斷視窗用：回傳文字、不 print（主程式用 --noconsole 打包）。"""
    empty_profile(monkeypatch, tmp_path)
    text = diagnose.report_text(Lang.EN, call_api=False)
    assert "No Claude desktop app data found" in text
    assert "== Summary ==" in text
    assert capsys.readouterr().out == ""


# -------------------------------------------------------- --dump-response（ROADMAP 第 14 項）


def test_anonymize_hides_ids_emails_and_tokens() -> None:
    body = {
        "user_id": "user-abc",
        "email": "someone@example.com",
        "plan_type": "plus",
        "nested": {"account_id": "acc_1", "note": "sk-ant-oat01-xyz", "id_list": ["a"]},
        "rows": [{"display_name": "Opus", "percent": 68}],
        "uuid_like": "123e4567-e89b-12d3-a456-426614174000",
        "jwt": "eyJhbGciOi.payload.sig",
        "resets_at": "2026-11-04T13:30:00+00:00",
        "count": 3,
        "flag": None,
    }
    assert diagnose.anonymize(body) == {
        "user_id": "<redacted>",
        "email": "<redacted>",
        "plan_type": "plus",
        "nested": {"account_id": "<redacted>", "note": "<redacted>", "id_list": ["a"]},
        "rows": [{"display_name": "<redacted>", "percent": 68}],
        "uuid_like": "<redacted>",
        "jwt": "<redacted>",
        "resets_at": "2026-11-04T13:30:00+00:00",
        "count": 3,
        "flag": None,
    }


def test_fixtures_are_anonymized() -> None:
    """tests/fixtures/ 裡的回應再跑一次去識別化不會有任何變化（沒有漏掉的 ID 或 token）。"""
    for path in (Path(__file__).parent / "fixtures").rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert diagnose.anonymize(data) == data, path.name


def test_dump_payload_prefers_json_then_ratelimit_headers() -> None:
    from usage_monitor.core.interfaces import Response

    json_resp = Response(200, {}, b'{"email": "a@b.c", "x": 1}')
    headers_resp = Response(
        429, {"anthropic-ratelimit-unified-5h-utilization": "0.4", "Server": "x"}, b"not json"
    )
    assert diagnose.dump_payload([json_resp, headers_resp]) == {"email": "<redacted>", "x": 1}
    assert diagnose.dump_payload([headers_resp]) == {
        "headers": {"anthropic-ratelimit-unified-5h-utilization": "0.4"}
    }
    assert diagnose.dump_payload([]) is None


def test_dump_response_writes_fixture_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from fakes import FakeTransport
    from usage_monitor.core.interfaces import Response

    url = "https://example.test/usage"
    fake = FakeTransport().add("GET", url, Response(200, {}, b'{"user_id": "u1", "percent": 5}'))
    monkeypatch.setattr(diagnose, "RequestsTransport", lambda: fake)

    class CallsApi(FakeProvider):
        def __init__(self, transport) -> None:  # type: ignore[no-untyped-def]
            super().__init__("codex", [USAGE])
            self._transport = transport

        def poll(self):  # type: ignore[no-untyped-def]
            self._transport.get(url, {}, timeout=30)
            return super().poll()

    monkeypatch.setattr(
        diagnose.registry, "create", lambda pid, transport, clock: CallsApi(transport)
    )
    assert diagnose.dump_response("codex", tmp_path, FakeClock(NOW), Lang.EN) == 0
    (saved,) = tmp_path.glob("usage_codex_*.json")
    assert json.loads(saved.read_text(encoding="utf-8")) == {"user_id": "<redacted>", "percent": 5}
    assert "Saved to" in capsys.readouterr().out
