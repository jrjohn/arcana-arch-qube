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


# A handler returns the violations it found, or None when its check cannot apply to this project
# (e.g. module boundaries in a project with no modules) — the rule is then "not evaluated".
Handler = Callable[[ScanContext, AstCheck], "list[Violation] | None"]

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
    "module_public_api_only": cc.check_module_public_api_only,
}


# Checks that only mean something when files are classified into layers. In a backend project with
# no recognisable layers they find nothing to look at and used to report "0 violations" = 100%
# (2026-11-16: a flat crate with raw SQL in db.rs scored 100 PASS). They are "not evaluated" then.
_LAYER_DEPENDENT = {
    "no_upward_imports", "no_skip_imports", "impl_import_only_di", "impl_in_subdir",
    "boundary_uses_dto", "boundary_complexity", "view_no_service_import",
    "transaction_placement", "module_public_api_only",
}
_BACKEND_CHAIN = ("controller", "service", "repository", "dao")


def detected_backend_layers(source_root: Path, profile: FrameworkProfile) -> set[str]:
    """Backend chain layers that at least one source file is classified into."""
    found: set[str] = set()
    for ext in profile.file_extensions:
        for fpath in profile.source_files(source_root, ext):
            layer = profile.classify_specific(str(fpath.relative_to(source_root)))
            if layer in _BACKEND_CHAIN:
                found.add(layer)
    return found


def is_unlayered(source_root: Path, profile: FrameworkProfile) -> bool:
    """A backend project in which no file is classified into any chain layer is not layered at all.
    (Fewer-than-two would also catch the single-layer fixtures that content rules are tested on.)"""
    return profile.category == "backend" and not detected_backend_layers(source_root, profile)


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
        for _ in profile.source_files(source_root, ext)
    )

    # Build import graph once — shared across import-based rules
    ctx = ScanContext(source_root, profile, build_import_graph(source_root, profile),
                      project_root or source_root)
    unlayered = is_unlayered(source_root, profile)

    for rule in rules:
        # Skip rules that don't apply to this framework
        if rule.applies_to and profile.framework not in rule.applies_to:
            continue

        violations: list[Violation] = []
        ran = 0
        declined = 0
        unimplemented: list[str] = []

        for check in rule.ast_checks:
            handler = HANDLERS.get(check.check)
            if handler is None:
                unimplemented.append(check.check)
                continue
            if unlayered and check.check in _LAYER_DEPENDENT:
                declined += 1  # nothing is classified into layers: this check would look at nothing
                continue
            if unlayered and check.check == "layer_dirs_exist":
                found = [Violation(
                    file=".", line=0,
                    message="未分層：找不到 controller/service/repository 任何一層 (no backend layers "
                            f"detected; found {sorted(detected_backend_layers(source_root, profile)) or 'none'})",
                    suggestion="Split the code into controller -> service -> repository -> dao layers.",
                    check_type=CheckType.AST)]
                violations.extend(found)
                ran += 1
                continue
            if unlayered and check.check == "no_db_in_service":
                found = cc.check_db_outside_repository(ctx, check)
            else:
                found = handler(ctx, check)
            if found is None:  # the check does not apply to this project (e.g. it has no modules)
                declined += 1
                continue
            violations.extend(found)
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
        if unlayered and any(c.check == "layer_dirs_exist" for c in rule.ast_checks):
            compliance = 0.0  # the layer chain does not exist at all
        elif rule.scoring_method == "boolean":
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
            not_applicable=ran == 0 and declined > 0,
        ))

    return results
