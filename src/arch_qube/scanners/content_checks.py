"""Checks for rules 05, 06, 08, 12, 14, 17, 19.

Until 2026-10-02 these rules declared check names the scanner never implemented, so they scored
100% without reading any code. Each check here is deliberately narrow: three of them guard
critical rules, where one finding fails the whole gate, so a false positive turns a repo's CI red
for no reason. When a heuristic cannot tell, it does not report.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from arch_qube.rules.models import CheckType, Violation

# Boundary = the layer that talks to the outside world.
_BOUNDARY = {"backend": {"controller"}, "client": {"presentation"}}

_COMMENT_PREFIXES = ("//", "#", "*", "/*", "--", "<!--")

_TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "androidtest", "unittest",
                   "integrationtest", "testing"}
_TEST_FILE_RE = re.compile(
    r"(\.spec\.|\.test\.|_test\.(go|py|rs|cpp|c)$|^test_.*\.py$|Tests?\.(java|kt|swift|cs)$|"
    r"Test\.(cpp|hpp)$|test_.*\.(cpp|c)$)")
_SKIP_DIRS = {".git", "node_modules", "build", "dist", "target", ".gradle", ".build", "out",
              "coverage", ".scannerwork", "arch-qube-reports", "DerivedData", "Pods", "vendor"}


def _is_test_path(rel: str) -> bool:
    lower = rel.lower()
    return any(p in lower for p in (".spec.", ".test.", "_test.", "_spec.", "mock", "stub.",
                                    "fixture", "/test/", "/tests/", "/__tests__/"))


def _layer_files(ctx, layers: set[str], skip_di: bool = True) -> Iterator[tuple[str, list[str]]]:
    """(relative path, lines) for every non-test source file in the given layers.

    skip_di=False for content rules: the rust profile treats every lib.rs/mod.rs as a DI container
    (right for import-direction checks — they re-export), but SQL in a service crate's lib.rs is
    still SQL in the service layer (a planted query there went unseen on 2026-10-02)."""
    for ext in ctx.profile.file_extensions:
        for fpath in ctx.source_root.rglob(f"*{ext}"):
            rel = str(fpath.relative_to(ctx.source_root))
            if _is_test_path(rel) or (skip_di and ctx.profile.is_di_container(rel)):
                continue
            if _content_layer(ctx.profile, rel) not in layers:
                continue
            try:
                yield rel, fpath.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue


def _content_layer(profile, rel: str) -> str | None:
    """Layer for content rules. classify_file() returns the FIRST layer whose path appears, and the
    go profile lists the shared `domain` layer first (ec6ebe0, to stop dependency-inversion
    imports from being flagged), so internal/domain/service/x.go classifies as domain and the
    service checks never saw a go service. If the first match is a shared layer, a more specific
    non-shared layer in the same path wins. Import-direction rules keep using classify_file."""
    return profile.classify_specific(rel)


def _code_lines(lines: list[str]) -> Iterator[tuple[int, str]]:
    """(line number, text) for lines that are not comments (line comments and /* */ blocks)."""
    in_block = False
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if in_block:
            if "*/" in s:
                in_block = False
            continue
        if s.startswith("/*") and "*/" not in s:
            in_block = True
            continue
        if not s or s.startswith(_COMMENT_PREFIXES) or s.startswith('"""') or s.startswith("'''"):
            continue
        yield i, raw


def _boundary_layers(ctx) -> set[str]:
    names = set(ctx.profile.get_layer_order())
    return _BOUNDARY.get(ctx.profile.category, set()) & names


def _v(file: str, line: int, message: str, suggestion: str) -> Violation:
    return Violation(file=file, line=line, message=message, suggestion=suggestion,
                     check_type=CheckType.AST)


# ---------- 05 dto-entity-separation: boundary must not import Entity classes ----------

# An Entity is something that lives in an entity/ or entities/ package. Matching the class name
# instead flagged Spring's ResponseEntity in every controller (7 of 11 hits in arcana-cloud-springboot).
_ENTITY_TARGET = re.compile(r"(^|/)entit(y|ies)(/|$)", re.I)


