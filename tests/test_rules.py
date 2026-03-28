"""Test rule loader and models."""
from pathlib import Path
from arch_qube.rules.loader import load_rules
from arch_qube.rules.models import Severity

RULES_DIR = Path(__file__).parent.parent / "rules"


def test_load_all_rules():
    rules = load_rules(RULES_DIR)
    assert len(rules) >= 6


def test_rule_has_required_fields():
    rules = load_rules(RULES_DIR)
    for rule in rules:
        assert rule.id
        assert rule.name
        assert rule.category in ("common", "client", "backend")
        assert isinstance(rule.severity, Severity)
        assert rule.weight > 0


def test_load_common_rules_only():
    rules = load_rules(RULES_DIR, category_filter="common")
    assert all(r.category == "common" for r in rules)
    assert len(rules) >= 4


def test_load_backend_rules_only():
    rules = load_rules(RULES_DIR, category_filter="backend")
    assert all(r.category == "backend" for r in rules)
    assert len(rules) >= 2


def test_layer_direction_rule_is_critical():
    rules = load_rules(RULES_DIR)
    ld = next(r for r in rules if r.id == "layer-direction")
    assert ld.severity == Severity.CRITICAL
    assert ld.weight == 15
    assert len(ld.ast_checks) > 0
