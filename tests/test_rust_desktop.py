"""rust-desktop profile (egui + Clean Architecture + MVVM-UDF, modelled on arcana-desktop-rust).

The backend `rust` profile scored that app 100 while classifying only core/domain/data/infra:
`use arcana_infra::x` matched no layer, so View/ViewModel rules passed without reading the UI.
These tests plant each violation the profile exists to catch and check it is reported."""
from pathlib import Path

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import run_ast_scan
from arch_qube.scanners.import_graph import build_import_graph

PROFILES = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"


def _crate(name: str) -> str:
    return f'[package]\nname = "{name}"\nversion = "0.1.0"\n'


GOOD = {
    "Cargo.toml": '[workspace]\nmembers = ["crates/*", "plugins/*"]\n',
    "crates/arcana-core/Cargo.toml": _crate("arcana-core"),
    "crates/arcana-core/src/lib.rs": "pub mod error;\n",
    "crates/arcana-core/src/error.rs": "pub struct AppError;\n",
    "crates/arcana-domain/Cargo.toml": _crate("arcana-domain"),
    "crates/arcana-domain/src/lib.rs": "pub mod entities;\npub use entities::Order;\n",
    "crates/arcana-domain/src/entities/mod.rs": "use arcana_core::error::AppError;\npub struct Order;\n",
    "crates/arcana-data/Cargo.toml": _crate("arcana-data"),
    "crates/arcana-data/src/lib.rs": "pub mod dao;\npub mod repository;\n",
    "crates/arcana-data/src/dao.rs": "use arcana_domain::Order;\npub struct OrderDao;\n",
    "crates/arcana-data/src/repository/mod.rs": "use crate::dao::OrderDao;\npub struct OrderRepository;\n",
    "crates/arcana-infra/Cargo.toml": _crate("arcana-infra"),
    "crates/arcana-infra/src/lib.rs": "pub mod services;\npub mod wiring;\n",
    "crates/arcana-infra/src/services.rs":
        "use arcana_data::repository::OrderRepository;\npub trait OrderService {}\n",
    "crates/arcana-infra/src/wiring.rs": "use arcana_data::dao::OrderDao;\n",
    "crates/arcana-ui/Cargo.toml": _crate("arcana-ui"),
    "crates/arcana-ui/src/lib.rs": "pub mod nav;\npub mod pages;\npub mod widgets;\n",
    "crates/arcana-ui/src/nav.rs": "pub enum Route { Orders }\n",
    "crates/arcana-ui/src/widgets.rs": "use egui::Ui;\npub fn card(ui: &mut Ui) {}\n",
    "crates/arcana-ui/src/pages/mod.rs": "pub mod order_list;\n",
    "crates/arcana-ui/src/pages/order_list/mod.rs": (
        "mod view;\npub use view::show;\n"
        "use arcana_domain::Order;\nuse arcana_infra::services::OrderService;\n"
        "use crate::nav::Route;\npub struct State;\n"
        "#[cfg(test)]\nmod t {\n    use arcana_data::dao::OrderDao;\n}\n"),
    "crates/arcana-ui/src/pages/order_list/view.rs": (
        "use egui::Ui;\nuse arcana_domain::Order;\nuse super::State;\n"
        "use crate::widgets::card;\npub fn show(ui: &mut Ui, s: &State) {}\n"),
    "crates/arcana-ui/src/pages/order_list/tests.rs": "use arcana_data::dao::OrderDao;\n",
    "crates/arcana-app/Cargo.toml": _crate("arcana-app"),
    "crates/arcana-app/src/main.rs": "use arcana_infra::wiring;\nuse arcana_data::dao::OrderDao;\nfn main() {}\n",
    "crates/arcana-ui/tests/ui.rs": "use arcana_data::dao::OrderDao;\n",
    # build output must not be scanned
    "target/debug/build/x/out/gen.rs": "use arcana_data::dao::OrderDao;\n",
}


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def _scan(root: Path) -> dict:
    profile = load_profile(PROFILES, "rust-desktop")
    return {r.rule_id: r for r in run_ast_scan(root, profile, load_rules(RULES), project_root=root)}


def _plant(tmp_path: Path, rel: str, line: str) -> dict:
    files = dict(GOOD)
    files[rel] = line + files[rel]
    _write(tmp_path, files)
    return _scan(tmp_path)


