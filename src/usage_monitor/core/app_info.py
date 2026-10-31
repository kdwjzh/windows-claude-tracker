"""程式名稱與 GitHub repo 位置（CLAUDE.md §3.9）。repo 改名或搬家時只改這裡。"""

from __future__ import annotations

PRODUCT_NAME = "Claude Usage Tracker"
APP_USER_MODEL_ID = "kdwjzh.WindowsClaudeTracker"
"""Windows 工作列用來分組與找圖示的 ID：不設的話 pythonw 執行時會被當成 Python。"""
REPO_OWNER = "kdwjzh"
REPO_NAME = "windows-claude-tracker"

REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
RELEASES_URL = f"{REPO_URL}/releases"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
