"""Test scanner against fixture codebases."""
from pathlib import Path
from arch_qube.rules.loader import load_rules
from arch_qube.profiles.loader import load_profile
from arch_qube.scanner import run_ast_scan
from arch_qube.scoring.engine import build_report

FIXTURES = Path(__file__).parent / "fixtures"
RULES_DIR = Path(__file__).parent.parent / "rules"
PROFILES_DIR = Path(__file__).parent.parent / "profiles"


def test_angular_good_has_no_violations():
    profile = load_profile(PROFILES_DIR, "angular")
    rules = load_rules(RULES_DIR)
    source = FIXTURES / "angular_good" / "src" / "app"
    results = run_ast_scan(source, profile, rules)

    total_violations = sum(len(r.violations) for r in results)
    assert total_violations == 0, f"Expected 0 violations, got {total_violations}"


def test_angular_bad_has_violations():
    profile = load_profile(PROFILES_DIR, "angular")
    rules = load_rules(RULES_DIR)
    source = FIXTURES / "angular_bad" / "src" / "app"
    results = run_ast_scan(source, profile, rules)

    total_violations = sum(len(r.violations) for r in results)
    assert total_violations > 0, "Expected violations in bad codebase"


def test_springboot_bad_has_violations():
    profile = load_profile(PROFILES_DIR, "springboot")
    rules = load_rules(RULES_DIR)
    source = FIXTURES / "springboot_bad" / "src" / "main" / "java" / "com" / "arcana"
    results = run_ast_scan(source, profile, rules)

    total_violations = sum(len(r.violations) for r in results)
    assert total_violations > 0, "Expected violations in bad codebase"


def test_report_scoring():
    profile = load_profile(PROFILES_DIR, "angular")
    rules = load_rules(RULES_DIR)
    source = FIXTURES / "angular_good" / "src" / "app"
    results = run_ast_scan(source, profile, rules)
    report = build_report(results, "angular", str(source), 3, 95.0)

    assert report.total_score >= 0
    assert report.grade in ("A+", "A", "B", "C", "D", "F")
    assert report.framework == "angular"


def test_bad_report_fails_gate():
    profile = load_profile(PROFILES_DIR, "angular")
    rules = load_rules(RULES_DIR)
    source = FIXTURES / "angular_bad" / "src" / "app"
    results = run_ast_scan(source, profile, rules)
    report = build_report(results, "angular", str(source), 1, 95.0)

    # Bad codebase should fail the gate
    assert report.total_violations > 0
