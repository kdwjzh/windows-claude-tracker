# Claude Usage Tracker

**English** | [繁體中文](README.zh-TW.md)

A small always-on-top widget that sits just above the Windows taskbar and shows your **Claude** (Pro/Max subscription) and **Codex** (ChatGPT account) usage percentages and reset countdowns.

> This is an unofficial tool, not affiliated with Anthropic or OpenAI. Claude, ChatGPT and Codex are trademarks of their respective owners.

```
┃ Claude                          │ Codex
┃ 5h  ■■■■□□□□□□  42% · 2h 13m    │ 5h  □□□□□□□□□□  0%
┃ 7d  ■■□□□□□□□□  18% · 4d 3h     │ 30d ■■■□□□□□□□  32% · 29d
```

- Green below 70%, yellow 70–89%, red 90% and above; hover over the widget to see the exact reset time
- Tray icon (check it when the widget is hidden), auto-hide in full screen, `Ctrl+Alt+U` to show/hide
- Supports the **Microsoft Store version of Claude Desktop** (data in `%LOCALAPPDATA%\Claude-Data\`)
- English and Traditional Chinese; follows your Windows display language by default and can be switched in Settings

## Install

1. Download the latest release from [Releases](https://github.com/kdwjzh/windows-claude-tracker/releases):
   - `ClaudeUsageTracker-vX.Y.Z.exe` (the app)
   - `diagnose-vX.Y.Z.exe` (optional diagnostics tool; put it in the **same folder** as the app so "Run diagnostics" can find it)
   - Check the files against `SHA256SUMS.txt` if you like: `Get-FileHash .\ClaudeUsageTracker-vX.Y.Z.exe`
2. Put the exe in a permanent folder (for example `%LOCALAPPDATA%\Programs\ClaudeUsageTracker\`) and double-click it
3. The widget appears above the right end of the taskbar and an icon appears in the tray. Right-click → "Settings…" to turn on "Start with Windows"

Requirements: Windows 10/11 (64-bit). **Run it as a normal user**, not as administrator: Claude Desktop encrypts its token with Windows DPAPI, which only the signed-in user can decrypt.

On first run, Windows SmartScreen may say "Windows protected your PC" (the exe is not code-signed): click "More info" → "Run anyway".

### Updating

When a new version is out, a blue dot appears at the bottom right of the tray icon, the tray menu gets a "New version vX.Y.Z →" item at the top, and you get one notification (also shown in Settings → About). The app never downloads or installs anything itself; clicking only opens the Release page.

Quit the old version (tray right-click → "Quit") → download the new exe → run it. Your settings carry over.
If "Start with Windows" is on, turn it off and on again in the new version's Settings so it points to the new exe.

### Uninstall

1. Settings → turn off "Start with Windows", then quit the app
2. Delete the exe
3. Delete settings and logs: `%APPDATA%\MyUsageMonitor\`

## Where the data comes from

| Service | Token source | Usage API |
| --- | --- | --- |
| Claude | ① Claude Code CLI: `%USERPROFILE%\.claude\.credentials.json` (only if not expired)<br>② Claude Desktop: `%LOCALAPPDATA%\Claude-Data\claude_*`, `%APPDATA%\Claude\`, the old Store path | `api.anthropic.com/api/oauth/usage` |
| Codex | `%USERPROFILE%\.codex\auth.json` (or `%CODEX_HOME%`) | `chatgpt.com/backend-api/wham/usage` |

Privacy and security:

- These files are only **read**, never modified, and the refresh token is never used (so the official apps never get signed out)
- Tokens are sent only to `api.anthropic.com` and `chatgpt.com`, and never written to logs, settings or anywhere else
- Usage is checked every 5 minutes by default. These usage APIs are undocumented, so a format change may temporarily stop the numbers from showing

## Settings file

Location: `%APPDATA%\MyUsageMonitor\settings.json`. Prefer the Settings window (changes apply immediately); edit the file by hand only with the app closed. If the file is broken, the app starts with defaults and saves the original as `settings.json.broken`.

| Field | Default | Description |
| --- | --- | --- |
| `interval_minutes` | `5` | Refresh interval in minutes, 1–1440 |
| `providers` | `["claude"]` | Services to show: `"claude"`, `"codex"` |
| `allow_cli_refresh` | `false` | When the Claude Code CLI token has expired and no other sign-in works, run `claude -p . --no-session-persistence` so the CLI refreshes itself (uses a little quota, at most once every 30 minutes, needs Claude Code ≥ 2.0.63) |
| `language` | `"system"` | `"system"` (follow Windows), `"zh-TW"`, `"en"` |
| `widget.visible` | `true` | Show the widget |
| `widget.locked` | `false` | Lock the position (no dragging) |
| `widget.opacity` | `0.9` | Background opacity, 0.3–1.0 |
| `widget.screen` / `widget.pos` | `null` | Screen and relative position of the widget; `null` means the default (bottom right of the work area) |
| `widget.hide_on_fullscreen` | `true` | Hide automatically while a video or game is full screen |
| `widget.hotkey` | `"Ctrl+Alt+U"` | Show/hide shortcut (modifiers + A–Z / 0–9 / F1–F24) |
| `widget.theme` | `"system"` | `"system"` (follow Windows), `"dark"`, `"light"` |
| `update_check.enabled` | `true` | Check GitHub for the latest version 30 seconds after start and every 24 hours (connects only to `api.github.com` and sends no personal data); when off, only "Check for updates" in About checks |
| `update_check.skipped_version` | `null` | Version saved by "Skip this version"; you won't be reminded about it again |
| `update_check.last_checked_at` / `notified_version` | `null` | Maintained by the app: time of the last successful check, and the version already notified |

## Troubleshooting

Run diagnostics first: Settings → Advanced → "Run diagnostics", or run `diagnose-vX.Y.Z.exe` directly. It goes through each token source, the decryption and the API response step by step, and the final summary (結論) says where it got stuck. **The output never contains full tokens, so you can paste it into an issue.** The diagnostics output is in Traditional Chinese for now.

| Symptom | Likely cause and fix |
| --- | --- |
| "Not signed in" next to the service name | No token found: open Claude Desktop (or the `claude` CLI) and sign in; it recovers within a minute |
| "Expired" | Open Claude Desktop so it refreshes the sign-in; if you only use the CLI, turn on "Allow CLI token refresh" |
| Diagnostics says "DPAPI 解金鑰失敗" (DPAPI key decryption failed) | The app isn't running as the user signed in to Windows (for example, run as administrator); start it with a normal double-click |
| Numbers are dimmed and "12 min ago" appears next to the service name | The network or server is temporarily unavailable; you're seeing the last numbers and they update once it recovers. On a corporate network, make sure `api.anthropic.com` is reachable |
| Codex 5h shows 0% | Your plan only has a long window (for example 30 days), with no 5-hour window |
| The shortcut does nothing and Settings shows red text | Another app has taken it; pick a different one in Settings |
| The widget is gone | Left-click the tray icon or press `Ctrl+Alt+U`; if it ended up off screen, tray right-click → "Reset position" |

Log: `%APPDATA%\MyUsageMonitor\monitor.log` (right-click → "Open log"). All tokens are masked in the log.

## Development

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\pre-commit.exe install
.\.venv\Scripts\pythonw.exe -m usage_monitor          # run
powershell -ExecutionPolicy Bypass -File scripts\check.ps1   # must pass before finishing any change
powershell -ExecutionPolicy Bypass -File scripts\build.ps1   # build into dist\
```

Architecture, rules and specs are in [CLAUDE.md](CLAUDE.md), key decisions in [docs/decisions/](docs/decisions/), and the change log in [CHANGELOG.md](CHANGELOG.md). Code comments and log messages are in Traditional Chinese.

### Releasing a new version

1. Update `__version__` in `src/usage_monitor/__init__.py` (SemVer, for example `1.2.0`)
2. Add a section for that version to `CHANGELOG.md`
3. Commit and push
4. Tag and push the tag:

   ```powershell
   git tag v1.2.0
   git push --tags
   ```

GitHub Actions runs all checks, builds, and creates the Release (with the two exes, `THIRD_PARTY_LICENSES.txt` and `SHA256SUMS.txt`; the notes come from CHANGELOG). Tags containing `-` (for example `v1.2.0-beta.1`) are marked as pre-releases.

To try a local build first: `scripts\build.ps1` produces `dist\ClaudeUsageTracker.exe`, `dist\diagnose.exe` and `dist\THIRD_PARTY_LICENSES.txt`. The app icon `assets\app.ico` is a designed file, not generated by code; to change the icon, replace that file (it must contain all 9 sizes from 16 to 256 px).

## License

Released under the [MIT](LICENSE) license. The licenses of the third-party components bundled in the exe (PySide6/Qt under LGPL-3.0, plus requests, cryptography, truststore and others) are listed in `THIRD_PARTY_LICENSES.txt` attached to every Release.

This is an unofficial tool, not affiliated with Anthropic or OpenAI. Claude, ChatGPT and Codex are trademarks of their respective owners.
