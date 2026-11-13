# Algorithm reference

How the app gets tokens, decrypts Claude Desktop data, calls the usage APIs and classifies errors. This document matches the current code; when the code changes, update it too. File locations and layer rules are in `CLAUDE.md` §4.

None of these APIs are documented, and their formats can change at any time: parse leniently, and when a new format shows up, save it under `tests/fixtures/` and add a test.

---

## 1. Claude token sources

Code: `providers/claude/provider.py`, `providers/claude/credentials/`

Sources are tried in order, and the **first unexpired** token wins:

| Order | Source (`source`) | Location | Format |
| --- | --- | --- | --- |
| 1 | CLI (`cli`) | `%CLAUDE_CONFIG_DIR%\.credentials.json`, otherwise `%USERPROFILE%\.claude\.credentials.json` | Plain JSON |
| 2 | Desktop (`desktop`) | The folders listed by `desktop_paths.data_dirs()`, in order | OSCrypt v10 encrypted |

- CLI: read `claudeAiOauth.accessToken` (must be non-empty after trimming) and `claudeAiOauth.expiresAt` (Unix milliseconds)
- Expiry: `expiresAt <= now`; a token with no expiry counts as unexpired
- If every source's token has expired, raise `AUTH` / `EXPIRED`; if none is found, raise `AUTH` / `NO_CREDENTIALS`
- If nothing usable is found and the CLI token has merely expired, and the `allow_cli_refresh` setting is on (off by default), run `claude -p . --no-session-persistence` so the CLI refreshes itself, then read it again (`platform/cli_refresh.py`)
- **Never use the refresh token**: OAuth refresh tokens rotate, and using one would sign the official app out

### 1.1 Desktop candidate folders

Defined only in `desktop_paths.py`, in this order:

