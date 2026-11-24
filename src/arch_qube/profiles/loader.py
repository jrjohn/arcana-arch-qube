"""Load framework profile from YAML."""
from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re
import yaml


@lru_cache(maxsize=None)
def _segment_glob(path: str) -> re.Pattern[str]:
    """A layer path with `*` (one directory-name fragment, never crossing "/"), anchored at a
    directory boundary; each globbed segment is a capture group. "*-rest/" matches
    ".../demo-rest/x" and ".../arcana-rest/x" but not ".../demo-rest-old/x"."""
    parts = []
    for seg in path.split("/"):
        if "*" in seg:
            parts.append("(" + re.escape(seg).replace(r"\*", "[^/]*") + ")")
        else:
            parts.append(re.escape(seg))
    return re.compile("/" + "/".join(parts))


def path_matches(probe: str, path: str, local_dirs: frozenset[str] | None = None) -> bool:
    """probe is "/" + a relative path. A plain layer path is a substring match at a directory
    boundary (as always); one containing `*` is a segment glob — so a profile can recognise a
    workspace crate / module by its role ("*-rest/", "*Data/") instead of a template's literal
    name ("arcana-rest/", "ArcanaData/"), and a product renamed from the template classifies
    identically.

    A globbed segment names one of the project's OWN directories: when the scan knows them
    (local_dirs), a segment that is not one of them does not match. Otherwise "*Data/" would read
    `import SwiftData` / `import CoreData` as the iOS data layer."""
    if "*" not in path:
        return "/" + path in probe
    for m in _segment_glob(path).finditer(probe):
        if local_dirs is None or all(g in local_dirs for g in m.groups()):
            return True
    return False


_NEVER_LOCAL = {".git", "node_modules", "target", ".build", "build", "dist", "Pods", ".gradle"}


def project_dir_names(root: Path, exclude: list[str] | tuple[str, ...] = ()) -> frozenset[str]:
    """Every directory name under root (build output and VCS pruned)."""
    import os
    skip = _NEVER_LOCAL | set(exclude)
    names: set[str] = set()
    for _dirpath, dirnames, _files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        names.update(dirnames)
    return frozenset(names)


def resolve_source_root(root: Path, source_root: str) -> Path | None:
    """root/source_root if it is a directory. A `*` in a segment is a glob (first match in sorted
    order), so "*-ios/Sources" finds the sources of a project renamed from arcana-ios."""
    if "*" not in source_root:
        cand = root / source_root
        return cand if cand.exists() else None
    for cand in sorted(root.glob(source_root)):
        if cand.is_dir():
            return cand
    return None


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
    # Directory names of the scanned project, set by FrameworkProfile.bind_project. None = unknown
    # (a profile used outside a scan): globbed segments then match any name.
    local_dirs: frozenset[str] | None = None

    def matches(self, rel_path: str) -> bool:
        probe = "/" + rel_path
        if not any(path_matches(probe, p, self.local_dirs) for p in self.paths):
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
    # Project-declared layers (arch-qube.yaml `layer_paths`). Consulted only when the built-in
    # layers match nothing, so a project can bring unlayered code UNDER the rules but can never
    # move a file out of the layer its path already puts it in.
    fallback_layers: list[LayerDef] = field(default_factory=list)

    def source_files(self, root: Path, ext: str, pattern: str | None = None):
        """root.rglob for one extension, minus exclude_dirs."""
        for f in root.rglob(pattern or f"*{ext}"):
            if self.exclude_dirs and any(
                    part in self.exclude_dirs for part in f.relative_to(root).parts[:-1]):
                continue
            yield f

    def bind_project(self, root: Path) -> None:
        """Tell glob layer paths ("*-rest/") which directory names are the project's own. Only
        walks the tree when some layer path actually globs."""
        layers = self.layers + self.fallback_layers
        if not any("*" in p for l in layers for p in l.paths):
            return
        names = project_dir_names(root, self.exclude_dirs)
        for l in layers:
            l.local_dirs = names

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
        for layer in self.fallback_layers:
            if layer.matches(rel_path):
                return layer.name
        return None

    def classify_specific(self, rel_path: str) -> str | None:
        """Like classify_file, but a shared layer (domain/core) that matched first gives way to a
        more specific non-shared layer in the same path, and a package path written without a
        trailing slash (Go imports a directory) is matched as a directory. internal/domain/service
        is the service layer, not domain — whatever order the profile lists its layers in."""
        shared = {l.name for l in self.layers if l.is_shared}
        # Several layer paths in one file path: the one nearest the file wins.
        # arcana-repository/src/dao/x.rs is dao, not repository (2026-11-17: every dao/ file in a
        # repository crate was classified as repository, so the dao layer was invisible).
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


PROJECT_CONFIG = "arch-qube.yaml"


def find_project_config(start: Path) -> Path | None:
    """arch-qube.yaml in `start` or the nearest parent, stopping at the repository root (.git)."""
    d = start.resolve()
    while True:
        cand = d / PROJECT_CONFIG
        if cand.is_file():
            return cand
        if (d / ".git").exists() or d.parent == d:
            return None
        d = d.parent


def apply_project_layers(profile: FrameworkProfile, config: Path) -> dict[str, list[str]]:
    """Read `layer_paths: {layer: [path, ...]}` from a project's arch-qube.yaml into
    profile.fallback_layers. Returns what was applied (for the report). Unknown layer names are an
    error: a typo would otherwise silently leave the code unlayered — the very gap this closes.

    2026-11-17: Desktop KM's 14 domain crates (arcana-vault-index, -organize, ...) matched no
    layer path, so no rule looked at ~120 files and the scan still said 99.5 PASS."""
    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    raw = data.get("layer_paths") or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{config}: layer_paths must be a mapping of layer -> [paths]")
    known = set(profile.get_layer_order())
    applied: dict[str, list[str]] = {}
    for name, paths in raw.items():
        if name not in known:
            raise ValueError(f"{config}: unknown layer '{name}' (known: {sorted(known)})")
        if isinstance(paths, str):
            paths = [paths]
        paths = [p if p.endswith("/") else p + "/" for p in paths]
        profile.fallback_layers.append(LayerDef(name=name, paths=paths))
        applied[name] = paths
    # Dependency inversion is opt-in per project (no bundled profile turns it on): a project whose
    # data-access adapters implement repository ports declares it here, visibly.
    dip = data.get("dip_ports") or []
    if isinstance(dip, str):
        dip = [dip]
    for name in dip:
        if name not in known:
            raise ValueError(f"{config}: unknown layer '{name}' in dip_ports (known: {sorted(known)})")
    if dip:
        profile.dip_ports = list(dip)
        applied["dip_ports"] = list(dip)
    return applied
