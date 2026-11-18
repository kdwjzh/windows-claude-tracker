# Security policy

This app reads the sign-in tokens of Claude Code, Claude Desktop and Codex on your computer, so security problems matter. Thank you for reporting them responsibly.

## Reporting a problem

**Please don't open a public issue.** Report privately through GitHub instead:

1. Go to the [Security tab](https://github.com/kdwjzh/windows-claude-tracker/security) of this repository
2. Click **Report a vulnerability** and describe the problem and how to reproduce it

Never include a real token in a report; a masked one (the diagnostics tool prints the first 14 and last 4 characters) is enough.

You should get a first reply within a week. Once a fix is released, the report can be published with credit to you if you'd like.

## What counts

For example:

- A token, or part of one beyond the masked form, written to the log, the settings file, diagnostics output, a tooltip or anywhere else on disk
- A token sent anywhere other than `api.anthropic.com` (Claude) or `chatgpt.com` (Codex)
- The update check sending anything to `api.github.com` beyond the request for the latest release
- "Update now" downloading from anywhere other than this repository's release assets on `github.com` and the `*.githubusercontent.com` hosts it redirects to, or running a file whose SHA-256 doesn't match the release's `SHA256SUMS.txt`
- Account details from the Claude profile API (anything beyond the plan) being logged or stored
- The app modifying Claude or Codex files, or using a refresh token

## Supported versions

Only the latest release gets security fixes. Settings → About shows your version and checks for updates.
