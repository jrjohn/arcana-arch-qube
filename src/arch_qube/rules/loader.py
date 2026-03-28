"""Load YAML rule definitions from directory."""
from __future__ import annotations
from pathlib import Path
import yaml
from .models import Rule, Severity, AstCheck, AiCheck


def load_rules(rules_dir: Path, category_filter: str | None = None) -> list[Rule]:
    """Load all YAML rules from directory tree."""
    rules: list[Rule] = []
    for yaml_file in sorted(rules_dir.rglob("*.yaml")):
        rule = _parse_rule_file(yaml_file)
        if rule and (category_filter is None or rule.category == category_filter):
            rules.append(rule)
    return rules


def _parse_rule_file(path: Path) -> Rule | None:
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data or "id" not in data:
        return None

    ast_checks = [
        AstCheck(
            type=c.get("type", ""),
            check=c.get("check", ""),
            description=c.get("description", ""),
            params=c.get("params", {}),
        )
        for c in data.get("ast_checks", [])
    ]

    ai_checks = [
        AiCheck(
            type=c.get("type", ""),
            prompt_template=c.get("prompt_template", ""),
            description=c.get("description", ""),
        )
        for c in data.get("ai_checks", [])
    ]

    scoring = data.get("scoring", {})

    return Rule(
        id=data["id"],
        name=data.get("name", data["id"]),
        description=data.get("description", ""),
        category=data.get("category", "common"),
        severity=Severity(data.get("severity", "major")),
        weight=data.get("weight", 5),
        applies_to=data.get("applies_to", []),
        ast_checks=ast_checks,
        ai_checks=ai_checks,
        pass_threshold=scoring.get("pass_threshold", 100.0),
    )
