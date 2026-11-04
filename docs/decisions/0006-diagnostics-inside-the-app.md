# 0006 Diagnostics inside the app, one exe per release

- Status: accepted
- Date: 2026-11-04

## Context

Since stage 8, every release shipped two executables: `ClaudeUsageTracker-vX.Y.Z.exe` (the app, built with `--noconsole`) and `diagnose-vX.Y.Z.exe` (the diagnostics tool, built with a console and without Qt). Settings → Advanced → "Run diagnostics" and the sign-in error notification looked for the diagnostics exe in the app's folder and opened it in a new console window.

Many users only downloaded the app. Then "Run diagnostics" opened a command prompt with an error about a missing file, which most people couldn't make sense of, and the bug reports came without the output we needed. Because the app is built with `--noconsole`, it can't simply print the report itself.

## Decision

- Run diagnostics inside the app: a diagnostics window (`ui/diagnose_window.py`) shows the full report in a monospace, scrollable, selectable text box with "Copy" and "Run again" buttons
- Keep the checks in `usage_monitor.diagnose` unchanged; add `report_text(lang)` that returns the report instead of printing it. `ui` and `diagnose` sit in the same import-linter layer and may not import each other, so `bootstrap.py` injects `diagnose.report_text` into the `Controller`
- The report runs on a background thread (it reads files, decrypts and calls the API) and returns to the main thread through a Qt signal; an exception shows a one-line error and is logged, never crashing the app
- Releases ship one exe; `build.ps1` and `release.yml` no longer build or upload `diagnose.exe`, and `platform/launch.py` no longer looks for it
- `python -m usage_monitor.diagnose` (with `--lang`, `--poll`, `--no-api`, `--debug`) stays for development and advanced users in a terminal

## Reasons

- "Run diagnostics" always works: there is nothing extra to download or place in the right folder
- "Copy" gives users the whole report in one click, which is what the bug report form asks for
- The report follows the UI language automatically, with no command-line flag to pass
- The check logic stays in one place, used by both the window and the terminal command
- One fewer exe to build, sign, hash and explain in the README

## Alternatives

- Keep two exes and improve the error message when `diagnose.exe` is missing: still asks users to download a second file, and the report still has to be copied out of a console window
- Add a `--diagnose` flag to the main exe that opens a console (`AllocConsole`) and prints the report: a `--noconsole` build has no console to inherit, so the output would need a newly allocated console that closes with the process, copying from it is awkward, and Windows may flag a GUI app that spawns consoles
- Bundle `diagnose.exe` inside the main exe and extract it at run time: adds size and antivirus false positives for no benefit over running the same Python code in-process
