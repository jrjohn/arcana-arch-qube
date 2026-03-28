"""Main scanner — orchestrates AST checks against loaded rules."""
from __future__ import annotations
from pathlib import Path

from arch_qube.profiles.loader import FrameworkProfile
from arch_qube.rules.models import Rule, RuleResult, Severity, CheckType
from arch_qube.scanners.import_graph import (
    build_import_graph,
    check_layer_direction,
    check_impl_import_restriction,
)
from arch_qube.scanners.file_structure import (
    check_impl_colocation,
    check_impl_naming,
    check_layer_exists,
)


def run_ast_scan(
    source_root: Path,
    profile: FrameworkProfile,
    rules: list[Rule],
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
    edges = build_import_graph(source_root, profile)

    for rule in rules:
        # Skip rules that don't apply to this framework
        if rule.applies_to and profile.framework not in rule.applies_to:
            continue

        violations = []

        for check in rule.ast_checks:
            if check.check == "no_upward_imports":
                violations.extend(check_layer_direction(edges, profile))
            elif check.check == "no_skip_imports":
                violations.extend(check_layer_direction(edges, profile))
            elif check.check == "impl_import_only_di":
                violations.extend(check_impl_import_restriction(edges, profile))
            elif check.check == "impl_in_subdir":
                violations.extend(check_impl_colocation(source_root, profile))
            elif check.check == "impl_naming_convention":
                violations.extend(check_impl_naming(source_root, profile))
            elif check.check == "layer_dirs_exist":
                violations.extend(check_layer_exists(source_root, profile))

        # Deduplicate violations by (file, line, message)
        seen = set()
        unique_violations = []
        for v in violations:
            key = (v.file, v.line, v.message)
            if key not in seen:
                seen.add(key)
                unique_violations.append(v)

        # Calculate compliance
        if file_count > 0:
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
        ))

    return results
