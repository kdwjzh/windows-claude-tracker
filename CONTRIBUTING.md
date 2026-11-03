# Contributing

Thanks for your interest! Bug reports, ideas and pull requests are all welcome.

## Reporting bugs and ideas

Use the [issue forms](https://github.com/kdwjzh/windows-claude-tracker/issues/new/choose). For bugs, the diagnostics output (Settings → Advanced → "Run diagnostics") helps most; it never contains full tokens. Security problems go through [SECURITY.md](SECURITY.md), not a public issue.

## Setting up

Windows 10/11 and Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\pre-commit.exe install
.\.venv\Scripts\pythonw.exe -m usage_monitor
```

Only one copy of the app runs at a time: quit any installed version first (tray right-click → "Quit").

## Before you open a pull request

- **Run the checks**; everything must pass:

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\check.ps1
  ```

  This runs ruff (lint and format), pyright, import-linter and pytest with a 90% coverage threshold.
- **Keep the layers apart**: `core` → `providers` / `platform` → `services` → `ui`, and a lower layer never imports a higher one. import-linter enforces this. A new service goes in its own `providers/<name>/` folder plus one line in `providers/registry.py`.
- **Bug fixes start with a failing test** that reproduces the bug; the test stays.
- **Never commit tokens**, personal paths or account details, including in test fixtures. The pre-commit hook runs gitleaks.
- **UI text goes through `core/i18n.py`** in both Traditional Chinese and English.
- One change per pull request, with a line in `CHANGELOG.md` under `[Unreleased]`.

The full specs, rules and architecture are in [CLAUDE.md](CLAUDE.md), and past decisions in [docs/decisions/](docs/decisions/). Code comments and log messages are in Traditional Chinese; documentation is in English.

By contributing, you agree that your contribution is released under the [MIT license](LICENSE).