def test_every_source_file_lands_in_a_layer(tmp_path):
    _write(tmp_path, GOOD)
    profile = load_profile(PROFILES, "rust-desktop")
    layers = {str(f.relative_to(tmp_path)): profile.classify_specific(str(f.relative_to(tmp_path)))
              for f in profile.source_files(tmp_path, ".rs")}
    assert None not in layers.values(), [k for k, v in layers.items() if v is None]
    assert not any(k.startswith("target/") for k in layers)
    assert layers["crates/arcana-ui/src/pages/order_list/view.rs"] == "view"
    assert layers["crates/arcana-ui/src/pages/order_list/mod.rs"] == "viewmodel"
    assert layers["crates/arcana-data/src/repository/mod.rs"] == "repository"
    assert layers["crates/arcana-data/src/dao.rs"] == "dao"
    assert layers["crates/arcana-infra/src/services.rs"] == "service"


def test_use_paths_resolve_to_workspace_files(tmp_path):
    _write(tmp_path, GOOD)
    profile = load_profile(PROFILES, "rust-desktop")
    edges = {(e.source_file, e.target_import): e.target_layer
             for e in build_import_graph(tmp_path, profile)}
    view = "crates/arcana-ui/src/pages/order_list/view.rs"
    assert edges[(view, "crates/arcana-ui/src/pages/order_list/State")] == "viewmodel"  # super::
    assert edges[(view, "crates/arcana-ui/src/widgets/card")] == "view"  # crate::
    assert edges[(view, "crates/arcana-domain/src/Order")] == "domain"  # other workspace crate
    assert edges[(view, "egui::Ui")] == "view"  # the GUI toolkit
    # test code (tests.rs, tests/, #[cfg(test)]) and build output wire concrete types on purpose
    assert not any("tests" in s or s.startswith("target/") for s, _ in edges)
    assert not any(t.endswith("dao/OrderDao") and "pages" in s for s, t in edges)


def test_clean_app_passes_the_ui_rules(tmp_path):
    _write(tmp_path, GOOD)
    res = _scan(tmp_path)
    for rid in ("layer-direction", "unidirectional-data-flow", "view-no-service", "navgraph-typesafe"):
        assert res[rid].evaluated and not res[rid].violations, (rid, res[rid].violations)


def test_view_importing_a_repository_is_caught(tmp_path):
    res = _plant(tmp_path, "crates/arcana-ui/src/pages/order_list/view.rs",
                 "use arcana_data::repository::OrderRepository;\n")
    for rid in ("layer-direction", "unidirectional-data-flow"):
        assert [v.file for v in res[rid].violations] == ["crates/arcana-ui/src/pages/order_list/view.rs"]


def test_view_importing_a_service_is_caught(tmp_path):
    res = _plant(tmp_path, "crates/arcana-ui/src/pages/order_list/view.rs",
                 "use arcana_infra::services::OrderService;\n")
    assert [v.file for v in res["view-no-service"].violations] == [
        "crates/arcana-ui/src/pages/order_list/view.rs"]
    assert res["unidirectional-data-flow"].violations


def test_viewmodel_importing_a_dao_is_caught(tmp_path):
    res = _plant(tmp_path, "crates/arcana-ui/src/pages/order_list/mod.rs",
                 "use arcana_data::dao::OrderDao;\n")
    [v] = res["layer-direction"].violations
    assert "'viewmodel' imports from 'dao'" in v.message


def test_domain_importing_egui_is_caught(tmp_path):
    res = _plant(tmp_path, "crates/arcana-domain/src/entities/mod.rs", "use egui::Color32;\n")
    [v] = res["layer-direction"].violations
    assert "'domain' imports from 'view'" in v.message


def test_backend_rules_do_not_apply_and_unchecked_rules_are_not_evaluated(tmp_path):
    _write(tmp_path, GOOD)
    res = _scan(tmp_path)
    assert "controller-service-repo-dao" not in res and "controller-no-dao" not in res
    assert not res["module-boundary"].evaluated  # no modules declared: not a vacuous pass
    assert not res["mvvm-ioe-structure"].evaluated  # no implemented check


def test_without_a_nav_file_navgraph_fails(tmp_path):
    files = {k: v for k, v in GOOD.items() if not k.endswith("nav.rs")}
    files["crates/arcana-ui/src/pages/order_list/mod.rs"] = "pub struct State;\n"
    _write(tmp_path, files)
    assert _scan(tmp_path)["navgraph-typesafe"].violations
