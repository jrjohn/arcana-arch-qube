"""Rule data models."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class CheckType(Enum):
    AST = "ast"
    AI = "ai"


@dataclass
class Violation:
    file: str
    line: int
    message: str
    suggestion: str = ""
    check_type: CheckType = CheckType.AST


@dataclass
class RuleResult:
    rule_id: str
    rule_name: str
    category: str
    severity: Severity
    weight: int
    compliance: float  # 0.0 - 100.0
    violations: list[Violation] = field(default_factory=list)
    files_checked: int = 0
    check_type: CheckType = CheckType.AST
    # False when no check for this rule actually ran (no AST check this scanner implements, and
    # no AI result). Such a rule says nothing about the code, so it is excluded from the score
    # instead of counting as 100% compliant — which is what silently happened before 2026-10-02:
    # 13 of 21 rules were never checked yet contributed ~55 of every 100 points.
    evaluated: bool = True
    # check names declared in the rule YAML that this scanner has no implementation for
    unimplemented_checks: list[str] = field(default_factory=list)

    @property
    def weighted_score(self) -> float:
        return self.weight * (self.compliance / 100.0)

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0


@dataclass
class AstCheck:
    type: str
    check: str
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class AiCheck:
    type: str
    prompt_template: str
    description: str = ""


@dataclass
class Rule:
    id: str
    name: str
    description: str
    category: str  # common, client, backend
    severity: Severity
    weight: int
    applies_to: list[str] = field(default_factory=list)  # empty = all frameworks
    ast_checks: list[AstCheck] = field(default_factory=list)
    ai_checks: list[AiCheck] = field(default_factory=list)
    pass_threshold: float = 100.0


@dataclass
class ScanReport:
    framework: str
    source_root: str
    files_scanned: int
    total_score: float
    grade: str
    passed: bool
    threshold: float
    rule_results: list[RuleResult] = field(default_factory=list)

    @property
    def evaluated_results(self) -> list[RuleResult]:
        return [r for r in self.rule_results if r.evaluated]

    @property
    def not_evaluated(self) -> list[RuleResult]:
        return [r for r in self.rule_results if not r.evaluated]

    @property
    def critical_violations(self) -> int:
        return sum(
            len(r.violations)
            for r in self.rule_results
            if r.severity == Severity.CRITICAL
        )

    @property
    def total_violations(self) -> int:
        return sum(len(r.violations) for r in self.rule_results)
