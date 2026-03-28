"""TypeScript/JavaScript import parser."""
from __future__ import annotations
import re
from pathlib import Path

# Matches: import { X } from './path' or import X from 'path'
_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s*,?\s*)*\s*from\s*|"""
    r"""import\s*\(?\s*)['"]([^'"]+)['"]""",
    re.MULTILINE,
)

# Matches: require('path')
_REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")


def parse_imports(file_path: Path) -> list[str]:
    """Extract import targets from a TypeScript/JavaScript file."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    targets: list[str] = []
    for m in _IMPORT_RE.finditer(content):
        targets.append(m.group(1))
    for m in _REQUIRE_RE.finditer(content):
        targets.append(m.group(1))
    return targets


def resolve_import(source_file: Path, target: str, source_root: Path) -> str | None:
    """Resolve a relative import to a path relative to source_root."""
    if target.startswith("."):
        resolved = (source_file.parent / target).resolve()
        try:
            return str(resolved.relative_to(source_root.resolve()))
        except ValueError:
            return None
    # Absolute / package imports — return as-is for layer classification
    return target
