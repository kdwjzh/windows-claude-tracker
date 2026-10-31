# 0002 Use PySide6

- Status: accepted
- Date: 2026-10-25 (confirmed 2026-10-29)

## Context

The first implementation guide used pystray (tray) + tkinter (small window). The main UI later became a floating always-on-top widget, which needs rounded translucent corners, no frame, dragging and snapping, multiple monitors and DPI scaling, a hover card, a context menu, and dark/light themes.

## Decision

Build the whole UI with PySide6 (Qt 6): `QWidget` for the widget and `QSystemTrayIcon` for the tray. pystray and tkinter are no longer used.

## Reasons

- Qt supports all of the above natively; tkinter struggles with rounded translucent windows and DPI scaling
- The widget and tray share one event loop, instead of managing two threading models for tkinter + pystray
- Background poll results go back to the main thread through Qt signals, which makes the thread-safety boundary clear (CLAUDE.md §5.2 rule 13)
- The official LGPL license allows packaging and distribution

## Costs

- The packaged exe is about 60–80 MB; PyInstaller excludes unneeded modules such as QtWebEngine, QtQml and Qt3D to keep it smaller

## Alternatives

- pystray + tkinter: small, but can't meet the requirements above well
- wxPython: tray and window can share a loop, but translucent rounded windows and DPI support are weaker, and the community is smaller
- Native Win32 (ctypes): smallest, but far too much work
