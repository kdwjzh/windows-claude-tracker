# CLAUDE.md: Claude / Codex usage monitor (Python) — handover notes

> For Claude Code: read this whole file before starting any work. This file holds the specs, decisions and rules; algorithm details (tokens, decryption, API formats) are in `docs/algorithms.md`. If the two disagree, this file wins.
> Version: matches app v1.1.0 | Maintainer: kdwjzh | **Reply to the maintainer in Traditional Chinese**

---

## 1. Goal

A **floating always-on-top Windows widget plus a tray icon** that periodically shows:

- **Claude** (Pro/Max subscription): 5-hour and 7-day usage percentages and reset countdowns
- **Codex (ChatGPT account)**: 5-hour and long-window (weekly or monthly) usage percentages and reset countdowns

### Background

The Microsoft Store version of Claude Desktop moved its data to `%LOCALAPPDATA%\Claude-Data\claude_<publisher>\`, so tools that only look at the old paths can't find the token. Hence this Python rewrite, with **Claude Desktop** as the main token source.

### Non-goals

- No taskbar embedding (the old stage 9 was dropped on 2026-10-31: the floating mode is enough, and embedding into the Windows 11 taskbar is unsupported and expensive to maintain). Build a **floating, draggable, hideable, always-on-top widget above the taskbar** (§3.7); see ADR 0005
- No macOS/Linux support (but the pure logic in `core/` and `providers/` must be testable on Linux)
- No theme engine (internationalization was added to scope on 2026-10-30, see §3.8)
- No automatic download and install of new versions: **check and remind** only; users download from GitHub Releases themselves (§3.9)
- No other services such as Antigravity, Cursor, Grok, Copilot or OpenCode (but the architecture must allow adding one without changing existing code, see §4.3)
- No multiple accounts (one Claude account + one Codex account)
- No reading `~/.claude/.credentials.json` inside WSL; no per-model weekly limits (`weekly_scoped`) or extra usage (`spend`) (decided 2026-10-31)

---

## 2. Decisions

| Topic | Decision | Reason |
| --- | --- | --- |
| Language | Python 3.12 (minimum 3.11) | Fast to develop; `datetime.fromisoformat` accepts `Z` only from 3.11 |
| Project layout | `pyproject.toml` + `src/` layout, package `usage_monitor` | Tests can't accidentally import files from the working directory; tool config in one place |
| Architecture | Layers (core → providers/platform → services → ui) + a service plug-in interface; dependency direction enforced by import-linter | Changing one feature doesn't ripple into others, see §4 and §5 |
| HTTP | `requests` + `truststore.inject_into_ssl()`, behind a `Transport` interface | Uses the Windows certificate store; tests can swap in a fake Transport |
| Decryption | `ctypes` calling `crypt32.CryptUnprotectData` + `cryptography.AESGCM` | No pywin32 dependency |
| UI framework | **PySide6 (Qt 6)**: `QWidget` for the widget, `QSystemTrayIcon` for the tray | Native rounded translucent frameless windows, dragging and per-monitor DPI; the cost is an exe of about 60–80 MB |
| UI look | **Design v1** (`docs/design/v1-*.png`: 10-segment bars, green/yellow/red). The two other directions (double rings, big numbers) are **not used** | Decided 2026-10-29, see ADR 0001 |
| Default poll interval | 5 minutes, minimum 1 minute | |
| Token source order | CLI `.credentials.json` (only if not expired) → desktop new path → desktop old path (regular install) → desktop old path (Store) | See §3.1 |
| Token expiry | Desktop: just re-read. CLI: optionally run `claude -p . --no-session-persistence`, **off by default** | A CLI refresh uses a little quota |
| Refresh token | **Never used by this app** | OAuth refresh tokens rotate; using one would sign the official app out |
| Main API | `GET /api/oauth/usage`; fall back to the Messages API headers only on an "unsupported" 4xx | The fallback costs 1 token of quota |
| Start with Windows | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` | No admin rights needed |
| Single instance | Named mutex `Local\MyUsageMonitor_SingleInstance` | |
| Show/hide shortcut | `Ctrl+Alt+U` by default, changeable in Settings; a failed registration is reported | Still usable if it clashes with other software |
| Settings / log location | `%APPDATA%\MyUsageMonitor\settings.json`, `monitor.log` (RotatingFileHandler 1 MB × 2) | |
| Settings format | JSON with `schema_version`; newer versions migrate old settings automatically | New fields don't break old settings files |
| Quality tools | `ruff` (lint + format), `pyright`, `import-linter`, `pytest` (with `pytest-qt`, `pytest-cov`), `pre-commit` + `gitleaks` | See §5.4 |
| Version control | **Public** GitHub repo `https://github.com/kdwjzh/windows-claude-tracker`, default branch `main`. Never commit tokens, personal paths, account details or screenshots; `.gitignore` excludes `settings.json`, `*.log`, `dist/`, `build/`; `gitleaks` in `pre-commit` scans for secrets before each commit | Anyone can see the full history |
| Packaging | PyInstaller `--noconsole --onefile`, excluding unneeded Qt modules; `diagnose` is built separately with a console | |
| App icon | `assets/app.ico` (a design file from the maintainer, 9 sizes from 16 to 256 px, **never generated or overwritten by code**): the exe icon (`--icon`) and the icon of every window and taskbar button (`QApplication.setWindowIcon()`); `__main__.py` sets the AppUserModelID `kdwjzh.WindowsClaudeTracker` first thing. The tray icon is still drawn dynamically from usage | When run with pythonw, the taskbar then doesn't show the Python icon or group it with other Python programs; the tray must reflect usage live |
| License | This project: MIT (`LICENSE`); Releases include `THIRD_PARTY_LICENSES.txt` (the PySide6/Qt LGPL-3.0 notice and the licenses of other dependencies); the README and the About page carry an unofficial-tool disclaimer | The exe bundles Qt, and the LGPL requires shipping the license and how to get the source |
| Releases | Push a `vX.Y.Z` tag → GitHub Actions (`windows-latest`) builds, tests and uploads the `.exe` files + SHA-256 to a GitHub Release | Every version is built in a clean environment; see §3.9 |
| Update check | **On by default**: checks the latest GitHub Release at start and every 24 hours and reminds the user about new versions; can be turned off in Settings | See §3.9 |
| Internationalization | Traditional Chinese + English; follows the Windows display language by default and can be switched in Settings; the whole UI switches together; translation tables are plain Python dicts (`core/i18n.py`) | See §3.8, ADR 0004 |
| Documentation language | Project documents (README.md, CHANGELOG.md, CLAUDE.md, docs/) are in English, with README.zh-TW.md kept in sync with README.md; code comments, logs and `diagnose` output stay in Traditional Chinese | Readable by international users and contributors; the app UI is already bilingual |

