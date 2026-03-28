"""Scoring engine — weighted score calculation and grading."""
from __future__ import annotations

from arch_qube.rules.models import RuleResult, ScanReport, Severity


def calculate_score(results: list[RuleResult]) -> tuple[float, str]:
    """Calculate weighted score and letter grade.

    Returns (score 0-100, grade letter).
    """
    if not results:
        return 100.0, "A+"

    total_weight = sum(r.weight for r in results)
    if total_weight == 0:
        return 100.0, "A+"

    weighted_sum = sum(r.weighted_score for r in results)
    score = (weighted_sum / total_weight) * 100.0
    score = round(score, 1)

    grade = _score_to_grade(score)
    return score, grade


def build_report(
    results: list[RuleResult],
    framework: str,
    source_root: str,
    files_scanned: int,
    threshold: float,
) -> ScanReport:
    """Build a complete scan report."""
    score, grade = calculate_score(results)

    # Any critical violation = automatic fail
    has_critical = any(
        r.severity == Severity.CRITICAL and not r.passed
        for r in results
    )

    passed = score >= threshold and not has_critical

    return ScanReport(
        framework=framework,
        source_root=source_root,
        files_scanned=files_scanned,
        total_score=score,
        grade=grade,
        passed=passed,
        threshold=threshold,
        rule_results=results,
    )


def _score_to_grade(score: float) -> str:
    if score >= 98:
        return "A+"
    if score >= 95:
        return "A"
    if score >= 85:
        return "B"
    if score >= 70:
        return "C"
    if score >= 50:
        return "D"
    return "F"
