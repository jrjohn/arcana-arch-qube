"""rust-desktop refinements: false positives removed, real findings kept.

1. test code (tests.rs, *_tests.rs, tests/, #[cfg(test)] items) is excluded from every check;
2. rule 06 scores an egui View by business-logic constructs, not by line count;
3. a View may import the plugin API's contract types, not its services.

Each fix is paired with the violation it must NOT hide (gates-that-never-looked)."""
from pathlib import Path

from arch_qube.profiles.loader import load_profile
from arch_qube.scanners.content_checks import _logic_points
from arch_qube.scanners.import_graph import _expand_use, blank_rust_cfg_test, build_import_graph

from tests.test_rust_desktop import GOOD, PROFILES, _crate, _scan, _write

VIEW = "crates/arcana-ui/src/pages/order_list/view.rs"
SHELL = "crates/arcana-ui/src/shell/mod.rs"

# A long immediate-mode layout function: 30+ lines, no business logic.
LONG_UI = """pub fn filters(ui: &mut Ui, s: &State, out: &mut Vec<Input>) {
    ui.horizontal(|ui| {
        ui.label("Status");
        egui::ComboBox::from_id_salt("status")
            .selected_text(s.status_text.clone())
            .show_ui(ui, |ui| {
                for (k, v) in [("all", "All"), ("open", "Open"), ("done", "Done")] {
                    if ui.selectable_label(s.status == k, v).clicked() {
                        out.push(Input::Status(k.to_owned()));
                    }
                }
            });
        let mut q = s.query.clone();
        if ui.text_edit_singleline(&mut q).changed() {
            out.push(Input::Query(q));
        }
        if s.loading {
            ui.spinner();
        } else {
            ui.label(format!("{} rows", s.rows.len()));
        }
        for row in &s.rows {
            ui.horizontal(|ui| {
                ui.label(&row.number);
                ui.label(&row.customer);
                if ui.button("Open").clicked() {
                    out.push(Input::Open(row.id));
                }
            });
        }
        let w = ui.available_width() - 24.0;
        ui.add_sized([w, 28.0], egui::Button::new("Search"));
    });
}
"""

# The same View computing what its ViewModel should: repository call, loop, totals.
LOGIC_IN_VIEW = """pub fn totals(ui: &mut Ui, repo: &dyn OrderRepository, svc: &UiServices) {
    let orders = repo.find_all().unwrap_or_default();
    let mut total = 0.0;
    let mut count = 0;
    for o in &orders {
        total += o.unit_price * f64::from(o.quantity);
        count += 1;
        if o.discount > 0.0 {
            total -= o.discount;
        }
    }
    svc.settings.set_value("last_total", total.into());
    ui.label(format!("{total} / {count}"));
}
"""


def _rule06(tmp_path, extra: dict[str, str]):
    files = dict(GOOD)
    files.update(extra)
    _write(tmp_path, files)
    return _scan(tmp_path)["no-business-logic-in-boundary"]


# ---------- 1. test code ----------

def test_test_files_and_cfg_test_items_are_not_judged(tmp_path):
    heavy = "use egui::Ui;\n" + LOGIC_IN_VIEW.replace("pub fn totals", "fn a") + \
        LOGIC_IN_VIEW.replace("pub fn totals", "fn b")
    res = _rule06(tmp_path, {
        "crates/arcana-ui/src/shell/tests.rs": heavy,
        "crates/arcana-ui/src/shell/heavy_tests.rs": heavy,
        "crates/arcana-ui/src/shell/tests/flows.rs": heavy,
        VIEW: "use egui::Ui;\npub fn show(ui: &mut Ui) {}\n#[cfg(test)]\nmod t {\n" + heavy + "}\n",
    })
    assert res.evaluated and res.violations == []


def test_code_after_a_cfg_test_item_is_still_judged(tmp_path):
    # the old import parser stopped at the first #[cfg(test)]: everything below went unseen
    res = _rule06(tmp_path, {
        VIEW: "use egui::Ui;\n#[cfg(test)]\nfn helper() -> u32 { 1 }\n" + LOGIC_IN_VIEW})
    assert [v.message.split(":")[0] for v in res.violations] == [
        "Business logic in boundary method 'totals'"]


def test_import_after_a_cfg_test_item_is_still_checked(tmp_path):
    files = dict(GOOD)
    files[VIEW] = ("#[cfg(test)]\nmod t {\n    use arcana_data::dao::OrderDao;\n}\n"
                   "use arcana_data::repository::OrderRepository;\n")
    _write(tmp_path, files)
    [v] = _scan(tmp_path)["layer-direction"].violations
    assert v.line == 5 and "repository" in v.message


def test_blank_rust_cfg_test_keeps_line_numbers():
    src = ["fn a() {}", "#[cfg(test)]", "mod t {", "  fn x() {}", "}", "fn b() {}",
           "#[cfg(test)] mod tests;", "#[cfg(test)]", "#[allow(dead_code)]", "fn h() -> u8 { 1 }",
           "fn c() {}"]
    assert blank_rust_cfg_test(src) == ["fn a() {}", "", "", "", "", "fn b() {}", "", "", "", "",
                                        "fn c() {}"]


# ---------- 2. business logic, not lines ----------

def test_long_pure_ui_view_is_not_flagged(tmp_path):
    assert LONG_UI.count("\n") > 30
    res = _rule06(tmp_path, {VIEW: "use egui::Ui;\n" + LONG_UI})
    assert res.evaluated and res.violations == []


