"""Load framework profile from YAML."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class LayerDef:
    name: str
    paths: list[str]
    is_shared: bool = False
    # Item-level layer: a target matches only if its LAST path segment is one of these names (as
    # well as one of `paths`). Lets a layer own a few data types of a module that also holds
    # services — e.g. plugin_api's MenuLocation enum lives in services/menu.rs next to the
    # MenuRegistry trait. A source *file* never ends in a bare item name, so files keep their
    # crate's layer; only imports of the listed items are reclassified.
    items: list[str] = field(default_factory=list)

    def matches(self, rel_path: str) -> bool:
        probe = "/" + rel_path
        if not any("/" + p in probe for p in self.paths):
            return False
        return not self.items or probe.rstrip("/").rsplit("/", 1)[-1] in self.items


@dataclass
class FrameworkProfile:
    framework: str
    platform: str  # web, mobile, desktop, backend, embedded
    category: str  # client or backend
    source_roots: list[str]
    layers: list[LayerDef]
    allowed_dependencies: dict[str, list[str]]
    file_extensions: list[str]
    import_pattern: str  # regex for static imports
    di_container_files: list[str] = field(default_factory=list)
    naming: dict[str, str] = field(default_factory=dict)
    # Dependency inversion (Fowler, PresentationDomainDataLayering: "arrange things so that the
    # domain does not depend on its data sources by introducing a mapper" / Hexagonal). Layers
    # listed here own interfaces ("ports") that a lower layer may depend on in order to implement
    # them — e.g. dao implementing the repository interface. Importing an *implementation* of a
    # port from below is still a violation.
    dip_ports: list[str] = field(default_factory=list)
    # Domain-oriented modules (Fowler: "split your top level into domain oriented modules which
    # are internally layered"). A directory under one of module_roots is a module; another module
    # may only use it through module_public files.
    module_roots: list[str] = field(default_factory=list)
    module_public: list[str] = field(default_factory=list)
    # How `use` paths are turned into file paths. "rust_workspace": crate::/super::/self:: resolve
    # against the importing file, and `use other_crate::x` resolves to that workspace crate's
    # directory (found from its Cargo.toml) — so an import can be classified by the same layer
    # paths as a file. Without it a Rust import is a bare `arcana_infra::x` that matches no layer.
    import_resolver: str | None = None
    # Directory names never scanned (build output, tooling crates). Empty = scan everything under
    # the source root, as before.
    exclude_dirs: list[str] = field(default_factory=list)
    # How rule 06 (no business logic in boundary) measures a boundary function. "lines" (default):
    # body length. "logic": count business-logic constructs and ignore UI calls — for immediate-mode
    # UI (egui), where a layout function is long by nature. See content_checks._logic_points.
    boundary_measure: str = "lines"

    def source_files(self, root: Path, ext: str, pattern: str | None = None):
        """root.rglob for one extension, minus exclude_dirs."""
        for f in root.rglob(pattern or f"*{ext}"):
            if self.exclude_dirs and any(
                    part in self.exclude_dirs for part in f.relative_to(root).parts[:-1]):
                continue
            yield f

    def get_layer_order(self) -> list[str]:
        return [l.name for l in self.layers]

    def classify_file(self, rel_path: str) -> str | None:
        """Determine which layer a file belongs to.

        A layer path matches whole directory names only: "Data/" matches ".../Data/x" but not
        "SwiftData/" (`import SwiftData` was read as the iOS data layer once package imports were
        matched as directories)."""
        for layer in self.layers:
            if layer.matches(rel_path):
                return layer.name
        return None

    def classify_specific(self, rel_path: str) -> str | None:
        """Like classify_file, but a shared layer (domain/core) that matched first gives way to a
        more specific non-shared layer in the same path, and a package path written without a
        trailing slash (Go imports a directory) is matched as a directory. internal/domain/service
        is the service layer, not domain — whatever order the profile lists its layers in."""
        shared = {l.name for l in self.layers if l.is_shared}
        for path in (rel_path, rel_path.rstrip("/") + "/"):
            first = self.classify_file(path)
            if first is not None and first not in shared:
                return first
            for layer in self.layers:
                if not layer.is_shared and layer.matches(path):
                    return layer.name
        return self.classify_file(rel_path) or self.classify_file(rel_path.rstrip("/") + "/")

    def is_di_container(self, rel_path: str) -> bool:
        """Check if file is a DI container / module file."""
        from pathlib import PurePosixPath
        from fnmatch import fnmatch
        p = PurePosixPath(rel_path)
        for pat in self.di_container_files:
            # PurePath.match supports ** glob patterns
            if p.match(pat):
                return True
            # fnmatch on full path (handles **/ as wildcard prefix)
            if fnmatch(rel_path, pat.replace("**/", "*")):
                return True
            # Check basename match for patterns like "*Impl.cpp", "*Config.java"
            pat_name = pat.rsplit("/", 1)[-1] if "/" in pat else pat
            if pat_name != "**" and "*" in pat_name and fnmatch(p.name, pat_name):
                return True
        return False

    def is_allowed_dependency(self, from_layer: str, to_layer: str) -> bool:
        allowed = self.allowed_dependencies.get(from_layer, [])
        return to_layer in allowed or to_layer == from_layer


def load_profile(profiles_dir: Path, framework: str) -> FrameworkProfile:
    path = profiles_dir / f"{framework}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)

    layers = [
        LayerDef(
            name=l["name"],
            paths=l.get("paths", []),
            is_shared=l.get("is_shared", False),
            items=l.get("items", []),
        )
        for l in data.get("layers", [])
    ]

    return FrameworkProfile(
        framework=data["framework"],
        platform=data.get("platform", "web"),
        category=data.get("category", "client"),
        source_roots=data.get("source_roots", ["src"]),
        layers=layers,
        allowed_dependencies=data.get("allowed_dependencies", {}),
        file_extensions=data.get("file_extensions", [".ts"]),
        import_pattern=data.get("import_pattern", r"import .* from ['\"](.+?)['\"]"),
        di_container_files=data.get("di_container_files", []),
        naming=data.get("naming", {}),
        dip_ports=(data.get("dependency_inversion") or {}).get("ports", []),
        module_roots=(data.get("modules") or {}).get("roots", []),
        module_public=(data.get("modules") or {}).get("public", []),
        import_resolver=data.get("import_resolver"),
        exclude_dirs=data.get("exclude_dirs", []),
        boundary_measure=data.get("boundary_measure", "lines"),
    )
