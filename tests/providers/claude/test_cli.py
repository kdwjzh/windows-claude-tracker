from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from usage_monitor.providers.claude.credentials import cli
from usage_monitor.providers.claude.credentials.cli import CliCredentialSource


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_reads_access_token_and_expiry(tmp_path: Path) -> None:
    expires = datetime(2026, 10, 29, 12, tzinfo=UTC)
    path = _write(
        tmp_path / ".credentials.json",
        {
            "claudeAiOauth": {
                "accessToken": "sk-ant-oat01-test",
                "refreshToken": "never-used",
                "expiresAt": int(expires.timestamp() * 1000),
            }
        },
    )
    token = CliCredentialSource(path).read()
    assert token is not None
    assert token.value == "sk-ant-oat01-test"
    assert token.expires_at == expires
    assert token.source == "cli"


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps([]),
        json.dumps({}),
        json.dumps({"claudeAiOauth": None}),
        json.dumps({"claudeAiOauth": {"accessToken": ""}}),
        json.dumps({"claudeAiOauth": {"accessToken": 123}}),
    ],
)
def test_malformed_returns_none(tmp_path: Path, content: str) -> None:
    path = tmp_path / ".credentials.json"
    path.write_text(content, encoding="utf-8")
    assert CliCredentialSource(path).read() is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert CliCredentialSource(tmp_path / "nope.json").read() is None


def test_unreadable_returns_none(tmp_path: Path) -> None:
    # 資料夾不能當檔案讀 → OSError
    assert CliCredentialSource(tmp_path).read() is None


def test_signature_changes_with_content(tmp_path: Path) -> None:
    path = tmp_path / ".credentials.json"
    source = CliCredentialSource(path)
    assert source.signature().endswith("|missing")
    _write(path, {"claudeAiOauth": {"accessToken": "a"}})
    first = source.signature()
    _write(path, {"claudeAiOauth": {"accessToken": "abcdef"}})
    assert source.signature() != first
    assert "abcdef" not in source.signature()


def test_path_honours_claude_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert cli.credentials_path() == tmp_path / "cfg" / ".credentials.json"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    assert cli.credentials_path() == tmp_path / "home" / ".claude" / ".credentials.json"
    assert CliCredentialSource().path == cli.credentials_path()
