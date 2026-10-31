"""診斷工具（主控台）：python -m usage_monitor.diagnose。

逐步檢查 Claude 的 token 來源與 API，清楚指出卡在哪一步。

安全：
- token 只印遮罩後的樣子（前 14 碼＋末 4 碼；太短的整個遮掉）
- token cache 的 key 含安裝 ID 與帳號 ID，只印出其中的 scope
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from usage_monitor import __version__
from usage_monitor.core import i18n, timefmt
from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.i18n import Lang, t
from usage_monitor.core.interfaces import Clock, Provider
from usage_monitor.core.json_access import as_dict, as_str, parse_unix_ms
from usage_monitor.core.models import Window
from usage_monitor.platform import oscrypt
from usage_monitor.platform.clock import SystemClock
from usage_monitor.platform.http import RequestsTransport, inject_truststore
from usage_monitor.providers import registry
from usage_monitor.providers.claude.credentials import desktop_paths
from usage_monitor.providers.claude.credentials.cli import CliCredentialSource
from usage_monitor.providers.claude.credentials.desktop import CACHE_KEYS, cache_values
from usage_monitor.providers.claude.credentials.scopes import entry_scopes, select_token

MASK_MIN_LEN = 24


def mask(token: str) -> str:
    """前 14 碼＋末 4 碼；太短（測試用或格式異常）的整個遮掉。"""
    token = token.strip()
    if len(token) < MASK_MIN_LEN:
        return f"***（{len(token)} 字元）"
    return f"{token[:14]}…{token[-4:]}"


def describe_expiry(expires_at: datetime | None, now: datetime) -> str:
    if expires_at is None:
        return "沒有到期時間"
    local = expires_at.astimezone().strftime("%Y-%m-%d %H:%M")
    if expires_at <= now:
        return f"{local}（已過期 {timefmt.ago(expires_at, now).removesuffix('前')}）"
    return f"{local}（還有 {timefmt.countdown(expires_at, now)}）"


@dataclass
class Report:
    """收集輸出與問題；`problems` 是最後「結論」要列出的待處理事項。"""

    lines: list[str] = field(default_factory=list[str])
    problems: list[str] = field(default_factory=list[str])

    def section(self, title: str) -> None:
        if self.lines:
            self.lines.append("")
        self.lines.append(f"== {title} ==")

    def ok(self, text: str, indent: int = 1) -> None:
        self.lines.append(f"{'  ' * indent}✓ {text}")

    def fail(self, text: str, indent: int = 1) -> None:
        self.lines.append(f"{'  ' * indent}✗ {text}")

    def info(self, text: str, indent: int = 1) -> None:
        self.lines.append(f"{'  ' * indent}· {text}")

    def problem(self, text: str) -> None:
        if text not in self.problems:
            self.problems.append(text)

    def text(self) -> str:
        return "\n".join(self.lines)


# ---------------------------------------------------------------- CLI


def check_cli(report: Report, source: CliCredentialSource, now: datetime) -> None:
    report.section("Claude Code CLI")
    custom = os.environ.get("CLAUDE_CONFIG_DIR")
    report.info(f"CLAUDE_CONFIG_DIR：{custom or '未設定'}")
    path = source.path
    if not path.exists():
        report.info(f"{path}：不存在（沒有用 CLI 登入，可忽略）")
        return
    token = source.read()
    if token is None:
        report.fail(f"{path}：存在但讀不到 accessToken")
        return
    report.ok(f"{path}：token {mask(token.value)}")
    report.info(f"到期：{describe_expiry(token.expires_at, now)}", indent=2)
    if token.is_expired(now):
        report.info("CLI token 已過期，會改用桌面版", indent=2)


# ---------------------------------------------------------------- 桌面版


def _load_json(path: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        data = as_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        return None, type(e).__name__
    return (data, None) if data is not None else (None, "不是 JSON 物件")


@dataclass
class DirResult:
    has_files: bool = False
    key_ok: bool = False
    has_token: bool = False
    has_valid_token: bool = False
    used: bool = False
    """這個資料夾的 token 就是程式實際會用的那一個。"""


def check_desktop_dir(
    report: Report,
    directory: Path,
    unprotect: Callable[[bytes], bytes],
    now: datetime,
    *,
    may_use: bool = True,
) -> DirResult:
    """`may_use`：前面的資料夾還沒有可用的 token（程式會往下找到這裡）。

    與 DesktopCredentialSource 相同的規則：每個資料夾只看第一個挑得出 token 的 cache；
    該 token 未過期就採用，否則換下一個資料夾。實際採用的那一筆標 `→`。
    """
    result = DirResult()
    dir_picked = False
    config_path, state_path = directory / "config.json", directory / "Local State"
    report.lines.append(f"  {directory}")
    if not directory.exists():
        report.info("資料夾不存在", indent=2)
        return result
    has_config, has_state = config_path.exists(), state_path.exists()
    exists = {True: "有", False: "沒有"}
    report.info(f"config.json：{exists[has_config]}｜Local State：{exists[has_state]}", indent=2)
    if not (has_config and has_state):
        return result
    result.has_files = True

    config, err = _load_json(config_path)
    if config is None:
        report.fail(f"config.json 讀取失敗：{err}", indent=2)
        return result
    values = cache_values(config)
    empty = [k for k in CACHE_KEYS if as_str(config.get(k)) == ""]
    report.info(
        f"token cache：{', '.join(n for n, _ in values) or '沒有'}"
        + (f"（空值略過：{', '.join(empty)}）" if empty else ""),
        indent=2,
    )
    if not values:
        return result

    state, err = _load_json(state_path)
    encrypted = as_str((as_dict((state or {}).get("os_crypt")) or {}).get("encrypted_key"))
    if not encrypted:
        report.fail(f"Local State 沒有 os_crypt.encrypted_key{f'（{err}）' if err else ''}", 2)
        return result
    try:
        key = oscrypt.unwrap_key(encrypted, unprotect)
    except (OSError, ValueError) as e:
        report.fail(f"DPAPI 解金鑰失敗：{e}", indent=2)
        report.problem(
            "DPAPI 解不開桌面版的金鑰："
            "請用登入 Windows 的同一個使用者執行，不要用系統管理員或其他帳號"
        )
        return result
    report.ok(f"DPAPI 解金鑰成功（{len(key)} bytes）", indent=2)
    result.key_ok = True

    for name, value in values:
        try:
            entries = as_dict(json.loads(oscrypt.decrypt_v10(value, key).decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as e:
            report.fail(f"[{name}] 解密失敗：{e}", indent=2)
            report.problem("桌面版 token cache 解不開：config.json 與 Local State 可能不是同一組")
            continue
        if not entries:
            report.fail(f"[{name}] 解密後不是 JSON 物件", indent=2)
            continue
        picked = select_token(entries)
        use_this = False
        if picked is not None and not dir_picked:
            dir_picked = True
            pick_expiry = parse_unix_ms(picked.expires_at_ms)
            use_this = may_use and (pick_expiry is None or pick_expiry > now)
            result.used = use_this
        report.ok(f"[{name}] 解密成功，{len(entries)} 筆", indent=2)
        for entry_key, raw in entries.items():
            entry = as_dict(raw) or {}
            token = (as_str(entry.get("token")) or "").strip()
            expires = parse_unix_ms(entry.get("expiresAt"))
            chosen = use_this and picked is not None and token == picked.token
            scopes = " ".join(entry_scopes(entry_key)) or "（無法解析）"
            if not token:
                report.info(f"scopes={scopes}  token=（空）", indent=3)
                continue
            result.has_token = True
            if expires is None or expires > now:
                result.has_valid_token = True
            report.lines.append(
                f"      {'→' if chosen else ' '} scopes={scopes}  token={mask(token)}"
                f"  到期={describe_expiry(expires, now)}"
            )
    return result


def check_desktop(
    report: Report,
    dirs: Sequence[Path],
    unprotect: Callable[[bytes], bytes],
    now: datetime,
) -> None:
    report.section("Claude 桌面版候選資料夾（依優先順序；→ 是實際會用的 token）")
    results: list[DirResult] = []
    for d in dirs:
        may_use = not any(r.used for r in results)
        results.append(check_desktop_dir(report, d, unprotect, now, may_use=may_use))
    if not any(r.has_files for r in results):
        report.problem(
            "找不到 Claude 桌面版的資料（config.json＋Local State）：確認已安裝桌面版並登入過；"
            "若資料夾又搬家，請回報上面列出的路徑"
        )
    elif any(r.key_ok for r in results) and not any(r.has_token for r in results):
        report.problem("桌面版沒有任何登入 token：請開啟 Claude 桌面版並登入")
    elif any(r.has_token for r in results) and not any(r.has_valid_token for r in results):
        report.problem("桌面版的 token 都已過期：開啟 Claude 桌面版讓它自動更新登入")


def check_markers(report: Report, dirs: Sequence[Path]) -> None:
    report.section("舊路徑的搬家標記")
    found = False
    for d in dirs:
        try:
            markers = sorted(p.name for p in d.glob(desktop_paths.MOVED_MARKER_GLOB))
        except OSError:
            markers = []
        if markers:
            found = True
            report.info(f"{d}：{', '.join(markers)}（資料已搬到新路徑）")
    if not found:
        report.info("沒有")


# ---------------------------------------------------------------- API


_HINTS = {
    ErrKind.AUTH: "登入資訊無效或被拒絕：開啟 Claude 桌面版確認已登入",
    ErrKind.TRANSIENT: "網路或伺服器暫時有問題：稍後再試；公司網路請確認能連到 api.anthropic.com",
    ErrKind.UNSUPPORTED: "這個帳號不支援用量 API，備援也失敗：請把這份輸出回報",
}


def _window_line(w: Window, now: datetime) -> str:
    label = w.label or "?"
    if not w.available:
        return f"{label:>4}  —"
    text = f"{label:>4}  {w.percent:5.1f}%"
    if w.resets_at:
        text += (
            f"  {timefmt.countdown(w.resets_at, now)}後重置"
            f"（{timefmt.reset_moment(w.resets_at, now)}）"
        )
    return text


def _source(provider: Provider) -> str:
    """來源代碼翻成中文（診斷工具不做多語系）。"""
    code = provider.source_label()
    if not code:
        return "—"
    key = f"source_{code}"
    return t(Lang.ZH_TW, key) if i18n.has(key) else code


def check_api(report: Report, provider: Provider, clock: Clock) -> bool:
    report.section(f"實際呼叫 {provider.display_name} API")
    try:
        usage = provider.poll()
    except PollError as e:
        report.fail(f"失敗（{e.kind.name}{f'，HTTP {e.status}' if e.status else ''}）：{e.message}")
        report.info(f"token 來源：{_source(provider)}")
        report.problem(_HINTS[e.kind])
        return False
    now = clock.now()
    report.ok(f"成功，token 來源：{_source(provider)}")
    report.info(_window_line(usage.session, now))
    report.info(_window_line(usage.long, now))
    return True


# ---------------------------------------------------------------- 組合


def run(
    report: Report,
    *,
    clock: Clock,
    cli: CliCredentialSource,
    dirs: Sequence[Path],
    unprotect: Callable[[bytes], bytes],
    provider: Provider | None,
) -> bool:
    """跑完所有檢查並寫出結論；回傳是否成功取得用量（沒有呼叫 API 時看有沒有問題）。"""
    now = clock.now()
    report.lines.append(f"用量監控診斷 v{__version__}｜{now.astimezone():%Y-%m-%d %H:%M}")
    check_cli(report, cli, now)
    check_desktop(report, dirs, unprotect, now)
    check_markers(report, dirs)
    api_ok = check_api(report, provider, clock) if provider is not None else None

    report.section("結論")
    if api_ok:
        report.ok("可以正常取得用量")
    elif api_ok is None and not report.problems:
        report.ok("token 來源看起來正常（沒有呼叫 API）")
    for p in report.problems:
        (report.info if api_ok else report.fail)(p)
    return api_ok if api_ok is not None else not report.problems


def poll_only(provider: Provider, clock: Clock) -> int:
    report = Report()
    ok = check_api(report, provider, clock)
    for p in report.problems:
        report.info(p)
    print(report.text())
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m usage_monitor.diagnose",
        description=(
            "檢查 token 來源與 API，指出卡在哪一步。輸出不含完整 token，可以直接貼給別人看。"
        ),
    )
    parser.add_argument("--poll", choices=registry.available(), help="只呼叫一次 API 並印出用量")
    parser.add_argument("--no-api", action="store_true", help="只檢查 token 來源，不呼叫 API")
    parser.add_argument("--debug", action="store_true", help="顯示 debug log（不含 token）")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    inject_truststore()
    clock = SystemClock()

    if args.poll:
        return poll_only(registry.create(args.poll, RequestsTransport(), clock), clock)

    report = Report()
    ok = run(
        report,
        clock=clock,
        cli=CliCredentialSource(),
        dirs=desktop_paths.data_dirs(),
        unprotect=oscrypt.dpapi_unprotect,
        provider=None if args.no_api else registry.create("claude", RequestsTransport(), clock),
    )
    print(report.text())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
