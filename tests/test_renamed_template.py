"""Layers are recognised by role, not by the template's name.

2026-11-24 (arcana-cloud-rust pilot): tools/new-app.sh renamed crates arcana-rest/ -> demo-rest/ ...
and the product scored 99.8 but FAILED "Backend Layer Chain": rust.yaml listed the template's
literal crate names, so a renamed product had no layers. The same held for rust-desktop
(arcana-ui/, arcana-data/ ...) and iOS (ArcanaData/ ...). A product renamed from a template must
classify exactly like the template, and a flat project must still be unlayered."""
import shutil
from pathlib import Path

import pytest

from arch_qube.profiles.loader import apply_project_layers, load_profile, resolve_source_root
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import is_unlayered, run_ast_scan
from arch_qube.scoring.engine import calculate_score

ROOT = Path(__file__).parent.parent
PROFILES_DIR = ROOT / "src" / "arch_qube" / "profiles"
RULES_DIR = ROOT / "src" / "arch_qube" / "rules"

RUST_CRATES = {
    "rest": "use {n}_service::user_service::UserService;\npub fn get() {{ UserService::find(); }}\n",
    "service": "use {n}_repository::user_repository::UserRepository;\n"
               "pub struct UserService;\nimpl UserService {{ pub fn find() {{ UserRepository::get(); }} }}\n",
    "repository": "use {n}_domain::user::User;\npub struct UserRepository;\n"
                  "impl UserRepository {{ pub fn get() -> Option<User> {{ None }} }}\n",
    "domain": "use {n}_core::Id;\npub struct User {{ pub id: Id }}\n",
    "core": "pub type Id = u64;\n",
}
RUST_MODULE = {"rest": "handler", "service": "user_service", "repository": "user_repository",
               "domain": "user", "core": None}


def _rust_workspace(root: Path, name: str) -> Path:
    members = []
    for role, body in RUST_CRATES.items():
        crate = f"{name}-{role}"
        members.append(f'"crates/{crate}"')
        src = root / "crates" / crate / "src"
        src.mkdir(parents=True)
        (root / "crates" / crate / "Cargo.toml").write_text(
            f'[package]\nname = "{crate}"\nversion = "0.1.0"\n')
        mod = RUST_MODULE[role]
        if mod:
            (src / "lib.rs").write_text(f"pub mod {mod};\n")
            (src / f"{mod}.rs").write_text(body.format(n=name))
        else:
            (src / "lib.rs").write_text(body.format(n=name))
    (root / "Cargo.toml").write_text(f"[workspace]\nmembers = [{', '.join(members)}]\n")
    return root


def _scan(root: Path, framework: str):
    prof = load_profile(PROFILES_DIR, framework)
    src = root
    for sr in prof.source_roots:
        cand = resolve_source_root(root, sr)
        if cand is not None:
            src = cand
            break
    results = run_ast_scan(src, prof, load_rules(RULES_DIR), project_root=root)
    return prof, src, results


def _summary(results):
    score, _ = calculate_score(results)
    return score, sorted((r.rule_id, r.evaluated, r.compliance, len(r.violations))
                         for r in results)


def _rel_layers(prof, src):
    out = {}
    for f in sorted(src.rglob("*.rs")):
        rel = f.relative_to(src).as_posix()
        out[rel.replace("arcana", "NAME").replace("demo", "NAME")] = prof.classify_specific(rel)
    return out


def test_renamed_rust_workspace_classifies_like_the_template(tmp_path):
    orig = _rust_workspace(tmp_path / "orig", "arcana")
    ren = _rust_workspace(tmp_path / "ren", "demo")
    p1, s1, r1 = _scan(orig, "rust")
    p2, s2, r2 = _scan(ren, "rust")
    layers = _rel_layers(p1, s1)
    assert layers["NAME-rest/src/handler.rs"] == "controller"
    assert layers["NAME-core/src/lib.rs"] == "core"
    assert _rel_layers(p2, s2) == layers
    assert not is_unlayered(s2, p2)
    assert _summary(r2) == _summary(r1)


