"""Runtime source-version metadata."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPOSITORY_URL = "https://github.com/yuansui1023/G2DTC"


def current_commit_sha(repo_root: Path | None = None) -> str:
    """Return the current short Git commit SHA when it can be determined."""
    override = os.environ.get("G2DTC_COMMIT_SHA", "").strip()
    if override:
        return override[:7]

    root = repo_root or Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"

    sha = result.stdout.strip()
    if result.returncode == 0 and sha:
        return sha
    return "unavailable"


def source_url(commit_sha: str) -> str:
    """Return a repository or commit URL for the supplied version."""
    if commit_sha == "unavailable":
        return REPOSITORY_URL
    return f"{REPOSITORY_URL}/commit/{commit_sha}"
