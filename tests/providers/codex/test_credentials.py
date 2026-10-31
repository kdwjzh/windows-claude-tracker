from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from usage_monitor.providers.codex import credentials
from usage_monitor.providers.codex.credentials import CodexCredentialSource, jwt_expiry

EXP = datetime(2026, 11, 5, 8, tzinfo=UTC)


def fake_jwt(payload: object) -> str:
    def part(data: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{part({'alg': 'none'})}.{part(payload)}.c2ln"


def write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_reads_token_account_and_jwt_expiry(tmp_path: Path) -> None:
    token = fake_jwt({"exp": int(EXP.timestamp())})
    path = write(
        tmp_path / "auth.json",
        {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": {
                "id_token": "x",
                "access_token": token,
                "refresh_token": "never-used",
                "account_id": "acct-123",
            },
        },
    )
    auth = CodexCredentialSource(path).read_auth()
    assert auth is not None
    assert auth.token.value == token
    assert auth.token.expires_at == EXP
    assert auth.token.source == "codex_cli"
    assert auth.account_id == "acct-123"
    assert "acct-123" not in repr(auth)
    assert CodexCredentialSource(path).read() == auth.token


def test_opaque_token_has_no_expiry(tmp_path: Path) -> None:
    path = write(tmp_path / "auth.json", {"tokens": {"access_token": "opaque", "account_id": ""}})
    auth = CodexCredentialSource(path).read_auth()
    assert auth is not None
    assert auth.token.expires_at is None
    assert auth.account_id is None


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps([]),
        json.dumps({"OPENAI_API_KEY": "sk-x"}),  # 用 API key 登入：沒有 ChatGPT 帳號額度
        json.dumps({"tokens": None}),
        json.dumps({"tokens": {"access_token": "  "}}),
    ],
)
def test_malformed_returns_none(tmp_path: Path, content: str) -> None:
    path = tmp_path / "auth.json"
    path.write_text(content, encoding="utf-8")
    source = CodexCredentialSource(path)
    assert source.read_auth() is None
    assert source.read() is None


def test_missing_and_unreadable(tmp_path: Path) -> None:
    assert CodexCredentialSource(tmp_path / "none.json").read_auth() is None
    assert CodexCredentialSource(tmp_path).read_auth() is None  # 資料夾不能當檔案讀


@pytest.mark.parametrize(
    "token",
    ["opaque", "a.b", "a.!!!.c", f"a.{base64.urlsafe_b64encode(b'[1]').decode()}.c"],
)
def test_jwt_expiry_tolerates_garbage(token: str) -> None:
    assert jwt_expiry(token) is None


def test_signature(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    source = CodexCredentialSource(path)
    assert source.signature().endswith("|missing")
    write(path, {"tokens": {"access_token": "a"}})
    first = source.signature()
    write(path, {"tokens": {"access_token": "abcdef"}})
    assert source.signature() != first
    assert "abcdef" not in source.signature()


def test_path_honours_codex_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "ch"))
    assert credentials.auth_path() == tmp_path / "ch" / "auth.json"
    monkeypatch.delenv("CODEX_HOME")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    assert credentials.auth_path() == tmp_path / "home" / ".codex" / "auth.json"
    assert CodexCredentialSource().path == credentials.auth_path()