---

## 3. Technical specs

Full algorithm steps (decryption, scope parsing, API fields, the error classification table) are in `docs/algorithms.md`; this section lists specs and decisions only.

### 3.1 Where the Claude tokens are

| Source | Path | Format |
| --- | --- | --- |
| CLI | `%CLAUDE_CONFIG_DIR%\.credentials.json`, otherwise `%USERPROFILE%\.claude\.credentials.json` | Plain text: `claudeAiOauth.accessToken`, `claudeAiOauth.expiresAt` (ms) |
| Desktop (new) | Folders under `%LOCALAPPDATA%\Claude-Data\` matching `^claude_[a-z0-9]{13}$` (`claude_pzs8sxrjxfjjc` first) | OSCrypt v10 |
| Desktop (old, regular install) | `%APPDATA%\Claude\` | OSCrypt v10 |
| Desktop (old, Store) | Folders under `%LOCALAPPDATA%\Packages\` matching `^Claude_[a-z0-9]{13}$` + `\LocalCache\Roaming\Claude\` | OSCrypt v10 |

The new folder is **lowercase** `claude_`; the package folder is **uppercase** `Claude_`. An old folder that only holds a `.user-data-left.claude_<publisher>` marker file has been migrated.

The new path and both old paths are **all kept and searched in order** (decided 2026-10-31): the token is found for both the regular and the Store install, migrated or not.

### 3.2 Desktop decryption (Chromium OSCrypt v10)

Each desktop folder needs two files: `config.json` and `Local State`.

1. `Local State` → `os_crypt.encrypted_key` → base64-decode → must start with `b"DPAPI"` → strip those 5 bytes → `CryptUnprotectData` → 32-byte AES key
2. `config.json` → try `oauth:tokenCacheV2`, then `oauth:tokenCache` (**skip empty strings**) → base64-decode → must start with `b"v10"` → then a 12-byte nonce → the rest is "ciphertext + 16-byte tag" → `AESGCM(key).decrypt(nonce, rest, None)`
3. The plaintext is a JSON object whose keys look like `<install>:<user>:<base url>:<scope1> <scope2> …` and whose values are `{"token": "...", "expiresAt": <ms>}`

**Scope parsing**: split the key on spaces; in the first word, everything after the second-to-last colon is the first scope, and each remaining word is another scope.

**Token selection** (largest wins): `(has both user:inference and user:profile, has user:inference, expiresAt)`.

DPAPI is bound to the signed-in Windows user, so the app must run as a normal user.

### 3.3 Claude usage API

```http
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <token>
anthropic-beta: oauth-2025-04-20
```

- `five_hour.utilization`, `seven_day.utilization`: **0–100**; `resets_at`: ISO 8601 (UTC)
- If `five_hour` / `seven_day` is null, use the `limits[]` item whose `scope` is null and whose `kind` is `session` / `weekly_all` (field `percent`, or its alias `utilization`)
- Neither window present → treated as a format error
- Only 5h and 7d are parsed; `weekly_scoped` (per-model weekly limits) and `spend` (extra usage) are not shown (§1)

**Fallback** (only when the usage API returns a 4xx other than 401/403/429; 5xx never falls back):

```http
POST https://api.anthropic.com/v1/messages
Authorization: Bearer <token>
anthropic-version: 2023-06-01
anthropic-beta: oauth-2025-04-20
{"model":"claude-haiku-4-5","max_tokens":1,"messages":[{"role":"user","content":"."}]}
```

Read the response headers `anthropic-ratelimit-unified-{5h,7d}-utilization` (**0–1, multiply by 100**), `-{5h,7d}-reset` (Unix seconds), `-status` and `-representative-claim`. When `status == rejected` and both utilizations are 0, set the window named by the claim (`five_hour` / `seven_day`) to 100%.

### 3.4 Codex usage API

- Credentials: `%CODEX_HOME%\auth.json`, otherwise `%USERPROFILE%\.codex\auth.json`; read `tokens.access_token` and `tokens.account_id`
- `GET https://chatgpt.com/backend-api/wham/usage` with headers `Authorization: Bearer …`, `User-Agent: codex-cli` and `ChatGPT-Account-Id: <account_id>` (only when present)
- `rate_limit.primary_window` / `secondary_window`: `used_percent` (0–100), `reset_at` (Unix seconds), `limit_window_seconds`
- Use `limit_window_seconds >= 86400` to decide which window is the long one; never rely on primary/secondary order
- **The long window isn't always 7 days**: Codex's long window has been measured at 30 days (`limit_window_seconds = 2592000`). Row labels come from `limit_window_seconds` (18000 → `5h`, 604800 → `7d`, 2592000 → `30d`) and are stored in `Window.label`
- Some accounts have **only a 30-day window and no 5h window**: an unreported period is still drawn as an empty bar showing 0%

