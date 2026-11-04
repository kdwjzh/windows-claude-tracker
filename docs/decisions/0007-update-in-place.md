# 0007 Download and install updates in place (keep the single portable exe)

- Status: accepted
- Date: 2026-11-04 (accepted 2026-11-05)

## Context

Updating takes several manual steps today: quit the app, open the Release page, download the new exe, put it where the old one was, start it, and delete the old file. ROADMAP item 8 asked to make this simpler.

ROADMAP item 13 (switching to `--onedir` + an installer) would also have helped, but the maintainer decided on 2026-11-04 to keep the single portable exe: many people don't want a small tool installed into a fixed folder such as `%LOCALAPPDATA%\Programs\`. So the update has to work wherever the user put the exe.

CLAUDE.md §1 listed "no automatic download and install of new versions" as a non-goal, and §5.1 rule 4 said the update check only connects to `api.github.com`. This ADR replaces both.

## Decision

- When a newer release exists, Settings → About offers an "Update now" button. **Nothing is downloaded until the user presses it**; the automatic check still only checks and reminds. The tray menu's "New version vX.Y.Z →" item and the new-version notification open that About page (instead of the Release page), so the user sees the button and the release link before deciding (maintainer's choice, 2026-11-04)
- Not behind a settings flag (maintainer's choice, 2026-11-04): it only runs when the user presses the button
- On press, the app:
  1. downloads `ClaudeUsageTracker-vX.Y.Z.exe` and `SHA256SUMS.txt` from that release's assets, into the folder of the running exe (a temporary name first)
  2. checks the exe's SHA-256 against `SHA256SUMS.txt` before writing anything; on a mismatch it writes nothing and reports the failure
  3. writes it under a temporary name, renames it to `ClaudeUsageTracker-vX.Y.Z.exe`, starts it with the old exe's path as an argument, and quits
- The new version waits a few seconds for the old one to exit (the single-instance mutex), deletes the old exe (only that exact file, and only when it sits in the same folder and looks like this app's exe), and carries on. "Start with Windows" already follows the running exe at start (ROADMAP item 1, `autostart.sync_command`); settings and usage history live in `%APPDATA%` and are untouched
- No batch file: the new file has a different name (the version is in it), so the running exe is never overwritten
- Download only from this repo's releases over https, with no token, account or usage data. The asset URLs must start with `https://github.com/kdwjzh/windows-claude-tracker/releases/download/`; the download follows GitHub's redirects by hand and only to `github.com` and `*.githubusercontent.com` (the shared HTTP transport itself still never follows redirects)
- Fallback to the old behavior (open the Release page) when: running from source (`python -m usage_monitor`), the exe's folder isn't writable, the release has no matching assets, or the download or check fails

## Reasons

- One click instead of six steps, and the exe stays where the user put it
- The version-in-the-name scheme plus `sync_command` already solve the hard parts (no overwriting a running file, autostart pointing at the new exe), so the new code is small
- Files the app downloads itself get no Mark of the Web, so SmartScreen usually doesn't prompt again for the new exe

## Limits

- The SHA-256 check catches broken or incomplete downloads, not a compromised repository: `SHA256SUMS.txt` comes from the same release. Protecting against that needs code signing (ROADMAP item 9, deferred)
- Antivirus software may still scan or hold the new exe
- The `--onefile` start-up cost (unpacking about 50 MB on each start) stays; ROADMAP item 13 is not done

## Alternatives

- `--onedir` + an Inno Setup installer, updating by running the new installer: fast start and an uninstall entry, but it installs into a fixed folder, which the maintainer rejected
- winget (`winget upgrade`): winget also puts the exe in its own fixed folder and only suits people who use the command line; it can be added later as an extra channel
- Replace the exe with a helper batch file after quitting: needed only when the file name stays the same; with versioned names it adds a moving part for nothing
- Download automatically in the background: saves a click but takes bandwidth and disk without asking, and surprises people; the check stays "remind only"
