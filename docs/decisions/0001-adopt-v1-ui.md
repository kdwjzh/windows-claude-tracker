# 0001 Adopt the v1 UI

- Status: accepted
- Date: 2026-10-29

## Context

The UI designs explored three directions:

1. v1: one column per service; each row is a period label + a 10-segment bar + "percentage · reset countdown"
2. v2: double rings
3. v3: big numbers

The widget sits permanently just above the taskbar, so it has to be small and show at a glance "is it nearly full, and when does it reset".

## Decision

Adopt v1. The designs are stored in `docs/design/v1-*.png`, the exact values are in CLAUDE.md §3.7, and the implementation keeps them together in `ui/theme.py`.

## Reasons

- Segmented bars stay readable even at 16–24 px tall, and the same visual language works for the tray icon
- The text always shows the percentage, so meaning never depends on color alone
- The column layout extends naturally to a second service (Codex), and the long-period label can be `7d` or `30d`

## Alternatives

- v2 double rings: attractive, but needs more area and takes too much space above the taskbar
- v3 big numbers: shows only one number clearly at a time, so 5h and the long period can't be seen together