### 3.5 Error classification and scheduling

| Situation | Class | Scheduling |
| --- | --- | --- |
| No token found | Auth | Stop calling the API; compare the credential signature every 60 seconds and resume only when it changes |
| Token expired | Auth | Same as above |
| HTTP 401/403 | Auth | Same as above |
| HTTP 429, 5xx | Transient | Exponential backoff `30s × 2^(n-1)`, capped at the poll interval; with `Retry-After`, use the larger value |
| Connection failure, timeout | Transient | Same as above |
| Other 4xx | Unsupported | Claude falls back to the Messages API |
| Bad JSON or no windows at all | Transient | Same as transient, and log it |

Other rules:

- **Each service polls, records errors and backs off independently**: a Claude error never affects Codex's display or schedule
- Auth errors raise a system notification **once**; the flag resets when the error clears
- On failure, keep the last data and mark it `stale`
- When any window's `resets_at` is near, schedule another poll at `resets_at + 10 seconds`
- Countdown text is redrawn every 60 seconds without calling the API
- Only one poll runs at a time; manual refresh wakes the loop with a `threading.Event`

**Credential signatures**: the CLI file uses "path + size + mtime"; the desktop app uses the SHA-256 of the `oauth:tokenCache*` ciphertext. **Don't use the mtime of the desktop `config.json`**: the desktop app rewrites it often, for example to save the window position.

### 3.6 Data model (`core/models.py`)

```python
@dataclass(frozen=True)
class Window:
    available: bool = False  # the service reported this window (0% counts), as opposed to "no data"
    percent: float = 0.0  # 0–100
    resets_at: datetime | None = None  # UTC aware
    label: str | None = None  # "5h", "7d", "30d"; the UI uses a default when None


@dataclass(frozen=True)
class Usage:
    session: Window  # short window (5h)
    long: Window  # long window (7d / 30d)
    fetched_at: datetime


@dataclass(frozen=True)
class ProviderState:  # maintained by the services layer; the UI only reads this
    provider_id: str
    usage: Usage | None  # last successful data
    error: PollError | None  # last error; None on success
    stale: bool  # usage is old (the last poll failed)
    source_label: str | None  # "desktop" / "cli" / "codex_cli"; translated by the UI, never a token
```

Every dataclass is `frozen=True`: once created, data can't be quietly changed by another module.

### 3.7 UI: design v1

Designs: the 5 images `docs/design/v1-*.png` (2× resolution). **The implementation must match these images**; the text below gives exact values, and where image and text differ, the text's values win.

| Artboard | File | Content |
| --- | --- | --- |
| 1 | `docs/design/v1-1-placement.png` | The widget on the desktop and where the tray icon is (the image shows the widget dragged higher; the **default position** is still as described below: bottom right of the work area, 8 px from the edges) |
| 2 | `docs/design/v1-2-states.png` | The widget's 8 states (the basis of the `viewmodel` golden tests) |
| 3 | `docs/design/v1-3-interactions.png` | Hover card, context menu, drag snapping, show/hide |
| 4 | `docs/design/v1-4-tray.png` | The tray icon's 4 states, tooltip, tray menu, Windows notification |
| 5 | `docs/design/v1-5-settings.png` | Settings window |

