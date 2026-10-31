# 0005 No taskbar embedding

- Status: accepted
- Date: 2026-10-31

## Context

CLAUDE.md originally listed "real taskbar embedding" as the last, experimental stage (stage 9): find `Shell_TrayWnd` and `TrayNotifyWnd`, use `SetParent` to place the widget in an empty part of the taskbar, and handle Explorer restarts, auto-hide, left/right alignment, taskbars on secondary monitors, and so on.

After stages 0–8c were done, the maintainer used the floating widget for a while (bottom right of the work area, just above the taskbar, draggable and hideable) and looked at what embedding would take: the taskbar is only 48 px tall while the widget is 69 px, so embedding would need a separate compact layout.

## Decision

- Don't embed into the taskbar; remove the old stage 9 from the plan
- Keep the current floating always-on-top widget (§3.7): default position at the bottom right, drag snapping, auto-hide in full screen, toggling with `Ctrl+Alt+U` and the tray
- Don't start on it unless the maintainer brings it up again; if that happens, write a new ADR that supersedes this one

## Reasons

- The floating mode meets the need: the maintainer reviewed it on 2026-10-31 and is happy with it as it is
- The Windows 11 taskbar doesn't support embedding third-party windows: cross-process `SetParent` into the XAML taskbar has no official guarantee, and a Windows update could break it, cover icons, or lose it after an Explorer restart
- High maintenance cost: taskbar position, auto-hide, centered icons, secondary monitors, DPI and Explorer restarts all need handling, each combination needs testing on real machines, and little of it can be automated
- It would also need a separate layout that fits in 48 px, splitting the UI into two looks apart from design v1

## Alternatives

- Embed with `SetParent` as planned and fall back to floating on failure: feasible, but all the maintenance cost above remains, and the only gain is saving a small strip above the taskbar
- Don't embed; just place the top-level window over an empty part of the taskbar: no `SetParent` needed, but clicking the taskbar raises it above topmost windows, which looks like flickering
- Tray icon only (no widget): simplest, but no text or countdowns, and seeing the numbers at a glance is the whole point
