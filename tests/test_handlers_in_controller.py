"""2026-11-16: Desktop KM scored 99.4 PASS. Template crates had all four layers, so the project counted
as layered; the crates doing the real work had none, and their axum handlers were invisible to rules
that classify by path. handlers_in_controller judges by content."""
import shutil
from pathlib import Path

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import run_ast_scan

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"


def _chain(root: Path):
    profile = load_profile(PROFILES_DIR, "rust")
    res = {r.rule_id: r for r in run_ast_scan(root, profile, load_rules(RULES_DIR))}
    return res["controller-service-repo-dao"]


def test_handlers_outside_the_controller_layer_are_flagged():
    chain = _chain(FIXTURES / "rust_layered_plus_flat")
    flagged = [v for v in chain.violations if "未分層的 HTTP handler" in v.message]
    assert [v.file for v in flagged] == ["crates/vault-web/src/routes.rs"]
    assert "2 個" in flagged[0].message and "search_page" in flagged[0].message
    assert chain.compliance < 100.0


def test_handlers_inside_the_controller_layer_pass(tmp_path):
    # 對照組:同一個專案拿掉沒分層的 crate → 沒有這種違規。
    root = tmp_path / "p"
    shutil.copytree(FIXTURES / "rust_layered_plus_flat", root)
    shutil.rmtree(root / "crates" / "vault-web")
    chain = _chain(root)
    assert not [v for v in chain.violations if "未分層的 HTTP handler" in v.message]


def test_std_path_argument_is_not_a_handler():
    chain = _chain(FIXTURES / "rust_layered_plus_flat")
    assert not any("helper" in v.message for v in chain.violations)
