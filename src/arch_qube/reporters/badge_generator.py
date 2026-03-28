"""Badge generator — shields.io compatible URL."""
from __future__ import annotations
from arch_qube.rules.models import ScanReport

_GRADE_COLORS = {
    "A+": "brightgreen",
    "A": "green",
    "B": "yellow",
    "C": "orange",
    "D": "red",
    "F": "red",
}


def generate_badge_url(report: ScanReport) -> str:
    """Generate a shields.io badge URL."""
    color = _GRADE_COLORS.get(report.grade, "lightgrey")
    score = report.total_score
    grade = report.grade
    label = "arch--qube"
    msg = f"{grade}%20{score}%2F100"
    return f"https://img.shields.io/badge/{label}-{msg}-{color}.svg"


def generate_badge_markdown(report: ScanReport) -> str:
    """Generate Markdown badge for README."""
    url = generate_badge_url(report)
    return f"![Architecture Qube]({url})"