def check_boundary_uses_dto(ctx, check) -> list[Violation]:
    boundary = _boundary_layers(ctx)
    out = []
    for e in ctx.edges:
        if e.source_layer not in boundary or ctx.profile.is_di_container(e.source_file):
            continue
        if _ENTITY_TARGET.search(e.target_import):
            out.append(_v(e.source_file, e.line,
                          f"Boundary '{e.source_layer}' imports an Entity: '{e.target_import}'",
                          "Expose a DTO and convert with a Mapper; keep Entities behind the service layer."))
    return out


# ---------- 06 no-business-logic-in-boundary: boundary methods stay short ----------

_FUNC_START = {
    ".py": re.compile(r"^(\s*)(async\s+)?def\s+\w+"),
    ".go": re.compile(r"^\s*func\b"),
    ".rs": re.compile(r"^\s*(pub(\([^)]*\))?\s+)?(async\s+)?(unsafe\s+)?fn\s+\w+"),
    ".swift": re.compile(r"^\s*(@\w+\s+)*((public|private|internal|fileprivate|open|override|"
                         r"static|class|mutating|final|nonisolated)\s+)*func\s+\w+"),
    ".kt": re.compile(r"^\s*(@\w+(\([^)]*\))?\s+)*((public|private|internal|protected|override|"
                      r"suspend|inline|open|operator)\s+)*fun\s+"),
    ".java": re.compile(r"^\s*(@\w+(\([^)]*\))?\s+)*(public|private|protected)\s+"
                        r"(static\s+|final\s+|synchronized\s+|abstract\s+)*[\w<>\[\],.? ]+\s+\w+\s*\("),
    ".cs": re.compile(r"^\s*(\[[^\]]*\]\s*)*(public|private|protected|internal)\s+"
                      r"(static\s+|async\s+|override\s+|virtual\s+|sealed\s+)*[\w<>\[\],.? ]+\s+\w+\s*\("),
    ".ts": re.compile(r"^\s*(export\s+)?(default\s+)?(async\s+)?function\s+\w+|"
                      r"^\s*((public|private|protected|static|async|readonly)\s+)*\w+\s*\([^)]*\)\s*"
                      r"(:\s*[^={]+)?\{\s*$"),
}
for _ext in (".tsx", ".js", ".vue", ".ets"):
    _FUNC_START[_ext] = _FUNC_START[".ts"]
_NOT_A_FUNC = re.compile(r"^\s*(if|for|while|switch|catch|else|return|try|do|when|guard)\b")
# Declarative UI is long by nature and is not business logic: ArkUI/SwiftUI/Compose layout blocks
# (Column() { ... }, Row, Scroll — capitalised, they are component calls, not methods) and the render
# entry points. 26 of harmonyos's first-pass hits were `Column`, 12 were `build`.
_UI_RENDER = {"build", "render", "body", "template", "setup", "Content", "View"}


def _is_ui_block(name: str, lines: list[str], idx: int, ext: str) -> bool:
    if name in _UI_RENDER:
        return True
    if ext in (".ts", ".tsx", ".js", ".vue", ".ets") and name[:1].isupper():
        return True
    if ext == ".kt" and any("@Composable" in lines[j] for j in range(max(0, idx - 3), idx + 1)):
        return True
    return False


def _brace_body_len(lines: list[str], start: int) -> int:
    """Lines from `start` (0-based, the header) to the brace that closes the first '{'."""
    depth, opened = 0, False
    for j in range(start, min(len(lines), start + 2000)):
        code = re.sub(r'"(\\.|[^"\\])*"|\'(\\.|[^\'\\])*\'|//.*$', "", lines[j])
        for ch in code:
            if ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
                if opened and depth == 0:
                    return j - start + 1
        if not opened and j - start > 3:  # declaration without a body (interface, abstract)
            return 0
    return 0


def _indent_body_len(lines: list[str], start: int, indent: int) -> int:
    end = start + 1
    while end < len(lines):
        s = lines[end]
        if s.strip() and (len(s) - len(s.lstrip())) <= indent:
            break
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return end - start


