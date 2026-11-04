"""診斷工具（主控台）：python -m usage_monitor.diagnose。

逐步檢查 Claude 的 token 來源與 API，清楚指出卡在哪一步。
輸出語言：`--lang`（從儀表板執行時會帶目前的語言）＞設定檔的 language＞Windows 顯示語言；
文字都在 core/i18n.py（diag_* key）。debug log 維持中文（給維護者看）。

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
from usage_monitor.core.i18n import LANGUAGE_CHOICES, Lang, resolve_language, t
from usage_monitor.core.interfaces import Clock, Provider
from usage_monitor.core.json_access import as_dict, as_str, parse_unix_ms
from usage_monitor.core.models import Window
from usage_monitor.platform import oscrypt, paths
from usage_monitor.platform.clock import SystemClock
from usage_monitor.platform.http import RequestsTransport, inject_truststore
from usage_monitor.platform.ui_language import system_ui_languages
from usage_monitor.providers import registry
from usage_monitor.providers.claude.credentials import desktop_paths
from usage_monitor.providers.claude.credentials.cli import CliCredentialSource
from usage_monitor.providers.claude.credentials.desktop import CACHE_KEYS, cache_values
from usage_monitor.providers.claude.credentials.scopes import entry_scopes, select_token

MASK_MIN_LEN = 24


def mask(token: str, lang: Lang = Lang.ZH_TW) -> str:
    """前 14 碼＋末 4 碼；太短（測試用或格式異常）的整個遮掉。"""
    token = token.strip()
    if len(token) < MASK_MIN_LEN:
        return t(lang, "diag_mask_short", n=len(token))
    return f"{token[:14]}…{token[-4:]}"


def describe_expiry(expires_at: datetime | None, now: datetime, lang: Lang = Lang.ZH_TW) -> str:
    if expires_at is None:
        return t(lang, "diag_no_expiry")
    local = expires_at.astimezone().strftime("%Y-%m-%d %H:%M")
    if expires_at <= now:
        ago = timefmt.ago(expires_at, now, lang)
        ago = ago.removesuffix("前") if lang is Lang.ZH_TW else ago
        return t(lang, "diag_expired", time=local, ago=ago)
    countdown = timefmt.countdown(expires_at, now, lang)
    return t(lang, "diag_expires_in", time=local, countdown=countdown)


def settings_language(path: Path) -> str:
    """設定檔的 language；只讀不寫（不用 SettingsStore：它遇到壞檔會改名）。"""
    try:
        data = as_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return "system"
    value = as_str((data or {}).get("language"))
    return value if value in LANGUAGE_CHOICES else "system"


@dataclass
class Report:
    """收集輸出與問題；`problems` 是最後「結論」要列出的待處理事項。"""

    lines: list[str] = field(default_factory=list[str])
    problems: list[str] = field(default_factory=list[str])
    lang: Lang = Lang.ZH_TW

    def t(self, key: str, **params: object) -> str:
        return t(self.lang, key, **params)

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
    report.info(report.t("diag_cli_env", value=custom or report.t("diag_unset")))
    path = source.path
    if not path.exists():
        report.info(report.t("diag_cli_missing", path=path))
        return
    token = source.read()
    if token is None:
        report.fail(report.t("diag_cli_unreadable", path=path))
        return
    report.ok(report.t("diag_cli_token", path=path, token=mask(token.value, report.lang)))
    expiry = describe_expiry(token.expires_at, now, report.lang)
    report.info(report.t("diag_expiry", expiry=expiry), indent=2)
    if token.is_expired(now):
        report.info(report.t("diag_cli_expired"), indent=2)


# ---------------------------------------------------------------- 桌面版


def _load_json(path: Path, lang: Lang) -> tuple[dict[str, object] | None, str | None]:
    try:
        data = as_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        return None, type(e).__name__
    return (data, None) if data is not None else (None, t(lang, "diag_not_object"))


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
        report.info(report.t("diag_dir_missing"), indent=2)
        return result
    has_config, has_state = config_path.exists(), state_path.exists()
    exists = {True: report.t("diag_yes"), False: report.t("diag_none")}
    files = report.t("diag_files", config=exists[has_config], state=exists[has_state])
    report.info(files, indent=2)
    if not (has_config and has_state):
        return result
    result.has_files = True

    config, err = _load_json(config_path, report.lang)
    if config is None:
        report.fail(report.t("diag_config_failed", error=err), indent=2)
        return result
    values = cache_values(config)
    empty = [k for k in CACHE_KEYS if as_str(config.get(k)) == ""]
    names = ", ".join(n for n, _ in values) or report.t("diag_none")
    skipped = report.t("diag_caches_empty", names=", ".join(empty)) if empty else ""
    report.info(report.t("diag_caches", names=names) + skipped, indent=2)
    if not values:
        return result

    state, err = _load_json(state_path, report.lang)
    encrypted = as_str((as_dict((state or {}).get("os_crypt")) or {}).get("encrypted_key"))
    if not encrypted:
        suffix = report.t("diag_paren", text=err) if err else ""
        report.fail(report.t("diag_no_key") + suffix, 2)
        return result
    try:
        key = oscrypt.unwrap_key(encrypted, unprotect)
    except (OSError, ValueError) as e:
        report.fail(report.t("diag_dpapi_failed", error=e), indent=2)
        report.problem(report.t("diag_problem_dpapi"))
        return result
    report.ok(report.t("diag_dpapi_ok", n=len(key)), indent=2)
    result.key_ok = True

    for name, value in values:
        try:
            entries = as_dict(json.loads(oscrypt.decrypt_v10(value, key).decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as e:
            report.fail(report.t("diag_decrypt_failed", name=name, error=e), indent=2)
            report.problem(report.t("diag_problem_decrypt"))
            continue
        if not entries:
            report.fail(report.t("diag_decrypted_not_object", name=name), indent=2)
            continue
        picked = select_token(entries)
        use_this = False
        if picked is not None and not dir_picked:
            dir_picked = True
            pick_expiry = parse_unix_ms(picked.expires_at_ms)
            use_this = may_use and (pick_expiry is None or pick_expiry > now)
            result.used = use_this
        report.ok(report.t("diag_decrypted", name=name, n=len(entries)), indent=2)
        for entry_key, raw in entries.items():
            entry = as_dict(raw) or {}
            token = (as_str(entry.get("token")) or "").strip()
            expires = parse_unix_ms(entry.get("expiresAt"))
            chosen = use_this and picked is not None and token == picked.token
            scopes = " ".join(entry_scopes(entry_key)) or report.t("diag_scopes_unknown")
            if not token:
                report.info(report.t("diag_entry_empty", scopes=scopes), indent=3)
                continue
            result.has_token = True
            if expires is None or expires > now:
                result.has_valid_token = True
            line = report.t(
                "diag_entry",
                scopes=scopes,
                token=mask(token, report.lang),
                expiry=describe_expiry(expires, now, report.lang),
            )
            report.lines.append(f"      {'→' if chosen else ' '} {line}")
    return result


def check_desktop(
    report: Report,
    dirs: Sequence[Path],
    unprotect: Callable[[bytes], bytes],
    now: datetime,
) -> None:
    report.section(report.t("diag_desktop_section"))
    results: list[DirResult] = []
    for d in dirs:
        may_use = not any(r.used for r in results)
        results.append(check_desktop_dir(report, d, unprotect, now, may_use=may_use))
    if not any(r.has_files for r in results):
        report.problem(report.t("diag_problem_no_desktop"))
    elif any(r.key_ok for r in results) and not any(r.has_token for r in results):
        report.problem(report.t("diag_problem_no_token"))
    elif any(r.has_token for r in results) and not any(r.has_valid_token for r in results):
        report.problem(report.t("diag_problem_expired"))


def check_markers(report: Report, dirs: Sequence[Path]) -> None:
    report.section(report.t("diag_markers_section"))
    found = False
    for d in dirs:
        try:
            markers = sorted(p.name for p in d.glob(desktop_paths.MOVED_MARKER_GLOB))
        except OSError:
            markers = []
        if markers:
            found = True
            report.info(report.t("diag_marker", dir=d, names=", ".join(markers)))
    if not found:
        report.info(report.t("diag_none"))


# ---------------------------------------------------------------- API


_HINTS = {
    ErrKind.AUTH: "diag_hint_auth",
    ErrKind.TRANSIENT: "diag_hint_transient",
    ErrKind.UNSUPPORTED: "diag_hint_unsupported",
}


def _window_line(w: Window, now: datetime, lang: Lang = Lang.ZH_TW) -> str:
    label = w.label or "?"
    if not w.available:
        return f"{label:>4}  —"
    text = f"{label:>4}  {w.percent:5.1f}%"
    if w.resets_at:
        countdown = timefmt.countdown(w.resets_at, now, lang)
        moment = timefmt.reset_moment(w.resets_at, now, lang=lang)
        text += "  " + t(lang, "diag_window_reset", countdown=countdown, moment=moment)
    return text


def _source(provider: Provider, lang: Lang) -> str:
    code = provider.source_label()
    if not code:
        return "—"
    key = f"source_{code}"
    return t(lang, key) if i18n.has(key) else code


def _error_text(e: PollError, name: str, lang: Lang) -> str:
    """中文照舊印原訊息（最詳細）；英文改用錯誤原因的英文說明（原訊息只有中文）。"""
    if lang is Lang.ZH_TW:
        return e.message
    if e.reason is None:
        return t(lang, "error_unexpected")
    return t(lang, f"error_{e.reason.value}", name=name, status=e.status or "?")


def check_api(report: Report, provider: Provider, clock: Clock) -> bool:
    report.section(report.t("diag_api_section", name=provider.display_name))
    try:
        usage = provider.poll()
    except PollError as e:
        status = report.t("diag_http", status=e.status) if e.status else ""
        message = _error_text(e, provider.display_name, report.lang)
        report.fail(report.t("diag_api_failed", kind=e.kind.name, status=status, message=message))
        report.info(report.t("diag_source", source=_source(provider, report.lang)))
        report.problem(report.t(_HINTS[e.kind]))
        return False
    now = clock.now()
    report.ok(report.t("diag_api_ok", source=_source(provider, report.lang)))
    report.info(_window_line(usage.session, now, report.lang))
    report.info(_window_line(usage.long, now, report.lang))
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
    title_time = f"{now.astimezone():%Y-%m-%d %H:%M}"
    report.lines.append(report.t("diag_title", version=__version__, time=title_time))
    check_cli(report, cli, now)
    check_desktop(report, dirs, unprotect, now)
    check_markers(report, dirs)
    api_ok = check_api(report, provider, clock) if provider is not None else None

    report.section(report.t("diag_summary"))
    if api_ok:
        report.ok(report.t("diag_ok"))
    elif api_ok is None and not report.problems:
        report.ok(report.t("diag_ok_no_api"))
    for p in report.problems:
        (report.info if api_ok else report.fail)(p)
    return api_ok if api_ok is not None else not report.problems


def report_text(lang: Lang, *, call_api: bool = True) -> str:
    """跑完整診斷並回傳文字（主程式的診斷視窗用；bootstrap 注入給 ui，ui 不直接 import 這裡）。

    會讀檔、解密、呼叫 API：要在背景執行緒呼叫。truststore 由呼叫端先注入。
    """
    clock = SystemClock()
    report = Report(lang=lang)
    run(
        report,
        clock=clock,
        cli=CliCredentialSource(),
        dirs=desktop_paths.data_dirs(),
        unprotect=oscrypt.dpapi_unprotect,
        provider=registry.create("claude", RequestsTransport(), clock) if call_api else None,
    )
    return report.text()


def poll_only(provider: Provider, clock: Clock, lang: Lang = Lang.ZH_TW) -> int:
    report = Report(lang=lang)
    ok = check_api(report, provider, clock)
    for p in report.problems:
        report.info(p)
    print(report.text())
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    lang = resolve_language(settings_language(paths.settings_file()), system_ui_languages())
    parser = argparse.ArgumentParser(
        prog="python -m usage_monitor.diagnose", description=t(lang, "diag_description")
    )
    parser.add_argument("--poll", choices=registry.available(), help=t(lang, "diag_arg_poll"))
    parser.add_argument("--no-api", action="store_true", help=t(lang, "diag_arg_no_api"))
    parser.add_argument("--debug", action="store_true", help=t(lang, "diag_arg_debug"))
    parser.add_argument("--lang", choices=[x.value for x in Lang], help=t(lang, "diag_arg_lang"))
    args = parser.parse_args(argv)
    if args.lang:
        lang = Lang(args.lang)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    inject_truststore()
    clock = SystemClock()

    if args.poll:
        return poll_only(registry.create(args.poll, RequestsTransport(), clock), clock, lang)

    report = Report(lang=lang)
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
