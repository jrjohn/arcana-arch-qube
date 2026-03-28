"""Java/Kotlin import parser."""
from __future__ import annotations
import re
from pathlib import Path

_JAVA_IMPORT_RE = re.compile(r"^import\s+(?:static\s+)?([a-zA-Z0-9_.]+);", re.MULTILINE)
_KOTLIN_IMPORT_RE = re.compile(r"^import\s+([a-zA-Z0-9_.]+)", re.MULTILINE)


def parse_imports(file_path: Path) -> list[str]:
    """Extract import targets from a Java or Kotlin file."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    suffix = file_path.suffix.lower()
    pattern = _KOTLIN_IMPORT_RE if suffix == ".kt" else _JAVA_IMPORT_RE

    return [m.group(1) for m in pattern.finditer(content)]


def import_to_layer_path(import_target: str) -> str:
    """Convert Java package import to directory-style path for layer classification.

    e.g. 'com.arcana.cloud.dao.impl.UserDaoImpl' -> 'dao/impl'
    """
    parts = import_target.split(".")
    # Find the layer-relevant segment after the base package
    # Common base: com.arcana.cloud.{layer}.{sub}
    known_layers = {"controller", "service", "repository", "dao", "domain", "data", "presentation"}
    for i, part in enumerate(parts):
        if part.lower() in known_layers:
            # Return from layer onward (e.g. "service/impl")
            remaining = parts[i:]
            # Last element is class name, skip it
            if len(remaining) > 1:
                return "/".join(remaining[:-1])
            return remaining[0]
    return "/".join(parts)
