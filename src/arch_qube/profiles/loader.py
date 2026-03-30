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

    def get_layer_order(self) -> list[str]:
        return [l.name for l in self.layers]

    def classify_file(self, rel_path: str) -> str | None:
        """Determine which layer a file belongs to."""
        for layer in self.layers:
            for lpath in layer.paths:
                if lpath in rel_path:
                    return layer.name
        return None

    def is_di_container(self, rel_path: str) -> bool:
        """Check if file is a DI container / module file."""
        from pathlib import PurePosixPath
        p = PurePosixPath(rel_path)
        for pat in self.di_container_files:
            # PurePath.match supports ** glob patterns
            if p.match(pat):
                return True
            # Also check basename match for simple patterns like "*Config.java"
            if "*" in pat and "/" not in pat:
                from fnmatch import fnmatch
                if fnmatch(p.name, pat):
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
    )
