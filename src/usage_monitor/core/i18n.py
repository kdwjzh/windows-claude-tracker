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
    "reset_updating": "已重置 · 更新中",
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
    "nav_usage": "用量",
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
    "tray_icon": "系統匣圖示顯示",
    "tray_icon_hint": (
        "自動：顯示最近有在用（用量有增加）的監控對象；"
        "剛開程式時，先顯示同時有 5h 與 7d 額度中用量最高的"
    ),
    "tray_icon_auto": "自動（最近使用的）",
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
    "diagnose_hint": "檢查 token 來源與 API，結果可以複製；輸出不含完整 token",
    "run": "執行",
    "history_clear": "清除用量歷史",
    "history_clear_hint": "每次更新的百分比與時間只存在這台電腦，保留 90 天；不含 token 或對話內容",
    "history_clear_button": "清除",
    "history_clear_confirm": "要刪除所有用量歷史紀錄嗎？刪除後無法復原。",
    "history_cleared": "已清除",
    "usage_none": "沒有啟用任何 AI 監控對象",
    "usage_line_title": "過去 7 天的 {period}用量",
    "usage_bars_title": "每個 {period}週期的最高用量",
    "usage_average": "最近 {n} 個週期平均用到 {percent}",
    "usage_current": "本期",
    "usage_no_data": "還沒有紀錄",
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
    "update_install": "立即更新",
    "update_status_downloading": "正在下載 v{version}…",
    "update_status_install_failed": "更新失敗，請按「前往下載」手動更新",
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
    "notify_update_body": "點這則通知查看並更新。",
    "notify_updated_title": "用量監控已更新到 v{version}",
    "notify_updated_body": "新版本已經在執行，點這則通知查看。",
    # 診斷工具（diagnose）
    "diag_window_title": "用量監控 · 診斷",
    "diag_window_hint": (
        "逐步檢查 token 來源、解密與 API；輸出不含完整 token，可以按「複製」貼到問題回報"
    ),
    "diag_running": "診斷中…",
    "diag_copy": "複製",
    "diag_copied": "已複製",
    "diag_rerun": "重新執行",
    "diag_window_failed": "診斷時發生錯誤（{error}），詳細內容請看 log",
    "diag_title": "用量監控診斷 v{version}｜{time}",
    "diag_description": (
        "檢查 token 來源與 API，指出卡在哪一步。輸出不含完整 token，可以直接貼給別人看。"
    ),
    "diag_arg_poll": "只呼叫一次 API 並印出用量",
    "diag_arg_no_api": "只檢查 token 來源，不呼叫 API",
    "diag_arg_debug": "顯示 debug log（不含 token）",
    "diag_arg_lang": "輸出語言（預設跟隨設定檔的 language）",
    "diag_arg_dump": "呼叫一次用量 API，把去識別化的回應存成 JSON 檔（可當測試 fixture）",
    "diag_dump_saved": "已存成 {path}（已去識別化，送出前仍請自己看過一次）",
    "diag_dump_none": "沒有收到可以存的回應",
    "diag_mask_short": "***（{n} 字元）",
    "diag_no_expiry": "沒有到期時間",
    "diag_expired": "{time}（已過期 {ago}）",
    "diag_expires_in": "{time}（還有 {countdown}）",
    "diag_paren": "（{text}）",
    "diag_none": "沒有",
    "diag_yes": "有",
    "diag_unset": "未設定",
    "diag_cli_env": "CLAUDE_CONFIG_DIR：{value}",
    "diag_cli_missing": "{path}：不存在（沒有用 CLI 登入，可忽略）",
    "diag_cli_unreadable": "{path}：存在但讀不到 accessToken",
    "diag_cli_token": "{path}：token {token}",
    "diag_expiry": "到期：{expiry}",
    "diag_cli_expired": "CLI token 已過期，會改用桌面版",
    "diag_not_object": "不是 JSON 物件",
    "diag_desktop_section": "Claude 桌面版候選資料夾（依優先順序；→ 是實際會用的 token）",
    "diag_dir_missing": "資料夾不存在",
    "diag_files": "config.json：{config}｜Local State：{state}",
    "diag_config_failed": "config.json 讀取失敗：{error}",
    "diag_caches": "token cache：{names}",
    "diag_caches_empty": "（空值略過：{names}）",
    "diag_no_key": "Local State 沒有 os_crypt.encrypted_key",
    "diag_dpapi_failed": "DPAPI 解金鑰失敗：{error}",
    "diag_dpapi_ok": "DPAPI 解金鑰成功（{n} bytes）",
    "diag_decrypt_failed": "[{name}] 解密失敗：{error}",
    "diag_decrypted_not_object": "[{name}] 解密後不是 JSON 物件",
    "diag_decrypted": "[{name}] 解密成功，{n} 筆",
    "diag_scopes_unknown": "（無法解析）",
    "diag_entry_empty": "scopes={scopes}  token=（空）",
    "diag_entry": "scopes={scopes}  token={token}  到期={expiry}",
    "diag_markers_section": "舊路徑的搬家標記",
    "diag_marker": "{dir}：{names}（資料已搬到新路徑）",
    "diag_api_section": "實際呼叫 {name} API",
    "diag_api_failed": "失敗（{kind}{status}）：{message}",
    "diag_http": "，HTTP {status}",
    "diag_source": "token 來源：{source}",
    "diag_api_ok": "成功，token 來源：{source}",
    "diag_window_reset": "{countdown}後重置（{moment}）",
    "diag_summary": "結論",
    "diag_ok": "可以正常取得用量",
    "diag_ok_no_api": "token 來源看起來正常（沒有呼叫 API）",
    "diag_problem_dpapi": (
        "DPAPI 解不開桌面版的金鑰：請用登入 Windows 的同一個使用者執行，不要用系統管理員或其他帳號"
    ),
    "diag_problem_decrypt": "桌面版 token cache 解不開：config.json 與 Local State 可能不是同一組",
    "diag_problem_no_desktop": (
        "找不到 Claude 桌面版的資料（config.json＋Local State）：確認已安裝桌面版並登入過；"
        "若資料夾又搬家，請回報上面列出的路徑"
    ),
    "diag_problem_no_token": "桌面版沒有任何登入 token：請開啟 Claude 桌面版並登入",
    "diag_problem_expired": "桌面版的 token 都已過期：開啟 Claude 桌面版讓它自動更新登入",
    "diag_hint_auth": "登入資訊無效或被拒絕：開啟 Claude 桌面版確認已登入",
    "diag_hint_transient": (
        "網路或伺服器暫時有問題：稍後再試；公司網路請確認能連到 api.anthropic.com"
    ),
    "diag_hint_unsupported": "這個帳號不支援用量 API，備援也失敗：請把這份輸出回報",
}