1. Folders under `%LOCALAPPDATA%\Claude-Data\` matching `^claude_[a-z0-9]{13}$` (new path, **lowercase** `claude_`)
2. `%APPDATA%\Claude\` (old path, regular install; listed even if it doesn't exist, to help diagnostics)
3. Folders under `%LOCALAPPDATA%\Packages\` matching `^Claude_[a-z0-9]{13}$` + `\LocalCache\Roaming\Claude\` (old path, Store install, **uppercase** `Claude_`)

When one level has several folders, the one ending in `pzs8sxrjxfjjc` comes first and the rest are sorted by name. An old folder that only contains a `.user-data-left.<new folder name>` marker file has been migrated to the new path.

Across desktop folders the first unexpired token also wins; if all have expired, the first one found is returned (so the error says "expired" rather than "not found").

## 2. Desktop decryption (Chromium OSCrypt v10)

Code: `platform/oscrypt.py`, `providers/claude/credentials/desktop.py`

Each folder needs `config.json` and `Local State`. Any failing step returns `None` and writes a debug log entry; nothing raises.

1. **AES key**: `Local State` → `os_crypt.encrypted_key` → base64-decode → must start with `b"DPAPI"` → strip those 5 bytes → `CryptUnprotectData` (as the signed-in Windows user) → must be 32 bytes
2. **Ciphertext**: try `oauth:tokenCacheV2`, then `oauth:tokenCache` in `config.json`; **skip empty strings**
3. **Decrypt**: base64-decode → must start with `b"v10"` → then a 12-byte nonce → the rest is "ciphertext + 16-byte tag" → `AESGCM(key).decrypt(nonce, rest, None)`
4. **Plaintext**: a JSON object whose keys look like `<install>:<user>:<base url>:<scope1> <scope2> …` and whose values are `{"token": "...", "expiresAt": <ms>}`

**Scope parsing** (`scopes.entry_scopes`): split the key on spaces; in the first word, everything after the second-to-last colon is the first scope (the base URL itself contains a colon), and each remaining word is another scope.

**Token selection** (`scopes.select_token`): skip empty tokens and malformed entries; the sort key (largest wins) is:

```
(has both user:inference and user:profile, has user:inference, expiresAt (-1 if missing))
```

## 3. Credential signatures

On an auth error the scheduler pauses that service, compares the signature every 60 seconds, and resumes only when it changes.

| Source | Signature |
| --- | --- |
| Claude CLI, Codex | Path + file size + mtime |
| Claude Desktop | SHA-256 of the `oauth:tokenCache*` ciphertext in each candidate folder |

**Don't use the mtime of the desktop `config.json`**: the desktop app rewrites it often, for example to save the window position.

## 4. Claude usage API

Code: `providers/claude/api.py`, `providers/claude/parse.py`

```http
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <token>
anthropic-beta: oauth-2025-04-20
```

- `five_hour` / `seven_day`: `utilization` (**0–100**), `resets_at` (ISO 8601, UTC)
- If either is null or has no `utilization`, look in `limits[]` for the item whose `scope` is null and whose `kind` is `session` (5h) / `weekly_all` (7d); the percentage is `percent`, falling back to `utilization`
- Per-model weekly limits (added 2026-11-13): every `limits[]` item with `kind == "weekly_scoped"` becomes a window in `Usage.scoped`, labeled `scope.model.display_name` and using the same `percent` / `utilization` and `resets_at` fields; items without a name or percentage are skipped. `weekly_scoped_shares[]` entries map `limit_index` (the item's position in `limits[]`) to `allowance_percent_of_weekly`, stored as `Window.share` (for example Fable: at most 50% of the weekly limit). Seen in `tests/fixtures/claude/usage_scoped_2026_11.json` (the model name is anonymized there)
- Neither window present → `TRANSIENT` / `BAD_RESPONSE`; if only one is present, the other is marked "no data" (`available=False`)
- A response that isn't JSON → `TRANSIENT` / `BAD_RESPONSE`
- Format changes (added 2026-11-04): `KNOWN_KEYS`, `KNOWN_BUCKET_KEYS`, `KNOWN_LIMIT_KEYS` and `KNOWN_LIMIT_KINDS` in `parse.py` list the fields seen in the 2026-11 response (`tests/fixtures/claude/usage_full_2026_11.json`). Fields outside them whose value isn't null, and unknown `limits[].kind` values, are logged at debug level (names only, never values). Null fields are ignored: the response carries many null code-named fields that come and go

### 4.1 Messages API fallback

Used only when the usage API returns an "other 4xx" (anything except 401, 403 and 429). **It costs 1 token of quota.**

```http
POST https://api.anthropic.com/v1/messages
Authorization: Bearer <token>
anthropic-version: 2023-06-01
anthropic-beta: oauth-2025-04-20

