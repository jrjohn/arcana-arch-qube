"""2026-11-23: iNAPLink (ESP32 gateway, 5,900 lines of flat C in main/) scored 90/100 —
the esp32 profile did not scan .c, and with every file in main/ (the shared core layer) no
layer rule had anything to violate. A layered firmware must keep its score."""
from pathlib import Path

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import chain_layers, is_unlayered, run_ast_scan
from arch_qube.scoring.engine import build_report

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"


def _profile(fw="esp32"):
    return load_profile(PROFILES_DIR, fw)


def _scan(name: str, fw="esp32"):
    return {r.rule_id: r for r in run_ast_scan(FIXTURES / name, _profile(fw), load_rules(RULES_DIR))}


def test_esp32_profile_scans_c_files():
    assert ".c" in _profile().file_extensions


def test_embedded_chain_is_the_profiles_non_shared_layers():
    assert set(chain_layers(_profile("esp32"))) == {"service", "driver"}
    assert "service" in chain_layers(_profile("stm32"))


def test_flat_firmware_is_unlayered_and_layered_is_not():
    assert is_unlayered(FIXTURES / "esp32_flat", _profile())
    assert not is_unlayered(FIXTURES / "esp32_layered", _profile())


def test_flat_firmware_fails_layer_direction_instead_of_not_evaluated():
    ld = _scan("esp32_flat")["layer-direction"]
    assert ld.evaluated and ld.compliance == 0.0
    assert any("未分層" in v.message for v in ld.violations)


def test_flat_firmware_report_fails():
    results = run_ast_scan(FIXTURES / "esp32_flat", _profile(), load_rules(RULES_DIR))
    report = build_report(results, framework="esp32", source_root=str(FIXTURES / "esp32_flat"),
                          files_scanned=3, threshold=90.0)
    assert not report.passed


def test_layered_firmware_keeps_layer_direction():
    ld = _scan("esp32_layered")["layer-direction"]
    assert ld.evaluated and ld.compliance == 100.0
    assert not any("未分層" in v.message for v in ld.violations)


def test_web_clients_are_not_judged_unlayered():
    # The rule covers backend + embedded only; a client profile with no chain is never "unlayered".
    assert chain_layers(_profile("angular")) == ()
