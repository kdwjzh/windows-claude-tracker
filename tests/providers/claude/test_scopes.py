from __future__ import annotations

import pytest

from usage_monitor.providers.claude.credentials.scopes import Picked, entry_scopes, select_token

BASE = "inst:user:https://api.anthropic.com"


@pytest.mark.parametrize(
    ("key", "scopes"),
    [
        (f"{BASE}:user:inference user:profile", ["user:inference", "user:profile"]),
        (f"{BASE}:user:inference", ["user:inference"]),
        (
            f"{BASE}:user:profile user:inference user:sessions:claude_code",
            ["user:profile", "user:inference", "user:sessions:claude_code"],
        ),
        ("a:b", []),
        ("nocolon extra", ["extra"]),
        ("", []),
        ("   ", []),
    ],
)
def test_entry_scopes(key: str, scopes: list[str]) -> None:
    assert entry_scopes(key) == scopes


def test_prefers_inference_and_profile_over_newer_inference_only() -> None:
    picked = select_token(
        {
            f"{BASE}:user:inference": {"token": "inf-only", "expiresAt": 9_000},
            f"{BASE}:user:profile user:inference": {"token": "both", "expiresAt": 8_000},
        }
    )
    assert picked == Picked("both", 8_000)


def test_order_of_entries_does_not_matter() -> None:
    picked = select_token(
        {
            f"{BASE}:user:profile user:inference": {"token": "both", "expiresAt": 8_000},
            f"{BASE}:user:inference": {"token": "inf-only", "expiresAt": 9_000},
        }
    )
    assert picked == Picked("both", 8_000)


def test_prefers_inference_over_other_scopes() -> None:
    picked = select_token(
        {
            f"{BASE}:user:profile": {"token": "profile", "expiresAt": 9_000},
            f"{BASE}:user:inference": {"token": "inf", "expiresAt": 1},
        }
    )
    assert picked is not None and picked.token == "inf"


def test_same_rank_prefers_later_expiry() -> None:
    picked = select_token(
        {
            f"{BASE}:user:inference user:profile": {"token": "old", "expiresAt": 1},
            f"x:{BASE}:user:inference user:profile": {"token": "new", "expiresAt": 2},
        }
    )
    assert picked is not None and picked.token == "new"


def test_missing_expiry_ranks_lowest() -> None:
    picked = select_token(
        {
            f"{BASE}:user:inference": {"token": "none"},
            f"y:{BASE}:user:inference": {"token": "dated", "expiresAt": 5},
        }
    )
    assert picked == Picked("dated", 5)


@pytest.mark.parametrize(
    "entries",
    [
        {},
        {f"{BASE}:user:inference": {"token": ""}},
        {f"{BASE}:user:inference": {"token": "   "}},
        {f"{BASE}:user:inference": {"token": None}},
        {f"{BASE}:user:inference": "not a dict"},
        {f"{BASE}:user:inference": {"expiresAt": 5}},
    ],
)
def test_ignores_empty_or_malformed(entries: dict[str, object]) -> None:
    assert select_token(entries) is None


def test_strips_token_whitespace() -> None:
    picked = select_token({f"{BASE}:user:inference": {"token": " tok \n"}})
    assert picked == Picked("tok", None)
