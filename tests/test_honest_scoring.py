"""A rule no check ran for must not count as compliant (2026-10-02: 13 of 21 rules were silently
scored 100% because the scanner ignored check names it did not implement)."""
from pathlib import Path

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.rules.models import AstCheck, Rule, RuleResult, Severity, Violation
from arch_qube.scanner import HANDLERS, run_ast_scan
from arch_qube.scoring.engine import build_report, calculate_score

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"


def _rule(check: str, severity=Severity.MAJOR) -> Rule:
    return Rule(id=f"r-{check}", name=check, description="", category="common",
                severity=severity, weight=10, ast_checks=[AstCheck(type="x", check=check)])


def _result(weight, compliance, evaluated=True, severity=Severity.MAJOR, violations=()):
    return RuleResult(rule_id=f"r{weight}{compliance}", rule_name="r", category="common",
                      severity=severity, weight=weight, compliance=compliance,
                      violations=list(violations), evaluated=evaluated)


def test_unknown_check_name_is_not_evaluated_and_named():
    profile = load_profile(PROFILES_DIR, "angular")
    [res] = run_ast_scan(FIXTURES / "angular_good" / "src" / "app", profile,
                         [_rule("no_such_check_anywhere")])
    assert res.evaluated is False
    assert res.unimplemented_checks == ["no_such_check_anywhere"]
    assert res.violations == []


def test_known_check_is_evaluated():
    profile = load_profile(PROFILES_DIR, "angular")
    [res] = run_ast_scan(FIXTURES / "angular_good" / "src" / "app", profile,
                         [_rule("no_upward_imports")])
    assert res.evaluated is True
    assert res.unimplemented_checks == []


def test_not_evaluated_rules_do_not_inflate_the_score():
    # one real rule at 50%, plus a heavy rule nothing checked: the old engine said 95.
    score, _ = calculate_score([_result(10, 50.0), _result(90, 100.0, evaluated=False)])
    assert score == 50.0


def test_nothing_evaluated_scores_zero_not_a_free_hundred():
    score, grade = calculate_score([_result(10, 100.0, evaluated=False)])
    assert (score, grade) == (0.0, "F")


def test_unevaluated_critical_rule_cannot_fail_or_pass_the_gate():
    results = [_result(10, 100.0),
               _result(10, 100.0, evaluated=False, severity=Severity.CRITICAL)]
    report = build_report(results, "angular", ".", 1, 90.0)
    assert report.passed is True
    assert len(report.not_evaluated) == 1


def test_every_bundled_rule_check_name_is_either_implemented_or_reported():
    """Guards the original failure mode: a typo or a not-yet-written check must show up as
    'not evaluated' in the report rather than disappear."""
    profile = load_profile(PROFILES_DIR, "springboot")
    rules = load_rules(RULES_DIR)
    results = run_ast_scan(FIXTURES / "springboot_good" / "src" / "main" / "java" / "com" / "arcana",
                           profile, rules)
    by_id = {r.rule_id: r for r in results}
    for rule in rules:
        if rule.applies_to and "springboot" not in rule.applies_to:
            continue
        names = [c.check for c in rule.ast_checks]
        res = by_id[rule.id]
        implemented = any(n in HANDLERS for n in names)
        # evaluated => something implemented ran; a handler may also decline (not applicable)
        assert not res.evaluated or implemented, rule.id
        assert implemented or not res.evaluated, rule.id
        assert res.unimplemented_checks == [n for n in names if n not in HANDLERS], rule.id
