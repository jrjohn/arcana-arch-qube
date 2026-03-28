"""Extract changed files from git diff for PR mode scanning."""
from __future__ import annotations
import subprocess
from pathlib import Path


def get_changed_files(
    source_root: Path,
    base_branch: str = "main",
    extensions: list[str] | None = None,
) -> list[Path]:
    """Get list of changed files relative to base branch."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
            capture_output=True, text=True, cwd=source_root,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        files = []
        for line in result.stdout.strip().splitlines():
            path = source_root / line
            if not path.exists():
                continue
            if extensions and path.suffix not in extensions:
                continue
            files.append(path)
        return files
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def get_diff_content(
    source_root: Path,
    base_branch: str = "main",
) -> str:
    """Get full unified diff content."""
    try:
        result = subprocess.run(
            ["git", "diff", f"{base_branch}...HEAD"],
            capture_output=True, text=True, cwd=source_root,
            timeout=30,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