def test_view_computing_totals_through_a_repository_is_flagged(tmp_path):
    assert LOGIC_IN_VIEW.count("\n") < 20  # the line-count rule never saw this one
    res = _rule06(tmp_path, {VIEW: "use egui::Ui;\n" + LOGIC_IN_VIEW})
    [v] = res.violations
    assert "'totals'" in v.message and "infra call x2" in v.message


def test_shell_state_machine_stays_flagged(tmp_path):
    shell = """impl Shell {
    fn apply(&mut self, tab: TabId, effects: Vec<Effect>) {
        for e in effects {
            match e {
                Effect::Theme(id) => {
                    self.svc.app_settings.set_theme_id(&id);
                    self.theme_id = id;
                }
                Effect::Culture(c) => {
                    self.svc.localization.set_culture(&c);
                }
                Effect::CloseSelf => self.close_tab(tab, true),
                Effect::ConfirmDiscard => self.dialog = Some(Dialog::Discard { tab }),
            }
        }
    }
}
"""
    res = _rule06(tmp_path, {SHELL: shell})
    assert [v.file for v in res.violations] == [SHELL]


def test_logic_points_ignore_layout_math_and_ui_branching():
    assert _logic_points(LONG_UI.splitlines())[0] == 0
    pts, hits = _logic_points(LOGIC_IN_VIEW.splitlines())
    assert pts > 6 and hits["infra call"] == 2 and hits["mutation"] == 3
    # a lookup table and a styling function are not decisions/mutations
    table = "fn key(r: &Route) -> &str {\n match r {\n Route::Home => \"nav.home\",\n" \
            " Route::Orders => \"nav.orders\",\n Route::Settings(_) => \"nav.settings\",\n }\n}"
    style = "fn visuals(p: &Palette) -> Visuals {\n let mut v = Visuals::dark();\n" \
            " v.panel_fill = p.background;\n v.window_fill = p.pane;\n v\n}"
    assert _logic_points(table.splitlines())[0] == 0
    assert _logic_points(style.splitlines())[0] == 0


def test_other_profiles_keep_the_line_count():
    for f in PROFILES.glob("*.yaml"):
        p = load_profile(PROFILES, f.stem)
        assert p.boundary_measure == ("logic" if f.stem == "rust-desktop" else "lines"), f.stem


# ---------- 3. plugin_api contract types ----------

PLUGIN_API = {
    "crates/arcana-plugin-api/Cargo.toml": _crate("arcana-plugin-api"),
    "crates/arcana-plugin-api/src/lib.rs": "pub mod schema;\npub mod services;\npub use services::*;\n",
    "crates/arcana-plugin-api/src/schema.rs": "pub struct SettingField;\npub enum SettingKind {}\n",
    "crates/arcana-plugin-api/src/health.rs": "pub enum HealthState {}\n",
    "crates/arcana-plugin-api/src/services/mod.rs": "pub mod menu;\npub use menu::*;\n",
    "crates/arcana-plugin-api/src/services/menu.rs":
        "pub enum MenuLocation {}\npub trait MenuRegistry {}\n",
    "crates/arcana-plugin-api/src/services/window.rs": "pub trait WindowService {}\n",
}


def _view_imports(tmp_path, lines: str) -> list[str]:
    files = dict(GOOD)
    files.update(PLUGIN_API)
    files[VIEW] = lines + files[VIEW]
    _write(tmp_path, files)
    return [v.message for v in _scan(tmp_path)["layer-direction"].violations]


def test_view_may_import_plugin_contract_types(tmp_path):
    assert _view_imports(tmp_path, (
        "use arcana_plugin_api::MenuLocation;\n"
        "use arcana_plugin_api::schema::{SettingField, SettingKind};\n"
        "use arcana_plugin_api::{HealthState, PluginState};\n")) == []


def test_view_importing_plugin_services_is_caught(tmp_path):
    msgs = _view_imports(tmp_path, (
        "use arcana_plugin_api::{HealthState, WindowService};\n"
        "use arcana_plugin_api::services::MenuRegistry;\n"))
    assert len(msgs) == 2
    assert any(m.endswith("src/WindowService'") for m in msgs)
    assert any(m.endswith("services/MenuRegistry'") for m in msgs)  # same file as MenuLocation
    assert all("'view' imports from 'plugin_api'" in m for m in msgs)


def test_plugin_api_files_stay_in_plugin_api(tmp_path):
    files = dict(GOOD)
    files.update(PLUGIN_API)
    _write(tmp_path, files)
    p = load_profile(PROFILES, "rust-desktop")
    assert p.classify_specific("crates/arcana-plugin-api/src/services/menu.rs") == "plugin_api"
    assert p.classify_specific("crates/arcana-plugin-api/src/services/MenuLocation") == "plugin_contract"
    assert p.classify_specific("crates/arcana-plugin-api/src/services/MenuRegistry") == "plugin_api"


def test_use_groups_are_expanded():
    assert _expand_use("a::{B, c::{D, self}, E as F, g::*}") == ["a::B", "a::c::D", "a::c", "a::E", "a::g"]
    assert _expand_use("x::Basket") == ["x::Basket"]  # "as" inside a name is not an alias


def test_multiline_use_group_resolves_each_item(tmp_path):
    files = dict(GOOD)
    files.update(PLUGIN_API)
    files[VIEW] = "use arcana_plugin_api::{\n    MenuLocation,\n    WindowService,\n};\n" + files[VIEW]
    _write(tmp_path, files)
    edges = {e.target_import: e.target_layer for e in build_import_graph(tmp_path, load_profile(PROFILES, "rust-desktop"))
             if e.source_file == VIEW}
    assert edges["crates/arcana-plugin-api/src/MenuLocation"] == "plugin_contract"
    assert edges["crates/arcana-plugin-api/src/WindowService"] == "plugin_api"