def test_flat_rust_project_is_still_unlayered(tmp_path):
    shutil.copytree(ROOT / "tests" / "fixtures" / "rust_flat", tmp_path / "p")
    prof, src, _ = _scan(tmp_path / "p", "rust")
    assert is_unlayered(src, prof)


def test_crate_named_only_like_a_role_is_not_a_layer():
    # The glob is one directory name ending in the role: "demo-rest-old/" or "rest-client/" is not
    # the controller crate.
    prof = load_profile(PROFILES_DIR, "rust")
    assert prof.classify_specific("demo-rest/src/x.rs") == "controller"
    assert prof.classify_specific("demo-rest-old/src/x.rs") is None
    assert prof.classify_specific("rest-client/src/x.rs") is None


@pytest.mark.parametrize("name", ["arcana", "demo", "acme-km"])
def test_rust_desktop_crates_by_role(name):
    prof = load_profile(PROFILES_DIR, "rust-desktop")
    assert prof.classify_specific(f"crates/{name}-ui/src/pages/home/mod.rs") == "viewmodel"
    assert prof.classify_specific(f"crates/{name}-ui/src/shell/top.rs") == "view"
    assert prof.classify_specific(f"crates/{name}-data/src/repository/user.rs") == "repository"
    assert prof.classify_specific(f"crates/{name}-data/src/sqlite.rs") == "dao"
    assert prof.classify_specific(f"crates/{name}-plugin-api/src/lib.rs") == "plugin_api"
    assert prof.is_di_container(f"crates/{name}-app/src/main.rs")


def _ios(root: Path, name: str) -> Path:
    src = root / f"{name.lower()}-ios" / "Sources"
    for layer in ("Presentation", "Domain", "Data", "Core"):
        (src / f"{name}{layer}").mkdir(parents=True)
    (src / f"{name}Data" / "UserRepository.swift").write_text(
        f"import SwiftData\nimport {name}Domain\nstruct UserRepository {{}}\n")
    (src / f"{name}Domain" / "User.swift").write_text(
        f"import Foundation\nimport {name}Core\nstruct User {{}}\n")
    (src / f"{name}Core" / "Id.swift").write_text("import Foundation\ntypealias Id = Int\n")
    (src / f"{name}Presentation" / "UserView.swift").write_text(
        f"import SwiftUI\nimport {name}Domain\nstruct UserView {{}}\n")
    return root


def test_renamed_ios_modules_classify_like_the_template(tmp_path):
    p1, s1, r1 = _scan(_ios(tmp_path / "orig", "Arcana"), "ios")
    p2, s2, r2 = _scan(_ios(tmp_path / "ren", "Demo"), "ios")
    assert s1.name == s2.name == "Sources"  # "*-ios/Sources" found the renamed source root
    assert p2.classify_specific("DemoData/UserRepository.swift") == "data"
    assert _summary(r2) == _summary(r1)


def test_ios_glob_does_not_swallow_apple_frameworks(tmp_path):
    # "*Data/" must not read `import SwiftData` / `import CoreData` as the app's data layer: a
    # globbed segment has to be one of the project's own directories.
    prof, _, _ = _scan(_ios(tmp_path / "p", "Demo"), "ios")
    assert prof.classify_specific("SwiftData") is None
    assert prof.classify_specific("CoreData") is None
    assert prof.classify_specific("DemoData") == "data"


def test_project_layer_paths_still_apply_to_renamed_crates(tmp_path):
    # Backward compatibility: a renamed product that ships an arch-qube.yaml (cloud-rust's
    # new-app.sh writes one) keeps working, and its entries change nothing now.
    (tmp_path / ".git").mkdir()
    cfg = tmp_path / "arch-qube.yaml"
    cfg.write_text("layer_paths:\n  controller: [demo-rest]\n  service: [vault-index]\n")
    prof = load_profile(PROFILES_DIR, "rust")
    apply_project_layers(prof, cfg)
    assert prof.classify_specific("demo-rest/src/x.rs") == "controller"
    assert prof.classify_specific("vault-index/src/x.rs") == "service"
