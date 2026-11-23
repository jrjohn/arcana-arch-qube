"""Client projects (web / mobile / desktop) with no file in any non-shared layer are unlayered:
the layer-direction rule scores 0 instead of every layer rule passing for free -- the same rule
that backend (PR #20) and embedded (PR #21) already follow. A layered client keeps its score;
the 8 arcana client templates scored identically before and after this change."""
from pathlib import Path

import pytest

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import chain_layers, is_unlayered, run_ast_scan
from arch_qube.scoring.engine import build_report

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"

CLIENTS = ["android", "ios", "harmonyos", "angular", "react", "vue", "windows", "rust-desktop"]


def _profile(fw):
    return load_profile(PROFILES_DIR, fw)


def _fx(fw, kind):
    return FIXTURES / f"{fw.replace('-', '_')}_{kind}"


def _scan(fw, kind):
    return {r.rule_id: r for r in run_ast_scan(_fx(fw, kind), _profile(fw), load_rules(RULES_DIR))}


@pytest.mark.parametrize("fw", ["android", "ios", "harmonyos", "angular", "react", "vue", "windows"])
def test_mvvm_client_chain_is_presentation_domain_data(fw):
    assert chain_layers(_profile(fw)) == ("presentation", "domain", "data")


def test_rust_desktop_chain_is_its_non_shared_layers():
    chain = chain_layers(_profile("rust-desktop"))
    assert "core" not in chain
    assert {"view", "viewmodel", "service", "repository", "dao", "domain"} <= set(chain)


@pytest.mark.parametrize("fw", CLIENTS)
def test_flat_client_is_unlayered_and_layered_is_not(fw):
    assert is_unlayered(_fx(fw, "flat"), _profile(fw))
    assert not is_unlayered(_fx(fw, "layered"), _profile(fw))


@pytest.mark.parametrize("fw", CLIENTS)
def test_flat_client_fails_layer_direction(fw):
    ld = _scan(fw, "flat")["layer-direction"]
    assert ld.evaluated and ld.compliance == 0.0
    assert any("未分層" in v.message for v in ld.violations)


def _report(fw, kind):
    results = run_ast_scan(_fx(fw, kind), _profile(fw), load_rules(RULES_DIR))
    return build_report(results, framework=fw, source_root=str(_fx(fw, kind)),
                        files_scanned=3, threshold=90.0)


@pytest.mark.parametrize("fw", CLIENTS)
def test_flat_client_report_fails_and_scores_below_layered(fw):
    # Both tiny fixtures lack tests, so both fail on other rules; the discriminating part is the
    # score: before this change the flat one scored the same as or HIGHER than the layered one
    # (84.9 vs 81.8 on android/ios/harmonyos).
    flat, layered = _report(fw, "flat"), _report(fw, "layered")
    assert not flat.passed
    assert flat.total_score < layered.total_score - 50


@pytest.mark.parametrize("fw", CLIENTS)
def test_layered_client_keeps_layer_direction(fw):
    ld = _scan(fw, "layered")["layer-direction"]
    assert ld.evaluated and ld.compliance == 100.0
    assert not any("未分層" in v.message for v in ld.violations)