def check_boundary_complexity(ctx, check) -> list[Violation]:
    max_lines = int(check.params.get("max_method_lines", 20))
    out = []
    for rel, lines in _layer_files(ctx, _boundary_layers(ctx)):
        # ViewModels are where client logic is supposed to live (rule 06 is about the View), and
        # a build script is not application code.
        if _VIEWMODEL_FILE.search("/" + rel) or Path(rel).name == "build.rs":
            continue
        ext = Path(rel).suffix
        pat = _FUNC_START.get(ext)
        if pat is None:
            continue
        for idx, line in enumerate(lines):
            m = pat.match(line)
            if not m or _NOT_A_FUNC.match(line):
                continue
            nm = re.search(r"(?:func|fun|fn|def|function)\s+(\w+)|(\w+)\s*\(", line)
            name = (nm.group(1) or nm.group(2)) if nm else "?"
            if _is_ui_block(name, lines, idx, ext):
                continue
            if ext == ".py":
                n = _indent_body_len(lines, idx, len(m.group(1)))
            else:
                n = _brace_body_len(lines, idx)
            if n > max_lines:
                out.append(_v(rel, idx + 1,
                              f"{n}-line method '{name}' in boundary "
                              f"(max {max_lines})",
                              "Move the logic into the Service/ViewModel; keep the boundary to delegation."))
    return out


# ---------- 08 test-coverage: a test suite exists ----------

def check_test_dir_exists(ctx, check) -> list[Violation]:
    root = ctx.project_root
    for path in root.rglob("*"):
        rel_parts = path.relative_to(root).parts
        if any(p in _SKIP_DIRS for p in rel_parts) or len(rel_parts) > 8:
            continue
        name = path.name
        if path.is_dir() and (name.lower() in _TEST_DIR_NAMES or name.endswith("Tests")):
            return []
        if path.is_file() and _TEST_FILE_RE.search(name):
            return []
        if path.is_file() and path.suffix == ".rs" and "#[cfg(test)]" in _head(path):
            return []
    return [_v(".", 0, "No test directory or test files found",
               "Add a test suite (tests/, src/test, *Tests target, *_test.go, *.spec.ts ...).")]


