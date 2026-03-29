"""Build import dependency graph and check layer violations."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from arch_qube.profiles.loader import FrameworkProfile
from arch_qube.rules.models import Violation, CheckType


@dataclass
class ImportEdge:
    source_file: str
    target_import: str
    source_layer: str | None
    target_layer: str | None
    line: int


def build_import_graph(
    source_root: Path,
    profile: FrameworkProfile,
) -> list[ImportEdge]:
    """Walk source files and extract all import edges with layer classification."""
    edges: list[ImportEdge] = []

    for ext in profile.file_extensions:
        for fpath in source_root.rglob(f"*{ext}"):
            # Skip test/spec/mock files — they legitimately import Impl
            if _is_test_file(fpath.name):
                continue
            rel = str(fpath.relative_to(source_root))
            src_layer = profile.classify_file(rel)
            imports = _parse_file_imports(fpath, profile)

            for line_num, target in imports:
                tgt_layer = profile.classify_file(target)
                edges.append(ImportEdge(
                    source_file=rel,
                    target_import=target,
                    source_layer=src_layer,
                    target_layer=tgt_layer,
                    line=line_num,
                ))
    return edges


def check_layer_direction(
    edges: list[ImportEdge],
    profile: FrameworkProfile,
) -> list[Violation]:
    """Check for upward or cross-layer import violations (Rule #1)."""
    violations: list[Violation] = []
    layer_order = profile.get_layer_order()

    for edge in edges:
        if edge.source_layer is None or edge.target_layer is None:
            continue
        if edge.source_layer == edge.target_layer:
            continue
        # DI container / wiring files can import from any layer
        if profile.is_di_container(edge.source_file):
            continue

        if not profile.is_allowed_dependency(edge.source_layer, edge.target_layer):
            violations.append(Violation(
                file=edge.source_file,
                line=edge.line,
                message=(
                    f"Layer violation: '{edge.source_layer}' imports from "
                    f"'{edge.target_layer}' via '{edge.target_import}'"
                ),
                suggestion=(
                    f"'{edge.source_layer}' can only depend on: "
                    f"{profile.allowed_dependencies.get(edge.source_layer, [])}"
                ),
                check_type=CheckType.AST,
            ))
    return violations


def check_impl_import_restriction(
    edges: list[ImportEdge],
    profile: FrameworkProfile,
) -> list[Violation]:
    """Check that only DI container files import *Impl (Rule #3)."""
    violations: list[Violation] = []

    for edge in edges:
        # Check if the import target looks like an Impl file
        target_lower = edge.target_import.lower()
        is_impl = (
            "impl/" in target_lower
            or target_lower.endswith("impl")
            or ".impl." in target_lower
            or "impl." in target_lower.split("/")[-1] if "/" in target_lower else False
        )
        if not is_impl:
            continue

        # Check if the source file is a DI container
        if profile.is_di_container(edge.source_file):
            continue

        # Also allow impl files importing from their own impl/ directory
        if edge.source_layer and "impl" in edge.source_file.lower():
            continue

        violations.append(Violation(
            file=edge.source_file,
            line=edge.line,
            message=f"Direct import of implementation: '{edge.target_import}'",
            suggestion="Import the interface instead. Only DI container should wire Impl.",
            check_type=CheckType.AST,
        ))
    return violations


def _parse_file_imports(
    fpath: Path, profile: FrameworkProfile
) -> list[tuple[int, str]]:
    """Parse imports from a file, returning (line_number, target) pairs."""
    import re

    try:
        lines = fpath.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    results: list[tuple[int, str]] = []
    pattern = re.compile(profile.import_pattern)

    for i, line in enumerate(lines, 1):
        m = pattern.search(line)
        if m:
            target = m.group(1)
            # For relative imports in TS/JS, try to resolve
            if target.startswith("."):
                from arch_qube.scanners.parsers.typescript import resolve_import
                source_root = fpath
                # Walk up to find source root
                for sr in profile.source_roots:
                    try:
                        root = _find_source_root(fpath, sr)
                        if root:
                            resolved = resolve_import(fpath, target, root)
                            if resolved:
                                target = resolved
                            break
                    except Exception:
                        pass
            # For Java imports, extract layer path
            elif "." in target and not target.startswith("."):
                from arch_qube.scanners.parsers.java import import_to_layer_path
                target = import_to_layer_path(target)

            results.append((i, target))
    return results


def _is_test_file(filename: str) -> bool:
    """Check if file is a test/spec/mock file."""
    lower = filename.lower()
    return any(p in lower for p in (".spec.", ".test.", "_test.", "_spec.", "mock.", "stub.", "fixture."))


def _find_source_root(fpath: Path, source_root_pattern: str) -> Path | None:
    """Find the source root directory by walking up from file."""
    current = fpath.parent
    target = source_root_pattern.rstrip("/").split("/")[-1]
    while current != current.parent:
        if current.name == target:
            return current
        current = current.parent
    return None
