"""Main scanner — orchestrates AST checks against loaded rules."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from arch_qube.profiles.loader import FrameworkProfile
from arch_qube.rules.models import AstCheck, Rule, RuleResult, CheckType, Violation
from arch_qube.scanners.import_graph import (
    ImportEdge,
    build_import_graph,
    check_layer_direction,
    check_impl_import_restriction,
)
from arch_qube.scanners.file_structure import (
    check_impl_colocation,
    check_impl_naming,
    check_layer_exists,
)
from arch_qube.scanners import content_checks as cc


@dataclass
class ScanContext:
    source_root: Path
    profile: FrameworkProfile
    edges: list[ImportEdge]
    project_root: Path  # the scanned path itself (source_root may be a sub-dir such as src/)


Handler = Callable[[ScanContext, AstCheck], list[Violation]]

# Every check name a rule YAML may use, mapped to the code that performs it. A name missing from
# this table is NOT silently treated as "no violations": the rule is reported as not evaluated
# and excluded from the score (see RuleResult.evaluated).
HANDLERS: dict[str, Handler] = {
    "no_upward_imports": lambda c, _: check_layer_direction(c.edges, c.profile),
    "no_skip_imports": lambda c, _: check_layer_direction(c.edges, c.profile),
    "impl_import_only_di": lambda c, _: check_impl_import_restriction(c.edges, c.profile),
    "impl_in_subdir": lambda c, _: check_impl_colocation(c.source_root, c.profile),
    "impl_naming_convention": lambda c, _: check_impl_naming(c.source_root, c.profile),
    "layer_dirs_exist": lambda c, _: check_layer_exists(c.source_root, c.profile),
    "boundary_uses_dto": cc.check_boundary_uses_dto,
    "boundary_complexity": cc.check_boundary_complexity,
    "test_dir_exists": cc.check_test_dir_exists,
    "view_no_service_import": cc.check_view_no_service_import,
    "navgraph_exists": cc.check_navgraph_exists,
    "no_db_in_service": cc.check_no_db_in_service,
    "transaction_placement": cc.check_transaction_placement,
}


def run_ast_scan(
    source_root: Path,
    profile: FrameworkProfile,
    rules: list[Rule],
    project_root: Path | None = None,
) -> list[RuleResult]:
    """Run all AST-based checks and return results per rule."""
    results: list[RuleResult] = []

    # Count source files
    file_count = sum(
        1
        for ext in profile.file_extensions
        for _ in source_root.rglob(f"*{ext}")
    )

    # Build import graph once — shared across import-based rules
    ctx = ScanContext(source_root, profile, build_import_graph(source_root, profile),
                      project_root or source_root)

    for rule in rules:
        # Skip rules that don't apply to this framework
        if rule.applies_to and profile.framework not in rule.applies_to:
            continue

        violations: list[Violation] = []
        ran = 0
        unimplemented: list[str] = []

        for check in rule.ast_checks:
            handler = HANDLERS.get(check.check)
            if handler is None:
                unimplemented.append(check.check)
                continue
            violations.extend(handler(ctx, check))
            ran += 1

        # Deduplicate violations by (file, line, message)
        seen = set()
        unique_violations = []
        for v in violations:
            key = (v.file, v.line, v.message)
            if key not in seen:
                seen.add(key)
                unique_violations.append(v)

        # Calculate compliance. A boolean rule ("a test suite exists") is all or nothing; scoring
        # it by violating-file share would turn "missing" into ~99%.
        if rule.scoring_method == "boolean":
            compliance = 0.0 if unique_violations else 100.0
        elif file_count > 0:
            violating_files = len(set(v.file for v in unique_violations))
            compliance = ((file_count - violating_files) / file_count) * 100.0
        else:
            compliance = 100.0

        results.append(RuleResult(
            rule_id=rule.id,
            rule_name=rule.name,
            category=rule.category,
            severity=rule.severity,
            weight=rule.weight,
            compliance=round(compliance, 1),
            violations=unique_violations,
            files_checked=file_count,
            check_type=CheckType.AST,
            evaluated=ran > 0,
            unimplemented_checks=unimplemented,
        ))

    return results
