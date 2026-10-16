"""Build import dependency graph and check layer violations."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

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
    rust_ws = profile.import_resolver == "rust_workspace"
    crates = _rust_crate_dirs(source_root) if rust_ws else {}

    for ext in profile.file_extensions:
        for fpath in profile.source_files(source_root, ext):
            # Skip test/spec/mock files — they legitimately import Impl
            if _is_test_file(fpath.name):
                continue
            rel = str(fpath.relative_to(source_root))
            if rust_ws and _is_rust_test(rel):
                continue
            src_layer = profile.classify_specific(rel)
            if rust_ws and fpath.suffix == ".rs":
                imports = _parse_rust_imports(fpath, source_root, crates)
            else:
                imports = _parse_file_imports(fpath, profile)

            for line_num, target in imports:
                # classify_specific: Go imports a package (a directory, no trailing slash), and the
                # go profile lists the shared domain layer first — together they left
                # internal/domain/{service,dao,repository} unclassified or "domain", so only 3% of
                # arcana-cloud-go's internal import edges were ever checked.
                tgt_layer = profile.classify_specific(target)
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
            if edge.target_layer in profile.dip_ports and not _is_impl_target(edge.target_import):
                continue  # implementing an upper layer's interface (dependency inversion)
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

    if fpath.suffix == ".go":
        return _parse_go_imports(lines)

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


_RUST_USE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?use\s+(?:::)?([A-Za-z0-9_:]+)")


def _rust_crate_dirs(root: Path) -> dict[str, str]:
    """{crate_name_with_underscores: "<dir relative to root>/src"} for every workspace crate."""
    out: dict[str, str] = {}
    for toml in root.rglob("Cargo.toml"):
        if "target" in toml.relative_to(root).parts:
            continue
        m = re.search(r'^\[package\][^\[]*?^name\s*=\s*"([^"]+)"',
                      toml.read_text(encoding="utf-8", errors="ignore"), re.M | re.S)
        if m:
            d = toml.parent.relative_to(root).as_posix()
            out[m.group(1).replace("-", "_")] = (d + "/src") if d != "." else "src"
    return out


def _is_rust_test(rel: str) -> bool:
    """Integration tests (tests/), `tests.rs` / `*_tests.rs` test modules, benches and examples
    wire concrete types on purpose."""
    parts = rel.split("/")
    name = parts[-1]
    return (any(p in ("tests", "benches", "examples") for p in parts[:-1])
            or name == "tests.rs" or name.endswith("_tests.rs"))


_STRIP_CODE = re.compile(r'"(\\.|[^"\\])*"|\'(\\.|[^\'\\])\'|//.*$')


def blank_rust_cfg_test(lines: list[str]) -> list[str]:
    """`lines` with every `#[cfg(test)]` item blanked (same length, so line numbers hold).

    The item is whatever follows the attribute (after further attributes): `mod tests;`,
    `mod tests { ... }`, a test-only fn or impl. Only that item goes — code after it is still
    read (stopping at the first #[cfg(test)] would hide a non-test fn below a test helper)."""
    out = list(lines)
    n, i = len(lines), 0
    while i < n:
        s = lines[i].strip()
        if not s.startswith("#[cfg(test)]"):
            i += 1
            continue
        rest = s[len("#[cfg(test)]"):].strip()
        j = i if rest and not rest.startswith("//") else i + 1
        while j < n and j != i and (not lines[j].strip() or lines[j].strip().startswith(("#[", "//"))):
            j += 1
        end = _rust_item_end(lines, j, skip_attr=(j == i)) if j < n else n - 1
        for k in range(i, min(end, n - 1) + 1):
            out[k] = ""
        i = end + 1
    return out


def _rust_item_end(lines: list[str], start: int, skip_attr: bool = False) -> int:
    """0-based index of the last line of the item starting at `start`: the `;` that ends a
    braceless item, or the brace closing its body."""
    depth, opened = 0, False
    for j in range(start, len(lines)):
        code = _STRIP_CODE.sub("", lines[j])
        if skip_attr and j == start:
            code = code.split("]", 1)[-1]
        for ch in code:
            if ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
                if opened and depth == 0:
                    return j
            elif ch == ";" and depth == 0:
                return j
    return len(lines) - 1


def _expand_use(tree: str) -> list[str]:
    """`a::{b, c::{d, self}, e as f}` -> [a::b, a::c::d, a::c, a::e]; a glob `a::*` -> a."""
    tree = re.sub(r"\s+", "", re.sub(r"\s+as\s+\w+", "", tree))
    i = tree.find("{")
    if i < 0:
        return [tree[:-3] if tree.endswith("::*") else tree]
    prefix, inner = tree[:i], tree[i + 1: tree.rfind("}")]
    parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        depth += ch == "{"
        depth -= ch == "}"
        cur += ch
    parts.append(cur)
    out = []
    for part in parts:
        if not part:
            continue
        for leaf in _expand_use(part):
            out.append(prefix.rstrip(":") if leaf == "self" else prefix + leaf)
    return out


def _rust_use_statements(lines: list[str]):
    """(line number, is_pub, [use paths]) per `use` statement, spanning lines until its `;`."""
    i, n = 0, len(lines)
    while i < n:
        m = _RUST_USE_HEAD.match(lines[i])
        if not m:
            i += 1
            continue
        start, stmt = i, lines[i][m.end():]
        while ";" not in stmt and i + 1 < n:
            i += 1
            stmt += " " + _STRIP_CODE.sub("", lines[i])
        i += 1
        stmt = stmt.split(";", 1)[0].lstrip()
        if stmt.startswith("::"):
            stmt = stmt[2:]
        yield start + 1, bool(m.group(1)), [p for p in _expand_use(stmt) if p]


_RUST_USE_HEAD = re.compile(r"^\s*(pub(?:\([^)]*\))?\s+)?use\s+")


def _parse_rust_imports(fpath: Path, root: Path, crates: dict[str, str]) -> list[tuple[int, str]]:
    """`use` paths resolved to project-relative module paths:
    crate::a::b -> <crate>/src/a/b, super::x -> parent module dir, other_ws_crate::a -> its dir.
    Brace groups are expanded (`use a::{B, c::D}` is two imports), so an item-level layer can
    tell `MenuLocation` from `MenuRegistry` in the same group.
    External crates stay as written with '::' (egui::Ui), so a layer path "egui::" can name them.
    #[cfg(test)] items are skipped: the inline test module wires concrete types on purpose."""
    try:
        lines = fpath.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    lines = blank_rust_cfg_test(lines)
    rel = fpath.relative_to(root).as_posix()
    # the module directory of this file: a/b.rs is module a/b; a/mod.rs, lib.rs, main.rs are a/
    parts = rel.split("/")
    mod_dir = parts[:-1] if parts[-1] in ("mod.rs", "lib.rs", "main.rs") else parts[:-1] + [parts[-1][:-3]]
    src_idx = max((i for i, p in enumerate(parts[:-1]) if p == "src"), default=None)
    crate_src = parts[: src_idx + 1] if src_idx is not None else parts[:-1]
    out: list[tuple[int, str]] = []
    for i, is_pub, paths in _rust_use_statements(lines):
        for path in paths:
            segs = [x for x in path.split("::") if x]
            if not segs:
                continue
            head = segs[0]
            if head == "crate":
                base, rest = crate_src, segs[1:]
            elif head in ("super", "self"):
                base, rest = list(mod_dir), segs
                while rest and rest[0] in ("super", "self"):
                    if rest.pop(0) == "super" and len(base) > len(crate_src):
                        base = base[:-1]
            elif head in crates:
                base, rest = crates[head].split("/"), segs[1:]
            elif ((root / "/".join(mod_dir) / f"{head}.rs").is_file()
                  or (root / "/".join(mod_dir) / head).is_dir()):
                if is_pub:
                    continue  # a module re-exporting its own child (`pub use view::show`) is structure
                base, rest = list(mod_dir), segs  # a child module of this one (`use shell::Shell`)
            else:
                out.append((i, path.lstrip(":")))
                continue
            out.append((i, "/".join(base + rest)))
    return out


def _is_impl_target(target: str) -> bool:
    t = target.lower().rstrip("/")
    last = t.rsplit("/", 1)[-1]
    return "/impl/" in t + "/" or last.endswith("impl") or last.endswith("_impl") or ".impl." in t


def _parse_go_imports(lines: list[str]) -> list[tuple[int, str]]:
    """Only real Go imports: `import "x"` and the lines of an `import ( ... )` block. The go
    profile's pattern (any double-quoted string) also matched every string literal, so a URL like
    "/api/service/x" in a service file became a fake cross-layer import."""
    import re
    out: list[tuple[int, str]] = []
    in_block = False
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if in_block:
            if s.startswith(")"):
                in_block = False
                continue
            m = re.search(r'"([^"]+)"', s)
            if m and not s.startswith("//"):
                out.append((i, m.group(1)))
        elif s.startswith("import ("):
            in_block = True
        elif s.startswith("import "):
            m = re.search(r'"([^"]+)"', s)
            if m:
                out.append((i, m.group(1)))
        elif s.startswith(("func ", "type ", "var ", "const ")):
            break  # imports are over
    return out


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
