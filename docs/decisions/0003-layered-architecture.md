# 0003 Layered architecture

- Status: accepted
- Date: 2026-10-29

## Context

The app depends on several undocumented things that can change at any time: where Claude Desktop keeps its data, and the format of the Anthropic and ChatGPT usage APIs. Any one of these changes should touch only one place, without breaking other services or the UI.

## Decision

Four layers, with dependencies pointing only downward:

```
ui ──▶ services ──▶ providers ──▶ core
              ╲          │         ▲
               ╲──▶  platform ─────┘
```

- `core`: pure logic, no I/O, never imports Qt / requests / ctypes / winreg
- `providers`: one folder per service; services never import each other
- `platform`: all Windows-specific ctypes / winreg code
- `services`: scheduling, state, settings; never imports Qt
- `ui`: reads only ViewModels, never touches providers or HTTP directly
- `bootstrap.py`: the composition root, the only module allowed to import everything

Layers talk through the Protocols in `core/interfaces.py` (`Provider`, `CredentialSource`, `Transport`, `Clock`).

These rules are import-linter contracts in `pyproject.toml`; breaking one makes `lint-imports` fail, and CI blocks it.

## Reasons

- A change to a path, an API format or a color threshold touches only one file (see the table in CLAUDE.md §4.2)
- `core`, `providers` and `services` don't depend on Windows or Qt, so they test quickly on Linux CI
- With `FakeTransport` and `FakeClock`, network and time logic is testable deterministically, without real waiting
- Adding a service only means adding `providers/<name>/` and registering it, without touching existing code

## Alternatives

- Splitting files by size with no layer rules: faster at first, but the rules live only in people's heads and things slowly tangle
- Plugins loaded dynamically via entry points: more flexible, but unnecessary for a handful of built-in services