{"model": "claude-haiku-4-5", "max_tokens": 1, "messages": [{"role": "user", "content": "."}]}
```

Read the response headers (prefix `anthropic-ratelimit-unified-`):

| Header | Meaning |
| --- | --- |
| `5h-utilization`, `7d-utilization` | **0–1**, multiply by 100 |
| `5h-reset`, `7d-reset` | Unix seconds |
| `status` | `rejected` means requests are being blocked |
| `representative-claim` | `five_hour` / `seven_day` |

- Even a 429 is used as long as these headers are present
- 401/403, or none of these headers → classified by status code (§6); a 2xx without the headers raises `UNSUPPORTED`
- When `status == rejected` and both utilizations are 0, set the window named by the claim to 100%

### 4.2 Plan (profile API)

Code: `providers/claude/api.get_profile`, `parse.parse_plan`, `provider._plan_for` (added 2026-11-13)

```http
GET https://api.anthropic.com/api/oauth/profile
Authorization: Bearer <token>
anthropic-beta: oauth-2025-04-20
```

- Read only `organization.organization_type` and `organization.rate_limit_tier`; ignore `account` (email, name) and everything else
- `claude_pro` → "Pro", `claude_max` → "Max" ("Max 5x" / "Max 20x" when `rate_limit_tier` ends in `max_5x` / `max_20x`), `claude_team` → "Team", `claude_enterprise` → "Enterprise", other `claude_xxx` → "Xxx"; missing → `None`
- Cached per token (SHA-256 of the token, memory only): re-read after 24 hours or when the token changes; any failure (HTTP error, not JSON) → `None`, retried after 1 hour, logged at debug level by exception type only; the usage poll is never affected

## 5. Codex usage API

Code: `providers/codex/`

**Credentials**: `%CODEX_HOME%\auth.json`, otherwise `%USERPROFILE%\.codex\auth.json`

- `tokens.access_token` (must be non-empty) and `tokens.account_id` (optional)
- Expiry: when the token is a JWT, read `exp` from the payload (Unix seconds; read only, not verified); expired → `AUTH` / `EXPIRED`
- No file or no token → `AUTH` / `NO_CREDENTIALS`

```http
GET https://chatgpt.com/backend-api/wham/usage
Authorization: Bearer <access_token>
User-Agent: codex-cli
ChatGPT-Account-Id: <account_id>      ← only when present
```

Each of `rate_limit.primary_window` / `secondary_window` has:

| Field | Meaning |
| --- | --- |
| `used_percent` | 0–100 |
| `reset_at` | Unix seconds; when missing, use `reset_after_seconds` added to the fetch time |
| `limit_window_seconds` | Window length |

The top-level `plan_type` (`free`, `plus`, …) becomes `Usage.plan` with its first letter capitalized (added 2026-11-13).

- **`limit_window_seconds >= 86400` decides the long window**, regardless of primary/secondary order; only without a length does it fall back to "primary is short, secondary is long"
- Row labels come from the window length (`core/windows.py`): a day or more → `round(seconds / 86400)` days (604800 → `7d`, 2592000 → `30d`), otherwise `round(seconds / 3600)` hours (18000 → `5h`); `5h` / `7d` when it can't be determined
- Measured: some accounts have only a single 30-day window (`limit_window_seconds = 2592000`) and no 5h window; an unreported period shows an empty bar and 0%
- No `rate_limit`, or neither window present → `TRANSIENT` / `BAD_RESPONSE`
- Format changes (added 2026-11-04): unknown non-null fields at the top level, in `rate_limit` and in each window are logged at debug level (names only), against the 2026-11 response in `tests/fixtures/codex/usage_free_30d_only.json`

## 6. Error classification and scheduling

Code: `core/errors.py`, `raise_for_status` in each `api.py`, `platform/http.py`, `services/scheduler.py`

On failure, `provider.poll()` raises only `PollError(kind, message, reason=…, status=…, retry_after=…)`. `message` is for logs only (in Chinese, and **never contains a token**); the UI shows the `reason` in the current language.

| Situation | `kind` | `reason` | Scheduling |
| --- | --- | --- | --- |
| No token found | `AUTH` | `NO_CREDENTIALS` | Pause; compare the credential signature every 60 seconds and resume only when it changes |
| Token expired | `AUTH` | `EXPIRED` | Same as above |
| HTTP 401/403 | `AUTH` | `REJECTED` | Same as above |
| HTTP 429 | `TRANSIENT` | `RATE_LIMITED` | Exponential backoff |
| HTTP 5xx | `TRANSIENT` | `SERVER` | Exponential backoff |
| Connection timeout | `TRANSIENT` | `TIMEOUT` | Exponential backoff |
| Connection failure | `TRANSIENT` | `NETWORK` | Exponential backoff |
| Other 4xx | `UNSUPPORTED` | `UNSUPPORTED` | Claude falls back to the Messages API |
| Not JSON, no windows at all, unexpected status code | `TRANSIENT` | `BAD_RESPONSE` | Exponential backoff |
| An exception the code didn't anticipate | `TRANSIENT` | `UNEXPECTED` | Exponential backoff, with the full traceback logged |

- **Exponential backoff**: after the n-th failure, wait `min(30 seconds × 2^(n-1), poll interval)`; with `Retry-After`, use the larger value. Reset to zero after a success
- **After a success**: the next poll is "now + poll interval"; if any window resets before then, it moves to `resets_at + 10 seconds`. The minimum delay is 10 seconds
- **Error isolation**: each service has its own schedule and backoff; any exception in one service affects only its own `ProviderState`
- On failure, the last successful data is kept and marked `stale`
- Every network request runs on a background thread with a 30-second timeout