_EN: dict[str, str] = {
    "loading": "Loading…",
    "unreported_detail": "Not reported for this plan",
    "full": "Full",
    "full_resets": "Full · resets {time}",
    "reset_updating": "Reset · updating",
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
    "nav_usage": "Usage",
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
    "tray_icon": "Tray icon shows",
    "tray_icon_hint": (
        "Auto shows the one you used most recently (its usage went up); right after start, "
        "the highest usage among those with both 5h and 7d limits"
    ),
    "tray_icon_auto": "Auto (most recently used)",
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
    "diagnose_hint": (
        "Checks token sources and the API; the result can be copied and never shows full tokens"
    ),
    "run": "Run",
    "history_clear": "Clear usage history",
    "history_clear_hint": (
        "Usage percentages and times from each refresh, kept on this computer for 90 days; "
        "never tokens or conversations"
    ),
    "history_clear_button": "Clear",
    "history_clear_confirm": "Delete all usage history? This can't be undone.",
    "history_cleared": "Cleared",
    "usage_none": "No AI services are being monitored",
    "usage_line_title": "{period} usage, last 7 days",
    "usage_bars_title": "Peak usage per {period} period",
    "usage_average": "Last {n} periods averaged {percent}",
    "usage_current": "Now",
    "usage_no_data": "No history yet",
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
    "update_install": "Update now",
    "update_status_downloading": "Downloading v{version}…",
    "update_status_install_failed": "Update failed. Use Download to update by hand",
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
    "notify_update_body": "Click this notification to see the update.",
    "notify_updated_title": "Usage Monitor updated to v{version}",
    "notify_updated_body": "The new version is running. Click this notification to see it.",
    # Diagnostics (diagnose)
    "diag_window_title": "Usage Monitor · Diagnostics",
    "diag_window_hint": (
        "Checks the token sources, the decryption and the API step by step. The output never "
        "contains full tokens: press Copy and paste it into a bug report"
    ),
    "diag_running": "Running diagnostics…",
    "diag_copy": "Copy",
    "diag_copied": "Copied",
    "diag_rerun": "Run again",
    "diag_window_failed": "Diagnostics hit an error ({error}); see the log for details",
    "diag_title": "Usage Monitor diagnostics v{version} | {time}",
    "diag_description": (
        "Checks the token sources and the API and shows where it gets stuck. "
        "The output never contains a full token, so it's safe to share."
    ),
    "diag_arg_poll": "call the API once and print the usage",
    "diag_arg_no_api": "only check the token sources, don't call the API",
    "diag_arg_debug": "show debug logs (never contain tokens)",
    "diag_arg_lang": "output language (default: the language in the settings file)",
    "diag_arg_dump": (
        "call the usage API once and save the anonymized response as a JSON file "
        "(usable as a test fixture)"
    ),
    "diag_dump_saved": "Saved to {path} (anonymized; still look it over before sharing it)",
    "diag_dump_none": "No response that could be saved",
    "diag_mask_short": "*** ({n} chars)",
    "diag_no_expiry": "no expiry time",
    "diag_expired": "{time} (expired {ago})",
    "diag_expires_in": "{time} ({countdown} left)",
    "diag_paren": " ({text})",
    "diag_none": "none",
    "diag_yes": "yes",
    "diag_unset": "not set",
    "diag_cli_env": "CLAUDE_CONFIG_DIR: {value}",
    "diag_cli_missing": "{path}: not found (not signed in with the CLI; safe to ignore)",
    "diag_cli_unreadable": "{path}: exists, but no accessToken could be read",
    "diag_cli_token": "{path}: token {token}",
    "diag_expiry": "Expires: {expiry}",
    "diag_cli_expired": "The CLI token has expired, so the desktop app's token will be used",
    "diag_not_object": "not a JSON object",
    "diag_desktop_section": (
        "Claude desktop app folders (in priority order; → marks the token that will be used)"
    ),
    "diag_dir_missing": "folder not found",
    "diag_files": "config.json: {config} | Local State: {state}",
    "diag_config_failed": "Couldn't read config.json: {error}",
    "diag_caches": "token cache: {names}",
    "diag_caches_empty": " (empty, skipped: {names})",
    "diag_no_key": "Local State has no os_crypt.encrypted_key",
    "diag_dpapi_failed": "DPAPI couldn't decrypt the key: {error}",
    "diag_dpapi_ok": "DPAPI decrypted the key ({n} bytes)",
    "diag_decrypt_failed": "[{name}] couldn't be decrypted: {error}",
    "diag_decrypted_not_object": "[{name}] decrypted, but it isn't a JSON object",
    "diag_decrypted": "[{name}] decrypted, {n} entries",
    "diag_scopes_unknown": "(couldn't parse)",
    "diag_entry_empty": "scopes={scopes}  token=(empty)",
    "diag_entry": "scopes={scopes}  token={token}  expires={expiry}",
    "diag_markers_section": "Migration markers in the old folders",
    "diag_marker": "{dir}: {names} (the data has moved to the new folder)",
    "diag_api_section": "Calling the {name} API",
    "diag_api_failed": "Failed ({kind}{status}): {message}",
    "diag_http": ", HTTP {status}",
    "diag_source": "Token source: {source}",
    "diag_api_ok": "Success, token source: {source}",
    "diag_window_reset": "resets in {countdown} ({moment})",
    "diag_summary": "Summary",
    "diag_ok": "Usage can be fetched normally",
    "diag_ok_no_api": "The token sources look fine (the API wasn't called)",
    "diag_problem_dpapi": (
        "DPAPI can't decrypt the desktop app's key: run this as the same user who is signed in "
        "to Windows, not as an administrator or another account"
    ),
    "diag_problem_decrypt": (
        "The desktop app's token cache can't be decrypted: "
        "config.json and Local State may not belong together"
    ),
    "diag_problem_no_desktop": (
        "No Claude desktop app data found (config.json + Local State): make sure the desktop "
        "app is installed and you've signed in; if its folder has moved again, please report "
        "the paths listed above"
    ),
    "diag_problem_no_token": (
        "The desktop app has no sign-in token: open Claude Desktop and sign in"
    ),
    "diag_problem_expired": (
        "All of the desktop app's tokens have expired: open Claude Desktop so it renews the sign-in"
    ),
    "diag_hint_auth": (
        "The sign-in is invalid or was rejected: open Claude Desktop and check you're signed in"
    ),
    "diag_hint_transient": (
        "A temporary network or server problem: try again later; "
        "on a company network, check that api.anthropic.com is reachable"
    ),
    "diag_hint_unsupported": (
        "This account doesn't support the usage API and the fallback failed too: "
        "please report this output"
    ),
}

CATALOG: dict[Lang, dict[str, str]] = {Lang.ZH_TW: _ZH_TW, Lang.EN: _EN}


def t(lang: Lang, key: str, **params: object) -> str:
    """取字並代入參數。缺 key 時退回繁體中文，再缺就回傳 key 本身（不讓畫面崩潰）。"""
    text = CATALOG[lang].get(key) or _ZH_TW.get(key) or key
    return text.format(**params) if params else text


def has(key: str) -> bool:
    return key in _ZH_TW
