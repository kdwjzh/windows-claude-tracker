# 0008 Show per-model weekly limits in the hover card and tooltip

- Status: accepted
- Date: 2026-11-13

## Context

CLAUDE.md §1 listed per-model weekly limits (`weekly_scoped`) as a non-goal on 2026-10-31, when no account in use had one. By November 2026 the Claude usage API reports one for the Fable model (`limits[]` item with `kind: "weekly_scoped"`, `scope.model.display_name: "Fable"`), and Claude's own settings page shows it next to the 5-hour and weekly limits. Fable can run out (94% on 2026-11-13) while the weekly limit is still at 74%, so not showing it hides the limit the user is about to hit.

## Decision

- Parse every `weekly_scoped` item into `Usage.scoped`, named by `scope.model.display_name`, so future models appear without code changes
- Show them only in the hover card (one line each) and the tray tooltip (only when everything still fits in 127 characters); the widget keeps two rows per column (maintainer's choice, 2026-11-13)
- The tray icon, the Usage page and `history.db` stay limited to the short and long periods for now (maintainer's choice, 2026-11-13)
- "Reset" vouchers shown on Claude's settings page are not part of this: they aren't in the usage API response

## Reasons

- The data is already in the response the app fetches every poll: no extra request, no new endpoint
- Hover card and tooltip have room for a variable number of lines; the widget's fixed two-row layout (design v1) doesn't

## Alternatives

- A third widget row for Claude: rejected, it makes the widget taller and leaves an empty row in the Codex column
- Only showing Fable by name: rejected, the next model would need a code change