The images use Noto Sans CJK (Segoe UI wasn't available where they were exported); the app uses `Segoe UI Variable` / `Microsoft JhengHei UI`.

The UI text examples below are in Traditional Chinese because the designs are; every string also has an English version in `core/i18n.py` (§3.8).

**Floating widget (artboards 1 and 2)**

```
┌───────────────────────────────────────────────────────────────────┐
│ ┃  Claude                              │  Codex                   │
│ ┃  5h  ■■■■□□□□□□  42% · 2時13分      │  5h  ■□□□□□□□□□  12% · 3時40分 │
│ ┃  7d  ■■□□□□□□□□  18% · 4天3時       │  30d ■□□□□□□□□□  6% · 29天     │
└───────────────────────────────────────────────────────────────────┘
```

- Dark panel `#232428`, 1 px border `#3a3c42`, 8 px corner radius; a 3 px drag handle `#5b5f67` on the left; a 1 px divider between the two columns
- **Each column shows the service name on top** (11 px, `#a0a4ab`); **each column shows its own period labels** (Codex may show `30d`)
- Each row: label (26 px wide) + 10-segment bar (each segment 8×14 px, 2 px gap, 2 px radius) + (a red `!` only on error) + text (about 92–112 px wide, enough for at least 「滿 · 20:15 重置」/ "Full · resets 20:15")
- Bar colors: < 70% `#35c27a`, 70–89% `#f0b232`, ≥ 90% `#f05a46`; empty segments `#3b3e45`
- Text color `#e6e6e6`; secondary text `#a0a4ab`
- States (artboard 2):
  - **Limit reached**: the text becomes 「滿 · 20:15 重置」/ "Full · resets 20:15" (the local reset time)
  - **Can't find a sign-in**: the bar turns all gray `#4a4d55`, a red `!` follows, the text is `—`, and a red reason appears next to the column name (for example 「未登入」/ "Not signed in", `#f08b7d`); the other column is unaffected
  - **Stale data**: the bar turns dark green `#5f7d6c`, the text dims to `#7c8088`, and 「12 分鐘前」/ "12 min ago" appears next to the column name
  - **Only one service enabled**: the other column disappears and the widget narrows automatically
  - **Locked**: the drag handle becomes a lock icon
  - **Light theme**: follows Windows; background `#f3f3f3`, border `#d4d6db`, text `#1f1f1f`, secondary `#5f6368`, empty segments `#d9dbe0`

**Interactions (artboard 3)**

- After hovering 0.5 seconds, a detail card appears above the widget: service name, data source, each period's percentage and 「今天 20:20 重置（2時13分後）」/ "Resets today 20:20 (in 2h 13m)", last update time, and 「雙擊立即更新」/ "Double-click to refresh"
- Context menu: Refresh now (double-click) / — / Lock position / Opacity › (100%, 90%, 75%, 60%) / Reset position / — / Hide widget (Ctrl+Alt+U) / Open dashboard (opens the Settings window) / Open log / — / Quit
- While dragging, show a blue outline `#7fb3ff`; on release within 12 px of a work-area edge, snap to it (8 px from the edge after snapping)
- Show/hide: tray left-click, the shortcut (`Ctrl+Alt+U` by default, changeable in Settings), or the context menu. Auto-hide in full screen (a maximized window isn't full screen); a manual hide is never undone by leaving full screen

**Tray and notifications (artboard 4)**

- **A single tray icon** (decided 2026-10-31): it draws both periods of the first enabled service (usually Claude); the tooltip has one line per service
- Icon: 64×64 dark rounded square, top bar 5h, bottom bar 7d, same color rules as above
  - **Red dot** = needs action (not signed in, expired, rejected)
  - **Gray dot** = stale data (temporarily unreachable)
- Tooltip: one line per service, for example `Claude 5h 42% · 2時13分 | 7d 18% · 4天3時`, **at most 127 characters** in total
- Tray context menu: Show widget ✓ / Refresh now / — / Lock position / Reset position / — / Start with Windows ✓ / Open dashboard (opens the Settings window) / Open log / — / Quit
  - When a new version exists, the **top** of the menu gets an extra 「有新版本 v1.2.0 →」/ "New version v1.2.0 →" item + separator, which opens the Release page; the tray icon gets a blue dot `#7fb3ff` at the bottom right (a different spot from the red and gray dots, so they can appear together)
- Windows notifications appear only when action is needed, once per error type; buttons "Run diagnostics" and "Close". A temporary network outage never notifies

**Settings window (artboard 5)**

- Windows 11 style, navigation on the left: General / Advanced / About
- Font: **bold** everywhere; Traditional Chinese uses Microsoft JhengHei (微軟正黑體), English keeps the widget's font list (`theme.FONT_FAMILIES`) (decided 2026-11-02)
- General: Updates (refresh interval, start with Windows), Widget (show, lock position, opacity slider, hide in full screen, show/hide shortcut, theme), Services (Claude and Codex switches + connection status and source)
- Advanced: allow CLI token refresh (off by default), open log folder, run diagnostics
- About (not in the designs; follow this description): GitHub icon + current version `v1.2.0` + "Check for updates" button (refresh icon); below it a status line: "You're up to date" / "Version v1.3.0 is available" (with a "Download" link) / "Can't check right now"; a "Check for updates automatically" switch (on by default); "Skip this version"; project page, license (MIT); and a disclaimer line at the bottom ("Unofficial tool, not affiliated with Anthropic or OpenAI. Claude, ChatGPT and Codex are trademarks of their respective owners." and the Chinese equivalent)
- Changes apply immediately; there is no "Save" button

**Window attributes**

- `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`
- `WA_TranslucentBackground`, `WA_ShowWithoutActivating`, plus `WS_EX_NOACTIVATE` added via ctypes
- Every 2 seconds (or on `WM_WINDOWPOSCHANGING`), call `SetWindowPos(HWND_TOPMOST, … SWP_NOACTIVATE|SWP_NOMOVE|SWP_NOSIZE)` again
- The position is saved as "screen name + coordinates relative to that screen's work area"; if the screen is gone or the position is off screen, fall back to the default position on the primary screen (bottom right of the work area, 8 px from the edges)

### 3.8 Internationalization (added 2026-10-30)

- Languages: Traditional Chinese (`zh-TW`), English (`en`)
- The `language` setting: `"system"` (default; follows the Windows display language: any `zh*` → Traditional Chinese, anything else → English), `"zh-TW"`, `"en"`; a "Language" drop-down under Settings "General → Widget", applied immediately
- **The whole UI switches together**: widget (countdowns, full, not signed in…), hover card, tray tooltip and menu, Windows notifications, Settings window
- Translation tables live in `core/i18n.py`: one `{key: text}` dict per language, looked up with `t(lang, key, **params)`; tests guarantee both languages have exactly the same keys and `{params}`
- Time formats by language: Chinese 「2時13分」「4天3時」「滿 · 20:15 重置」; English "2h 13m", "4d 3h", "Full · resets 20:15"
- Errors: `PollError` carries a `reason` (`ErrReason`, for example no token, expired, HTTP 401), and the UI shows text for that reason in the current language; `message` stays in Chinese and is for logs only
- Sources: `source_label` is a code (`desktop`, `cli`, `codex_cli`) that the UI translates (「桌面版」/ "Desktop app", and so on)
- Not translated: logs, `diagnose` (for problem reports, stays in Chinese), code comments

### 3.9 Releases and update check (added 2026-10-30)

**Release workflow (`.github/workflows/release.yml`)**

- Trigger: pushing a tag matching `v*.*.*` (for example `v1.2.0`)
- Steps (`windows-latest`): `check.ps1` passes → `build.ps1` builds → the tag version must equal `__version__` in `src/usage_monitor/__init__.py` (fail otherwise) → generate `SHA256SUMS.txt` → create a GitHub Release with `ClaudeUsageTracker-vX.Y.Z.exe`, `diagnose-vX.Y.Z.exe`, `THIRD_PARTY_LICENSES.txt` and `SHA256SUMS.txt`; the notes come from the matching section of `CHANGELOG.md`
- `THIRD_PARTY_LICENSES.txt` (added 2026-10-31): generated by `scripts/third_party_licenses.py` during `build.ps1` from the packages installed at that moment. Contents: Python; PySide6/shiboken6/Qt (LGPL-3.0 notice + where to get the source); the full license texts of requests, urllib3, idna, charset-normalizer, certifi, truststore, cryptography, cffi and the other dependencies; and the full LGPL-3.0/GPL-3.0 texts (`assets/licenses/`, from gnu.org). Qt modules excluded by `build.ps1` (PySide6-Addons and others) are not listed
- Tags containing `-` (for example `v1.2.0-beta.1`) are marked as pre-releases
- Steps to release (also in the README): update `__version__` → update `CHANGELOG.md` → commit → `git tag v1.2.0` → `git push --tags`

**Update check (`services/update_check.py`)**

- API: `GET https://api.github.com/repos/kdwjzh/windows-claude-tracker/releases/latest` with headers `Accept: application/vnd.github+json` and `User-Agent: windows-claude-tracker/<version>`; **no token of any kind**
- The repo owner and name live only in `core/app_info.py` (`REPO_OWNER`, `REPO_NAME`, `RELEASES_URL`); a rename only touches that file
- Strip the `v` from `tag_name` and compare with SemVer; ignore pre-releases and drafts; only a newer version counts as an update
- When: once 30 seconds after start, then every 24 hours, and immediately when "Check for updates" is pressed on the About page; `update_check.enabled` defaults to `true`, and when it's `false` only the manual button checks
- "Skip this version": stored in `update_check.skipped_version`; that version isn't reminded again, newer versions still are
- Errors: 404 (no Release yet or the API is temporarily unavailable), 403/429 (API rate limit) and network errors → status "Can't check right now", **no notification and no error icon**, a debug log entry only
- When a new version exists: an extra tray menu item + blue dot (§3.7); the Windows notification appears **once per new version**
- "Download" opens the Release page (`html_url`); nothing is downloaded inside the app
- All UI text ("Version … is available", "You're up to date", "Can't check right now" and so on) goes through `t()` in `core/i18n.py`, in both languages (§3.8)

---

## 4. Architecture

### 4.1 Directory layout

Principle: **split files by responsibility, not by size**. Each file has one reason to change; things that change together live together. No catch-all `utils.py`.

```
windows_Claude-usage-monitor/
├─ CLAUDE.md
├─ CHANGELOG.md
├─ README.md                   English
├─ README.zh-TW.md             Traditional Chinese (each README links to the other at the top)
├─ LICENSE                     MIT
├─ pyproject.toml              dependencies; ruff, pyright, pytest, import-linter config
├─ .pre-commit-config.yaml
├─ .github/workflows/ci.yml    ubuntu: ruff, pyright, lint-imports, pure-logic tests; windows: windows_only and pytest-qt tests
├─ .github/workflows/release.yml  on a pushed vX.Y.Z tag: build and create a GitHub Release (§3.9)
├─ scripts/
│  ├─ check.ps1                runs every check (must pass before finishing any work)
│  ├─ build.ps1                PyInstaller build (+ generates THIRD_PARTY_LICENSES.txt)
│  ├─ version_info.py          exe file version info
│  ├─ release_notes.py         verifies the tag version, extracts the CHANGELOG section
│  └─ third_party_licenses.py  generates THIRD_PARTY_LICENSES.txt (§3.9)
├─ assets/
│  ├─ app.ico                  app icon (from the maintainer, 9 sizes from 16 to 256 px; not generated by code)
│  └─ licenses/                full LGPL-3.0 and GPL-3.0 texts (included in THIRD_PARTY_LICENSES.txt)
├─ docs/
│  ├─ algorithms.md            algorithm reference: token sources, desktop decryption, API formats, error classification
│  ├─ design/                  UI designs (the 5 v1 PNGs, see §3.7)
│  └─ decisions/               architecture decision records (ADRs), one decision per file
├─ src/usage_monitor/
│  ├─ __main__.py              entry point: python -m usage_monitor (sets the AppUserModelID first)
│  ├─ bootstrap.py             composition root: creates and wires every object (the only place that knows "everything")
│  │
│  ├─ core/                    ① pure logic: no I/O, no Qt / requests / ctypes imports
│  │  ├─ app_info.py           app name, AppUserModelID, REPO_OWNER / REPO_NAME / RELEASES_URL
│  │  ├─ semver.py             version parsing and comparison (pure functions)
│  │  ├─ models.py             Window, Usage, ProviderState
│  │  ├─ errors.py             ErrKind, PollError
│  │  ├─ interfaces.py         Protocols for Provider, CredentialSource, Transport, Clock
│  │  ├─ levels.py             percentage → level (ok / warn / crit); the 70/90 thresholds live only here
│  │  ├─ timefmt.py            countdown text 「2時13分」/ "2h 13m", reset times (per language)
│  │  ├─ i18n.py               Lang, language detection, translation tables and t() (§3.8)
│  │  └─ windows.py            limit_window_seconds → labels "5h / 7d / 30d"
│  │
│  ├─ providers/               ② one folder per service; services never import each other
│  │  ├─ registry.py           list of registered services
│  │  ├─ claude/
│  │  │  ├─ provider.py        ClaudeProvider: credentials → api → parse
│  │  │  ├─ api.py             HTTP calls (through Transport)
│  │  │  ├─ parse.py           response JSON / headers → Usage (pure functions)
│  │  │  └─ credentials/
│  │  │     ├─ cli.py          CliCredentialSource
│  │  │     ├─ desktop.py      DesktopCredentialSource (decryption, token selection)
│  │  │     ├─ desktop_paths.py  desktop candidate path rules (if the paths move again, only this changes)
│  │  │     └─ scopes.py       entry_scopes(), select_token() (pure functions)
│  │  └─ codex/
│  │     ├─ provider.py
│  │     ├─ api.py
│  │     ├─ parse.py
│  │     └─ credentials.py
│  │
│  ├─ platform/                ② Windows adapter layer: every ctypes / winreg call lives here
│  │  ├─ paths.py              APPDATA / LOCALAPPDATA / USERPROFILE, location of assets/app.ico (including the packaged build)
│  │  ├─ app_identity.py       SetCurrentProcessExplicitAppUserModelID (failures are only logged)
│  │  ├─ oscrypt.py            DPAPI + AES-GCM
│  │  ├─ http.py               RequestsTransport (implements Transport)
│  │  ├─ autostart.py
│  │  ├─ single_instance.py
│  │  ├─ hotkey.py             RegisterHotKey
│  │  ├─ fullscreen.py         whether the foreground window is full screen
│  │  └─ topmost.py            WS_EX_NOACTIVATE, re-assert TOPMOST
│  │
│  ├─ services/                ③ application logic: no Qt imports, testable on Linux
│  │  ├─ scheduler.py          independent polling, backoff and auth pause per service
│  │  ├─ state_store.py        holds each service's ProviderState and notifies subscribers on change
│  │  ├─ update_check.py       queries the latest GitHub Release (through Transport) and produces UpdateState
│  │  ├─ settings/
│  │  │  ├─ schema.py          Settings dataclass + defaults + validation
│  │  │  ├─ migrations.py      v1 → v2 → … migration functions
│  │  │  └─ store.py           reads/writes settings.json (atomic writes)
│  │  └─ logging_setup.py      log setup + token-masking filter
│  │
│  ├─ ui/                      ④ UI: reads only ViewModels, never touches providers directly
│  │  ├─ theme.py              every color and size constant (the §3.7 values live only here)
│  │  ├─ viewmodel.py          ProviderState → WidgetVM / TrayVM (pure functions, testable)
│  │  ├─ bridge.py             turns services callbacks into Qt signals delivered on the main thread
│  │  ├─ widget/
│  │  │  ├─ widget.py          the widget window (event handling)
│  │  │  ├─ painter.py         draws from WidgetVM
│  │  │  ├─ placement.py       snapping, position restore (pure functions)
│  │  │  └─ menu.py            context menu
│  │  ├─ tray/
│  │  │  ├─ tray.py
│  │  │  └─ icon.py            draws the icon from TrayVM
│  │  ├─ hovercard.py
│  │  └─ settings_dialog/      Settings window
│  │
│  └─ diagnose.py              diagnostics tool (console)
└─ tests/
   ├─ fixtures/                anonymized API response samples (no tokens)
   ├─ fakes.py                 FakeTransport, FakeClock, FakeProvider, FakeCredentialSource
   ├─ core/                    mirrors the src layout
   ├─ providers/
   ├─ services/
   ├─ ui/                      viewmodel and placement unit tests + pytest-qt smoke tests
   └─ windows_only/            tests that need real Windows, marked @pytest.mark.windows
```

### 4.2 Dependency direction (the most important rule)

```
ui  ──▶  services  ──▶  providers  ──▶  core
                 ╲          │            ▲
                  ╲         ▼            │
                   ╲──▶  platform  ──────┘
bootstrap.py: the only place allowed to import every layer
```

- Arrows only point right and down: **a lower layer never knows an upper layer exists**
- `core` imports no other package of this project, and never `PySide6`, `requests`, `ctypes` or `winreg`
- `providers` and `services` never import `PySide6`; `providers.claude` and `providers.codex` never import each other
- `ui` never imports `providers` or `platform.http`: the UI gets data only through ViewModels
- These rules are import-linter contracts in `pyproject.toml`; **breaking one fails the checks**

The effect:

| What you want to change | Only touch | Unaffected |
| --- | --- | --- |
| Claude Desktop moves its folder again | `providers/claude/credentials/desktop_paths.py` | Codex, scheduling, UI |
| The Anthropic API response format changes | `providers/claude/parse.py` + fixture | Everything else |
| The color threshold moves from 70 to 75 | `core/levels.py` | Everything else (widget and tray change together) |
| Widget look tweaks | `ui/theme.py`, `ui/widget/painter.py` | Data fetching, scheduling |
| Add a service (for example Cursor) | Add `providers/cursor/` + one registration line in `registry.py` | Existing services and UI code |

### 4.3 Extension points (interfaces in `core/interfaces.py`)

```python
class Provider(Protocol):
    id: str  # "claude", "codex"
    display_name: str  # name shown on the widget

    def poll(self) -> Usage: ...  # raises PollError on failure
    def credential_signature(self) -> str: ...
    def source_label(self) -> str | None: ...


class CredentialSource(Protocol):
    name: str  # source code such as "cli", "desktop"

    def read(self) -> Token | None: ...  # returns None on failure, never raises
    def signature(self) -> str: ...


class Transport(Protocol):
    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> Response: ...
    def post(self, url: str, headers: Mapping[str, str], json: Any, timeout: float) -> Response: ...


class Clock(Protocol):
    def now(self) -> datetime: ...  # UTC aware
```

- `ClaudeProvider` takes an ordered list of `CredentialSource`s to try: supporting a new path only means adding a `CredentialSource` to the list
- Everything that needs the time goes through `Clock`; tests use `FakeClock` with a fixed time so countdowns and scheduling are testable
- Every network call goes through `Transport`; tests use `FakeTransport` returning JSON from `tests/fixtures/`

### 4.4 Data flow

```
Scheduler (background thread)
  └─ for each Provider: poll() → success: Usage / failure: PollError
       └─ StateStore.update(ProviderState) → notify subscribers
            └─ ui/bridge.py: turned into a Qt signal (back on the main thread)
                 └─ viewmodel.build(states, settings, clock) → WidgetVM / TrayVM
                      └─ widget / tray redraw from the VM
```

---

## 5. Rules

### 5.1 Security

1. **Tokens never touch disk**: not in logs, files, caches, exception messages or tooltips. The masking filter covers `sk-ant-…`, `Bearer …` and JWTs (`eyJ…`). `diagnose` prints only masked tokens (first 14 + last 4 characters). `tests/fixtures/` must never contain real tokens.
2. **Read only**: never modify any Claude or Codex file.
3. **Never use the refresh token**.
4. Tokens are sent only to `api.anthropic.com` and `chatgpt.com`. The update check connects only to `api.github.com` and sends no token, account or usage data.

### 5.2 Stability

5. Every network request runs on a background thread with a 30-second timeout.
6. Desktop path rules may only live in `desktop_paths.py`.
7. File-read and decryption failures always return `None` and write a debug log entry.
8. **Error isolation**: any exception from a service (including unexpected ones) only affects that service's own `ProviderState`; the Scheduler must catch and log it, must not let the polling thread die, and must not affect other services.
9. **The UI never crashes on data**: `viewmodel` has a display for every missing field (for example `—`); drawing code makes no assumptions about the data.
10. External programs always run with `creationflags=0x08000000` (`CREATE_NO_WINDOW`) and a timeout.
11. Internal times are always UTC-aware `datetime`s, converted to local time only in `viewmodel` / `timefmt`.
12. These APIs are undocumented; parsing must tolerate missing fields.
13. Qt objects are used only on the main thread; background data always arrives through the signals in `ui/bridge.py`.
14. The widget must never steal focus.

### 5.3 Testing strategy

| Layer | What to test | How |
| --- | --- | --- |
| `core` | Level thresholds, countdown formats, period labels | Plain unit tests, coverage target ≥ 95% |
| `providers` | Parsing, scope selection, path scanning, error classification | `FakeTransport` + `tests/fixtures/*.json`; desktop decryption uses fake data encrypted with a key generated in the test; path scanning uses `tmp_path` |
| `services` | Backoff, Retry-After, auth pause and resume, stale, early poll at reset, error isolation, settings migration | `FakeProvider` + `FakeClock`, no real waiting |
| `ui/viewmodel` | The VM for each state (the 8 states of §3.7 artboard 2) | **Golden tests**: fixed ProviderState input compared against the expected VM |
| `ui` windows | Can be created, redraws from a VM, doesn't raise | `pytest-qt`, `QT_QPA_PLATFORM=offscreen` |
| `windows_only` | DPAPI, registry, hotkeys, real desktop tokens | `@pytest.mark.windows`, Windows only; tests that need a signed-in account are also marked `@pytest.mark.live` and skipped by default |

Rules:

- **For every bug, first write a failing test that reproduces it, then fix it**; that test stays forever
- When an API response shows a new shape, save it (anonymized) as a new fixture and add a test
- Coverage threshold: `core` + `providers` + `services` combined ≥ 90%; CI fails below it

### 5.4 Tools and checks

`scripts/check.ps1` runs these in order, and everything must pass before work counts as done:

```powershell
ruff format --check .
ruff check .
pyright
lint-imports
pytest --cov=usage_monitor --cov-fail-under=90
```

- `pre-commit`: runs ruff and gitleaks (secret scanning) before each commit
- CI (GitHub Actions) runs on pushes and PRs in two jobs: the pure-logic tests for `core` / `providers` / `services` / `viewmodel` on `ubuntu-latest` (starts and runs faster), and the `windows_only` and pytest-qt tests on `windows-latest`
- pyright: strict mode for `core`, `providers`, `services`; basic for `ui`

### 5.5 Workflow for Claude Code

1. **One feature or one fix at a time**; finish it and pass the checks before starting the next
2. Before starting, say which files you'll change; **don't touch files outside that feature's scope**
3. When changing shared interfaces such as `core/models.py` or `core/interfaces.py`, update every implementation and test at the same time and note it in `CHANGELOG.md`
4. **Never change a test's expected values just to make it pass**, unless the behavior change is intentional; in that case, say so explicitly in your report
5. Wrap experimental features in a feature flag in the settings file, off by default
6. Write important decisions as `docs/decisions/NNNN-title.md` in English (context, decision, reasons, alternatives), for example `0001-adopt-v1-ui.md`, `0002-use-pyside6.md`
7. Update `CHANGELOG.md` (in English) after each feature; versions follow SemVer and live in `src/usage_monitor/__init__.py`
8. Always run `scripts/check.ps1` before finishing and include a summary of the result in your report
9. When the spec is unclear, ask the maintainer instead of assuming; once decided, write it straight into the relevant section
10. When README.md changes, update README.zh-TW.md to match

---

## 6. Feature overview

Progress and per-version details are in `CHANGELOG.md`.

| Stage | Content | Version |
| --- | --- | --- |
| 0 Tooling and skeleton | pyproject, ruff / pyright / import-linter, `check.ps1`, CI, ADRs 0001–0003 | v0.0.1 |
| 1 Claude core | CLI + desktop tokens (including the new `Claude-Data` path and OSCrypt v10 decryption), usage API, Messages fallback | v0.1.0 |
| 2 Diagnostics | `python -m usage_monitor.diagnose`: walks through token sources, decryption and API results step by step (tokens always masked) | v0.2.0 |
| 3 Services | Log masking, settings (schema / migration / atomic writes), independent scheduling and backoff per service | v0.3.0 |
| 4 Tray + widget | The design v1 floating widget, tray, hover card, drag snapping, shortcut, auto-hide in full screen | v0.4.0 |
| 5 Codex | Codex usage; windows classified and labeled by `limit_window_seconds` | v0.5.0 |
| 6 Settings window | General / Advanced / About, applied immediately | v0.6.0 |
| 6.5 Internationalization | Traditional Chinese + English, follows Windows by default; ADR 0004 | v0.7.0 |
| 7 CLI token refresh | Optional, off by default; lets `claude` refresh an expired CLI token | v0.8.0 |
| 8 Packaging and releases | PyInstaller build, GitHub Release created automatically from a pushed tag, update check | v0.9.0–v0.10.0 |
| 9 Taskbar embedding | Not done (ADR 0005) | — |
| 10 App icon and licenses | AppUserModelID + `assets/app.ico`, `THIRD_PARTY_LICENSES.txt`, disclaimer | v0.11.0 |
| 11 Public release | English docs, the repo made public with a clean history | v1.0.0 |

### Possible future work

None.

---

## 7. References

- Change log: `CHANGELOG.md` (what each version did and which behavior changed)
- Architecture decisions: `docs/decisions/`
- UI designs: `docs/design/v1-*.png`
- Algorithm reference: `docs/algorithms.md`
