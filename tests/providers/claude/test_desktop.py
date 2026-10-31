"""桌面版 token 解密：用測試內自產的金鑰加密假資料，DPAPI 用假的（直接回傳）。"""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from desktop_fixtures import entry, identity, make_dir
from fakes import FakeClock
from usage_monitor.providers.claude.credentials.desktop import DesktopCredentialSource, read_dir

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def source(*dirs: Path) -> DesktopCredentialSource:
    return DesktopCredentialSource(FakeClock(NOW), dirs=lambda: list(dirs), unprotect=identity)


def test_reads_token_from_v2_cache(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", entry("desk-token", NOW + timedelta(hours=1)))
    token = read_dir(d, identity)
    assert token is not None
    assert token.value == "desk-token"
    assert token.expires_at == NOW + timedelta(hours=1)
    assert token.source == "desktop"


def test_falls_back_to_v1_cache_and_skips_empty_v2(tmp_path: Path) -> None:
    d = make_dir(
        tmp_path / "a",
        entry("v1-token", NOW + timedelta(hours=1)),
        cache_key="oauth:tokenCache",
        extra={"oauth:tokenCacheV2": ""},
    )
    token = read_dir(d, identity)
    assert token is not None and token.value == "v1-token"


def test_v2_undecryptable_falls_back_to_v1(tmp_path: Path) -> None:
    d = make_dir(
        tmp_path / "a",
        entry("v1-token", NOW + timedelta(hours=1)),
        cache_key="oauth:tokenCache",
        extra={"oauth:tokenCacheV2": base64.b64encode(b"v10" + b"\0" * 40).decode()},
    )
    token = read_dir(d, identity)
    assert token is not None and token.value == "v1-token"


@pytest.mark.parametrize("missing", ["config.json", "Local State"])
def test_missing_files_return_none(tmp_path: Path, missing: str) -> None:
    d = make_dir(tmp_path / "a", entry("t", NOW + timedelta(hours=1)))
    (d / missing).unlink()
    assert read_dir(d, identity) is None


def test_no_cache_keys_returns_none(tmp_path: Path) -> None:
    assert read_dir(make_dir(tmp_path / "a"), identity) is None


def test_wrong_key_returns_none(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", entry("t", NOW + timedelta(hours=1)))
    other = make_dir(tmp_path / "b")  # 換成別的資料夾的 Local State
    (d / "Local State").write_bytes((other / "Local State").read_bytes())
    assert read_dir(d, identity) is None


def test_dpapi_failure_returns_none(tmp_path: Path) -> None:
    d = make_dir(tmp_path / "a", entry("t", NOW + timedelta(hours=1)))

    def failing(_: bytes) -> bytes:
        raise OSError("DPAPI 失敗")

    assert read_dir(d, failing) is None


@pytest.mark.parametrize(
    "state",
    ["not json", json.dumps({}), json.dumps({"os_crypt": {"encrypted_key": "@@@"}})],
)
def test_bad_local_state_returns_none(tmp_path: Path, state: str) -> None:
    d = make_dir(tmp_path / "a", entry("t", NOW + timedelta(hours=1)))
    (d / "Local State").write_text(state, encoding="utf-8")
    assert read_dir(d, identity) is None


def test_decrypted_payload_not_json_returns_none(tmp_path: Path) -> None:
    key = os.urandom(32)
    d = make_dir(tmp_path / "a", key=key)
    nonce = os.urandom(12)
    blob = base64.b64encode(b"v10" + nonce + AESGCM(key).encrypt(nonce, b"\xff\xfe", None))
    (d / "config.json").write_text(json.dumps({"oauth:tokenCacheV2": blob.decode()}))
    assert read_dir(d, identity) is None


def test_source_returns_first_unexpired_across_dirs(tmp_path: Path) -> None:
    expired = make_dir(tmp_path / "new", entry("old", NOW - timedelta(minutes=1)))
    valid = make_dir(tmp_path / "legacy", entry("fresh", NOW + timedelta(hours=1)))
    token = source(tmp_path / "missing", expired, valid).read()
    assert token is not None and token.value == "fresh"


def test_source_returns_expired_when_nothing_valid(tmp_path: Path) -> None:
    expired = make_dir(tmp_path / "a", entry("old", NOW - timedelta(minutes=1)))
    token = source(expired).read()
    assert token is not None and token.value == "old"


def test_source_returns_none_when_nothing_found(tmp_path: Path) -> None:
    assert source(tmp_path / "a", tmp_path / "b").read() is None


def test_signature_ignores_unrelated_config_changes(tmp_path: Path) -> None:
    key = os.urandom(32)
    d = make_dir(tmp_path / "a", entry("t", NOW + timedelta(hours=1)), key=key)
    s = source(d)
    before = s.signature()

    config = json.loads((d / "config.json").read_text())
    config["windowState"] = {"x": 999}  # 桌面版移動視窗時會改寫
    (d / "config.json").write_text(json.dumps(config))
    assert s.signature() == before

    make_dir(d, entry("t2", NOW + timedelta(hours=2)), key=key)  # 重新登入
    after = s.signature()
    assert after != before
    assert "t2" not in after


def test_signature_of_missing_dir(tmp_path: Path) -> None:
    assert source(tmp_path / "none").signature() == f"{tmp_path / 'none'}|"
