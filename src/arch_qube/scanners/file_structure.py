"""Check file structure conventions (impl/ colocation, naming)."""
from __future__ import annotations
from pathlib import Path
import re

from arch_qube.profiles.loader import FrameworkProfile
from arch_qube.rules.models import Violation, CheckType


def check_impl_colocation(
    source_root: Path,
    profile: FrameworkProfile,
) -> list[Violation]:
    """Check that impl/ directories are subdirectories of their interface dir (Rule #2)."""
    violations: list[Violation] = []

    for ext in profile.file_extensions:
        for fpath in source_root.rglob(f"*{ext}"):
            rel = str(fpath.relative_to(source_root))
            fname = fpath.stem.lower()

            # Check if this is an impl file outside an impl/ directory
            if _is_impl_name(fname) and "impl" not in str(fpath.parent).lower():
                violations.append(Violation(
                    file=rel,
                    line=1,
                    message=f"Implementation file '{fpath.name}' is not inside an impl/ subdirectory",
                    suggestion="Move to the impl/ subdirectory of the interface's directory",
                    check_type=CheckType.AST,
                ))
    return violations


def check_impl_naming(
    source_root: Path,
    profile: FrameworkProfile,
) -> list[Violation]:
    """Check that impl files follow InterfaceName + Impl convention (Rule #4)."""
    violations: list[Violation] = []

    for ext in profile.file_extensions:
        # Find all files in impl/ directories
        for fpath in source_root.rglob(f"impl/*{ext}"):
            rel = str(fpath.relative_to(source_root))
            stem = fpath.stem

            # Remove common suffixes for checking
            # e.g., UserServiceImpl.ts → check if UserService.ts exists as sibling of impl/
            clean_name = _strip_impl_suffix(stem)
            if clean_name == stem:
                # File in impl/ but doesn't have Impl suffix
                # Check it's not a helper/utility
                if not _is_test_or_util(stem):
                    violations.append(Violation(
                        file=rel,
                        line=1,
                        message=f"File in impl/ directory but name '{stem}' doesn't end with 'Impl'",
                        suggestion=f"Rename to '{stem}Impl{fpath.suffix}' or move out of impl/",
                        check_type=CheckType.AST,
                    ))
    return violations


def check_layer_exists(
    source_root: Path,
    profile: FrameworkProfile,
) -> list[Violation]:
    """Check that expected layer directories exist (Rule #16 for backend)."""
    violations: list[Violation] = []

    for layer in profile.layers:
        if layer.is_shared:
            continue
        found = False
        for lpath in layer.paths:
            if (source_root / lpath.rstrip("/")).exists():
                found = True
                break
        if not found:
            violations.append(Violation(
                file=str(source_root),
                line=0,
                message=f"Layer directory not found: '{layer.name}' (expected at {layer.paths})",
                suggestion=f"Create directory for the '{layer.name}' layer",
                check_type=CheckType.AST,
            ))
    return violations


def _is_impl_name(name: str) -> bool:
    """Check if filename suggests an implementation (case-insensitive)."""
    lower = name.lower()
    return (
        lower.endswith("impl")
        or lower.endswith(".impl")
        or lower.endswith("_impl")
        or lower.endswith("-impl")
    )


def _strip_impl_suffix(name: str) -> str:
    """Remove Impl suffix from a name."""
    for suffix in ("Impl", "impl", "_impl", "-impl", ".impl"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _is_test_or_util(name: str) -> bool:
    lower = name.lower()
    return any(k in lower for k in ("test", "spec", "mock", "stub", "fixture", "helper", "util"))