def _head(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


# ---------- 12 view-no-service: views reach services only through a ViewModel ----------

_VIEWMODEL_FILE = re.compile(r"view[-_.]?model|viewmodel|(^|[/_.-])vm\.|presenter|store\.|"
                             r"/stores?/|/composables?/|/hooks?/|/viewmodels?/", re.I)
_SERVICE_TARGET = re.compile(r"(^|/)services?(/|$)|service$|[-_.]service(\.|$)|usecases?(/|$)", re.I)
# Cross-cutting services a view legitimately needs even when they sit under domain/services:
# translation (a translate pipe *is* a view of the i18n service), navigation, theming, logging,
# user notifications. Rule 12 is about business services (UserService, OrderService ...).
# arcana-angular: all 6 first-pass hits were i18n.service / nav-graph.service.
_CROSS_CUTTING = re.compile(r"i18n|l10n|translat|locale|nav(igation|[-_]?graph)?[-_.]?service|"
                            r"router|routing|theme|logger|logging|analytics|toast|notification|"
                            r"snackbar|dialog|modal", re.I)


def check_view_no_service_import(ctx, check) -> list[Violation]:
    out = []
    for e in ctx.edges:
        if e.source_layer != "presentation" or ctx.profile.is_di_container(e.source_file):
            continue
        if _VIEWMODEL_FILE.search("/" + e.source_file):
            continue
        # Only domain/data services count: a UI service in core/ (toast, navigation) is fine.
        if e.target_layer not in ("domain", "data", "service"):
            continue
        target = e.target_import.rstrip("/")
        if _SERVICE_TARGET.search(target) and not _CROSS_CUTTING.search(target.rsplit("/", 1)[-1]):
            out.append(_v(e.source_file, e.line,
                          f"View imports a domain/data service directly: '{e.target_import}'",
                          "Call the service from the ViewModel and bind the view to its outputs."))
    return out


# ---------- 14 navgraph-typesafe: a navigation graph / route table exists ----------

_NAV_FILE = re.compile(r"nav[-_]?graph|navigation|router|routes|routing|approute|main_pages\.json|"
                       r"route\.(ts|kt|swift|ets|cs|tsx)$", re.I)


def check_navgraph_exists(ctx, check) -> list[Violation]:
    root = ctx.project_root
    for path in root.rglob("*"):
        rel_parts = path.relative_to(root).parts
        if any(p in _SKIP_DIRS for p in rel_parts) or _is_test_path("/".join(rel_parts)):
            continue
        # the whole relative path counts: vue keeps its routes in src/router/index.ts
        if path.is_file() and _NAV_FILE.search("/".join(rel_parts)):
            return []
    return [_v(".", 0, "No navigation graph / route definition file found",
               "Define routes in one typed NavGraph/route table instead of string literals.")]


# ---------- 17 service-no-db: no SQL / ORM queries in the service layer ----------

def _compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    out = []
    for p in patterns:
        out.append(re.compile(p if ".*" in p else re.escape(p)))
    return out


def check_no_db_in_service(ctx, check) -> list[Violation]:
    pats = _compile_patterns(check.params.get("forbidden_patterns", []))
    out = []
    for rel, lines in _layer_files(ctx, {"service"}, skip_di=False):
        for n, line in _code_lines(lines):
            for p in pats:
                if p.search(line):
                    out.append(_v(rel, n, f"Database access in service layer: '{line.strip()[:80]}'",
                                  "Move the query into a Repository and call it through its interface."))
                    break
    return out


# ---------- 19 transaction-at-service: no transaction annotations outside the service ----------

def check_transaction_placement(ctx, check) -> list[Violation]:
    annotations = check.params.get("annotations", [])
    forbidden = set(check.params.get("forbidden_layers", ["controller"]))
    pats = [re.compile(re.escape(a) + r"\b") for a in annotations]
    out = []
    for rel, lines in _layer_files(ctx, forbidden, skip_di=False):
        for n, line in _code_lines(lines):
            if any(p.search(line) for p in pats):
                out.append(_v(rel, n, f"Transaction boundary in '{ctx.profile.classify_file(rel)}': "
                                      f"'{line.strip()[:80]}'",
                              "Put the transaction on the Service method that owns the unit of work."))
    return out


# ---------- 22 module-boundary: modules meet only through each other's public surface ----------
# Fowler (Presentation Domain Data Layering): once a layer grows, "split your top level into domain
# oriented modules which are internally layered". The layer rules cannot see one module reaching
# into another's internals; this check can. A module is a directory directly under one of the
# profile's modules.roots that contains files (features/users/..., not a flat screens/Home.kt).

_SHARED_MODULES = {"shared", "common", "core", "ui", "components"}


def _module_of(path: str, roots: list[str]) -> str | None:
    p = "/" + path.strip("/")
    for root in roots:
        i = p.find("/" + root)
        if i < 0:
            continue
        rest = p[i + 1 + len(root):].split("/")
        if len(rest) >= 2 and rest[0]:  # a directory under the root, with something inside it
            return root + rest[0]
    return None


def _is_public(target: str, module: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatch
    inside = target.split(module, 1)[-1].strip("/")
    name = inside.rsplit("/", 1)[-1]
    stem = name.split(".")[0]
    for pat in patterns:
        if pat.endswith("/") and (inside + "/").startswith(pat):
            return True
        if fnmatch(name, pat) or fnmatch(stem, pat) or fnmatch(name, pat.rsplit(".", 1)[0]):
            return True
    return False


def check_module_public_api_only(ctx, check) -> list[Violation] | None:
    roots = ctx.profile.module_roots
    if not roots:
        return None
    modules = set()
    for ext in ctx.profile.file_extensions:
        for fpath in ctx.source_root.rglob(f"*{ext}"):
            m = _module_of(str(fpath.relative_to(ctx.source_root)), roots)
            if m:
                modules.add(m)
    if len(modules) < 2:
        return None  # nothing to keep apart
    public = ctx.profile.module_public or ["index", "public-api", "api/"]
    out = []
    for e in ctx.edges:
        src, tgt = _module_of(e.source_file, roots), _module_of(e.target_import, roots)
        if not src or not tgt or src == tgt:
            continue
        if tgt.rsplit("/", 1)[-1].lower() in _SHARED_MODULES or _is_public(e.target_import, tgt, public):
            continue
        out.append(_v(e.source_file, e.line,
                      f"Module '{src}' reaches into '{tgt}' internals: '{e.target_import}'",
                      f"Expose what is needed from '{tgt}' through its public API ({', '.join(public)})."))
    return out
