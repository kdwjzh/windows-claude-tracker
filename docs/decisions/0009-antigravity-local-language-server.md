# 0009 Track Antigravity through its local language server

- Status: accepted
- Date: 2026-11-23

## Context

CLAUDE.md §1 listed Antigravity (Google's AI IDE) as a non-goal. The maintainer now uses it and wants it on the widget. Antigravity has no public usage API. Two ways to read its quota were found:

1. **Google's cloud API** (`cloudcode-pa.googleapis.com`: `retrieveUserQuotaSummary`, `fetchAvailableModels`) with the Google sign-in stored by Antigravity. That sign-in lives in the Windows Credential Manager with a short-lived access token and a refresh token; keeping it working means refreshing it ourselves, with an OAuth client id and secret taken from Antigravity's own binary
2. **The local language server** that Antigravity starts. It writes `~/.gemini/antigravity/daemon/hub_<port>.json` (`pid`, `httpPort`, `httpsPort`, `csrfToken`) and answers Connect-RPC calls on `127.0.0.1` with the header `X-Codeium-Csrf-Token`. `RetrieveUserQuotaSummary` returns the same quota groups as option 1, with the window of each bucket (`5h` / `weekly`); `GetUserStatus` returns the plan (and account details)

In Antigravity 2.34.0 the csrf token is no longer on the language server's command line (it's passed on stdin), so scanning processes for `--csrf_token`, as older write-ups describe, no longer works; the hub file still has it.

## Decision

- Use option 2 only: read the newest `hub_*.json` whose `pid` is still running, call `RetrieveUserQuotaSummary` (and `GetUserStatus` for the plan, reading only `userTier.id`) on `http://127.0.0.1:<httpPort>`
- Never touch Antigravity's Google sign-in, and never send the csrf token anywhere but `127.0.0.1` (enforced in `platform/http.py`, which also bypasses any proxy for loopback requests)
- When Antigravity isn't running, show 「未開啟」/ "Not running" without a notification or red dot (`ErrReason.NOT_RUNNING`, polling paused until the hub files change)
- Widget: the short and long rows are the highest 5h and weekly usage across groups. When there is no 5h bucket and exactly two groups (the free / Google AI Plus "Starter" quota), the two rows show the groups instead, labeled 「Gem」 and 「C/G」 (Claude and GPT) (maintainer's choice, 2026-11-23). Every group's buckets go into `Usage.scoped` for the hover card. Title color blue (maintainer's choice)

## Reasons

- Option 1 needs the refresh token, which this app never uses (CLAUDE.md §5.1 rule 3): rotating it could sign Antigravity out. Taking a client secret out of another program's binary is also not acceptable
- Option 2 never leaves the computer, needs no Google token, and the quota summary carries no account details
- The cost: Antigravity must be running, and these internal RPCs can change without notice

## Alternatives

- Scanning process command lines for `--csrf_token`: doesn't work from 2.34.0 on
- Calling the language server from inside Antigravity's window (devtools protocol) for versions whose hub file has no token: too intrusive; if that happens the column says "Not running"
- One widget column per group: makes the widget much wider and turns one service into two
