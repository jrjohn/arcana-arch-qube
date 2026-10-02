"""Go layering was blind (2026-10-02): string literals were parsed as imports, package imports
(directories, no trailing slash) never matched a layer, and the domain-first go profile filed
internal/domain/{service,repository,dao} under "domain". Plus: opt-in dependency inversion."""
import dataclasses
from pathlib import Path

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import run_ast_scan
from arch_qube.scanners.import_graph import build_import_graph

PROFILES = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"
MOD = "github.com/acme/app/internal"


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def _layer_violations(root: Path, profile):
    rules = [r for r in load_rules(RULES) if r.id == "layer-direction"]
    [res] = run_ast_scan(root, profile, rules)
    return res.violations


def test_go_service_importing_controller_package_is_caught(tmp_path):
    _write(tmp_path, {
        "domain/service/user_service.go":
            f'package service\n\nimport (\n\t"context"\n\t"{MOD}/controller/http"\n)\n\nfunc F() {{}}\n',
        "controller/http/user.go": "package http\n"})
    vs = _layer_violations(tmp_path, load_profile(PROFILES, "go"))
    assert [v.file for v in vs] == ["domain/service/user_service.go"]
    assert "'service' imports from 'controller'" in vs[0].message


def test_go_layers_inside_domain_are_classified(tmp_path):
    _write(tmp_path, {
        "domain/dao/user_dao.go": f'package dao\n\nimport "{MOD}/domain/entity"\n',
        "domain/repository/user_repo.go": f'package repository\n\nimport "{MOD}/domain/dao"\n'})
    edges = build_import_graph(tmp_path, load_profile(PROFILES, "go"))
    got = {(e.source_layer, e.target_layer) for e in edges}
    assert got == {("dao", "domain"), ("repository", "dao")}


def test_go_string_literals_are_not_imports(tmp_path):
    _write(tmp_path, {"domain/service/s.go":
                      f'package service\n\nimport "{MOD}/domain/entity"\n\n'
                      'func F() string { return "/api/controller/users" }\n'})
    edges = build_import_graph(tmp_path, load_profile(PROFILES, "go"))
    assert [e.target_import for e in edges] == [f"{MOD}/domain/entity"]


def _dao_imports_repository(tmp_path, target: str):
    _write(tmp_path, {
        "domain/dao/user_dao.go": f'package dao\n\nimport "{MOD}/{target}"\n',
        "domain/repository/user_repository.go": "package repository\n"})


def test_dao_implementing_repository_interface_needs_dependency_inversion(tmp_path):
    _dao_imports_repository(tmp_path, "domain/repository")
    plain = load_profile(PROFILES, "go")
    assert len(_layer_violations(tmp_path, plain)) == 1  # dao -> repository is upward
    dip = dataclasses.replace(plain, dip_ports=["repository"])
    assert _layer_violations(tmp_path, dip) == []         # allowed: it implements the port


def test_dependency_inversion_still_forbids_importing_an_implementation(tmp_path):
    _dao_imports_repository(tmp_path, "domain/repository/impl")
    dip = dataclasses.replace(load_profile(PROFILES, "go"), dip_ports=["repository"])
    assert len(_layer_violations(tmp_path, dip)) == 1


def test_no_bundled_profile_turns_dependency_inversion_on_silently():
    for f in PROFILES.glob("*.yaml"):
        assert load_profile(PROFILES, f.stem).dip_ports == [], f.stem


def test_layer_paths_match_whole_directory_names():
    ios = load_profile(PROFILES, "ios")
    assert ios.classify_specific("SwiftData") is None          # Apple framework, not Data/
    assert ios.classify_specific("ArcanaData/Repo.swift") == "data"
    assert ios.classify_specific("Sources/Data/Repo.swift") == "data"
