"""多語系（CLAUDE.md §3.8）：語言判斷與翻譯表。純資料與純函式，不做 I/O。

新增或修改文字時，兩種語言都要改；tests/core/test_i18n.py 會檢查 key 與 {參數} 是否一致。
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum


class Lang(Enum):
    ZH_TW = "zh-TW"
    EN = "en"


LANGUAGE_CHOICES = ("system", Lang.ZH_TW.value, Lang.EN.value)
"""設定 `language` 允許的值；"system" 表示跟隨 Windows 顯示語言。"""

LANGUAGE_NAMES = {Lang.ZH_TW: "繁體中文", Lang.EN: "English"}
"""語言名稱一律用該語言本身書寫，不翻譯。"""


def resolve_language(choice: str, ui_languages: Sequence[str]) -> Lang:
    """設定值＋系統顯示語言（例如 Qt 的 uiLanguages()：["zh-Hant-TW", "en-US"]）→ 實際語言。

    "system" 時取系統第一個語言：任何中文（zh*）→ 繁體中文，其他 → English。
    """
    for lang in Lang:
        if choice == lang.value:
            return lang
    first = (ui_languages[0] if ui_languages else "").lower()
    return Lang.ZH_TW if first.startswith("zh") else Lang.EN


_ZH_TW: dict[str, str] = {
    # 小工具與懸停卡
    "loading": "讀取中…",
    "unreported_detail": "這個方案沒有回報此週期",
    "full": "滿",
    "full_resets": "滿 · {time} 重置",
    "period_hours": "{n} 小時",
    "period_days": "{n} 天",
    "note_not_signed_in": "未登入",
    "note_expired": "已過期",
    "note_rejected": "被拒絕",
    "note_unsupported": "不支援",
    "note_offline": "連線失敗",
    "hover_hint": "雙擊立即更新",
    "hover_source": "來源：{source}",
    "hover_updated": "最後更新 {time}",
    "hover_updated_ago": "最後更新 {time}（{ago}）",
    "hover_reset_unknown": "重置時間未知",
    "hover_reset_soon": "即將重置",
    "hover_reset_at": "{moment} 重置（{countdown}後）",
    # 錯誤說明（依 ErrReason）
    "error_no_credentials": "找不到 {name} 登入資訊",
    "error_expired": "{name} 登入已過期",
    "error_rejected": "登入被拒絕（HTTP {status}）",
    "error_rate_limited": "請求太頻繁，稍後會自動重試",
    "error_server": "伺服器暫時無法回應（HTTP {status}）",
    "error_network": "無法連線",
    "error_timeout": "連線逾時",
    "error_unsupported": "用量 API 不支援這個帳號（HTTP {status}）",
    "error_bad_response": "回應格式不認得",
    "error_unexpected": "發生未預期的錯誤",
    # 資料來源（source_label 代碼）
    "source_desktop": "桌面版",
    "source_cli": "CLI",
    "source_codex_cli": "Codex CLI",
    # 系統匣與通知
    "tray_stale": "(舊)",
    "tray_none": "沒有啟用任何服務",
    "tray_error_line": "{name}：{note}",
    "notify_not_signed_in": "{name} 找不到登入資訊",
    "notify_expired": "{name} 登入已過期",
    "notify_rejected": "{name} 登入被拒絕",
    "notify_body": "請開啟 {name} 並確認已登入。登入後會自動恢復，不需要重開本程式。",
    "notify_click": "點這則通知可執行診斷。",
    # 選單
    "menu_refresh": "立即更新",
    "menu_double_click": "雙擊",
    "menu_lock": "鎖定位置",
    "menu_opacity": "不透明度",
    "menu_reset_position": "重設位置",
    "menu_hide": "隱藏小工具",
    "menu_show": "顯示小工具",
    "menu_autostart": "開機時啟動",
    "menu_providers": "AI 監控對象",
    "menu_settings": "開啟儀表板",
    "menu_open_log": "開啟 log",
    "menu_quit": "結束",
    # 設定視窗
    "app_name": "用量監控",
    "settings_title": "用量監控 · 設定",
    "nav_general": "一般",
    "nav_advanced": "進階",
    "nav_about": "關於",
    "section_update": "更新",
    "section_widget": "小工具",
    "section_services": "AI 監控對象",
    "switch_on": "開啟",
    "switch_off": "關閉",
    "interval": "更新間隔",
    "interval_hint": "越短越即時，但不建議低於 1 分鐘",
    "interval_choice": "每 {n} 分鐘",
    "autostart": "開機時啟動",
    "visible": "顯示小工具",
    "locked": "鎖定位置",
    "locked_hint": "避免不小心拖動",
    "opacity": "不透明度",
    "fullscreen": "全螢幕時自動隱藏",
    "fullscreen_hint": "看影片、玩遊戲時不擋畫面",
    "hotkey": "顯示／隱藏快捷鍵",
    "hotkey_change": "變更",
    "hotkey_capturing": "按下新的組合鍵…（Esc 取消）",
    "hotkey_failed": "這組快捷鍵無法使用（格式不支援或被其他程式占用），請換一組",
    "theme": "主題",
    "theme_system": "跟隨 Windows",
    "theme_dark": "深色",
    "theme_light": "淺色",
    "language": "語言",
    "language_system": "跟隨 Windows",
    "status_disabled": "已停用",
    "status_connected": "已連線",
    "status_connected_source": "已連線 · 來源：{source}",
    "status_stale": "暫時連不上 · 顯示 {ago}的資料",
    "status_error": "{note} · {detail}",
    "cli_refresh": "允許 CLI 更新 token",
    "cli_refresh_hint": (
        "沒有其他可用登入、且 Claude Code CLI 的 token 過期時，執行 claude 讓它自己更新"
        "（會用掉少量額度，最多 30 分鐘一次）。需要 Claude Code 2.0.63 以上。"
    ),
    "open_logs": "開啟 log 資料夾",
    "open_logs_hint": "回報問題時附上 monitor.log",
    "open": "開啟",
    "diagnose": "執行診斷",
    "diagnose_hint": "在新視窗檢查 token 來源與 API；輸出不含完整 token",
    "run": "執行",
    "about_app": "用量監控 v{version}",
    "about_desc": "顯示 Claude 與 Codex 訂閱用量",
    "about_settings_file": "設定檔",
    "about_log_file": "log 檔",
    "about_project": "專案網址",
    "about_license": "授權",
    "about_license_value": "MIT",
    "about_disclaimer": (
        "非官方工具，與 Anthropic、OpenAI 無關；Claude、ChatGPT、Codex 為其各自擁有者的商標。"
    ),
    "section_version": "版本與更新",
    "section_project": "專案",
    # 更新檢查（CLAUDE.md §3.9）
    "update_menu": "有新版本 v{version} →",
    "update_check_now": "檢查更新",
    "update_download": "前往下載",
    "update_status_unknown": "尚未檢查",
    "update_status_checking": "檢查中…",
    "update_status_up_to_date": "已是最新版本",
    "update_status_available": "有新版本 v{version}",
    "update_status_skipped": "已略過 v{version}（有更新的版本時會再提醒）",
    "update_status_unavailable": "目前無法檢查",
    "update_auto": "自動檢查更新",
    "update_auto_hint": "啟動時與每 24 小時查一次 GitHub；只連 api.github.com，不傳送任何個人資料",
    "update_skip": "略過這個版本",
    "update_skip_hint": "不再提醒這個版本；更新的版本仍會提醒",
    "notify_update_title": "用量監控有新版本 v{version}",
    "notify_update_body": "點這則通知前往下載頁面。",
}

_EN: dict[str, str] = {
    "loading": "Loading…",
    "unreported_detail": "Not reported for this plan",
    "full": "Full",
    "full_resets": "Full · resets {time}",
    "period_hours": "{n}-hour",
    "period_days": "{n}-day",
    "note_not_signed_in": "Not signed in",
    "note_expired": "Expired",
    "note_rejected": "Rejected",
    "note_unsupported": "Unsupported",
    "note_offline": "Offline",
    "hover_hint": "Double-click to refresh",
    "hover_source": "Source: {source}",
    "hover_updated": "Updated {time}",
    "hover_updated_ago": "Updated {time} ({ago})",
    "hover_reset_unknown": "Reset time unknown",
    "hover_reset_soon": "Resets soon",
    "hover_reset_at": "Resets {moment} (in {countdown})",
    "error_no_credentials": "No {name} sign-in found",
    "error_expired": "{name} sign-in has expired",
    "error_rejected": "Sign-in rejected (HTTP {status})",
    "error_rate_limited": "Rate limited; retrying automatically",
    "error_server": "Server unavailable (HTTP {status})",
    "error_network": "Can't connect",
    "error_timeout": "Connection timed out",
    "error_unsupported": "Usage API not supported for this account (HTTP {status})",
    "error_bad_response": "Unrecognized response",
    "error_unexpected": "Unexpected error",
    "source_desktop": "Desktop app",
    "source_cli": "CLI",
    "source_codex_cli": "Codex CLI",
    "tray_stale": " (stale)",
    "tray_none": "No services enabled",
    "tray_error_line": "{name}: {note}",
    "notify_not_signed_in": "{name}: not signed in",
    "notify_expired": "{name}: sign-in expired",
    "notify_rejected": "{name}: sign-in rejected",
    "notify_body": (
        "Open {name} and make sure you're signed in. "
        "Monitoring resumes automatically; no restart needed."
    ),
    "notify_click": "Click this notification to run diagnostics.",
    "menu_refresh": "Refresh now",
    "menu_double_click": "Double-click",
    "menu_lock": "Lock position",
    "menu_opacity": "Opacity",
    "menu_reset_position": "Reset position",
    "menu_hide": "Hide widget",
    "menu_show": "Show widget",
    "menu_autostart": "Start with Windows",
    "menu_providers": "AI services to monitor",
    "menu_settings": "Open dashboard",
    "menu_open_log": "Open log",
    "menu_quit": "Quit",
    "app_name": "Usage Monitor",
    "settings_title": "Usage Monitor · Settings",
    "nav_general": "General",
    "nav_advanced": "Advanced",
    "nav_about": "About",
    "section_update": "Updates",
    "section_widget": "Widget",
    "section_services": "AI services to monitor",
    "switch_on": "On",
    "switch_off": "Off",
    "interval": "Refresh interval",
    "interval_hint": "Shorter is more up to date; 1 minute or more is recommended",
    "interval_choice": "Every {n} min",
    "autostart": "Start with Windows",
    "visible": "Show widget",
    "locked": "Lock position",
    "locked_hint": "Prevents accidental dragging",
    "opacity": "Opacity",
    "fullscreen": "Hide in full screen",
    "fullscreen_hint": "Stays out of the way of videos and games",
    "hotkey": "Show/hide shortcut",
    "hotkey_change": "Change",
    "hotkey_capturing": "Press a new shortcut… (Esc to cancel)",
    "hotkey_failed": "This shortcut can't be used (unsupported or taken by another app)",
    "theme": "Theme",
    "theme_system": "Follow Windows",
    "theme_dark": "Dark",
    "theme_light": "Light",
    "language": "Language",
    "language_system": "Follow Windows",
    "status_disabled": "Disabled",
    "status_connected": "Connected",
    "status_connected_source": "Connected · Source: {source}",
    "status_stale": "Temporarily offline · showing data from {ago}",
    "status_error": "{note} · {detail}",
    "cli_refresh": "Allow CLI token refresh",
    "cli_refresh_hint": (
        "When no other sign-in works and the Claude Code CLI token has expired, run claude "
        "so it refreshes itself (uses a little quota, at most every 30 minutes). "
        "Requires Claude Code 2.0.63 or later."
    ),
    "open_logs": "Open log folder",
    "open_logs_hint": "Attach monitor.log when reporting a problem",
    "open": "Open",
    "diagnose": "Run diagnostics",
    "diagnose_hint": "Checks token sources and the API in a new window; never shows full tokens",
    "run": "Run",
    "about_app": "Usage Monitor v{version}",
    "about_desc": "Shows your Claude and Codex subscription usage",
    "about_settings_file": "Settings file",
    "about_log_file": "Log file",
    "about_project": "Project page",
    "about_license": "License",
    "about_license_value": "MIT",
    "about_disclaimer": (
        "Unofficial tool, not affiliated with Anthropic or OpenAI. "
        "Claude, ChatGPT and Codex are trademarks of their respective owners."
    ),
    "section_version": "Version and updates",
    "section_project": "Project",
    "update_menu": "New version v{version} →",
    "update_check_now": "Check for updates",
    "update_download": "Download",
    "update_status_unknown": "Not checked yet",
    "update_status_checking": "Checking…",
    "update_status_up_to_date": "You're up to date",
    "update_status_available": "Version v{version} is available",
    "update_status_skipped": "Skipped v{version} (you'll be told about newer versions)",
    "update_status_unavailable": "Can't check right now",
    "update_auto": "Check for updates automatically",
    "update_auto_hint": (
        "Checks GitHub at startup and every 24 hours. "
        "Only contacts api.github.com and sends no personal data."
    ),
    "update_skip": "Skip this version",
    "update_skip_hint": "Stop reminding me about this version; newer versions still notify",
    "notify_update_title": "Usage Monitor v{version} is available",
    "notify_update_body": "Click this notification to open the download page.",
}

CATALOG: dict[Lang, dict[str, str]] = {Lang.ZH_TW: _ZH_TW, Lang.EN: _EN}


def t(lang: Lang, key: str, **params: object) -> str:
    """取字並代入參數。缺 key 時退回繁體中文，再缺就回傳 key 本身（不讓畫面崩潰）。"""
    text = CATALOG[lang].get(key) or _ZH_TW.get(key) or key
    return text.format(**params) if params else text


def has(key: str) -> bool:
    return key in _ZH_TW
