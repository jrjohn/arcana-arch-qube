"""AI semantic analyzer using Claude API."""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass

from arch_qube.rules.models import Rule, RuleResult, Violation, Severity, CheckType
from arch_qube.profiles.loader import FrameworkProfile
from arch_qube.ai.prompt_builder import build_file_prompt, build_project_prompt
from arch_qube.ai.response_parser import parse_ai_response
from arch_qube.ai.cache import get_file_hash, get_cached, set_cached


@dataclass
class AiStats:
    files_analyzed: int = 0
    api_calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def run_ai_scan(
    source_root: Path,
    profile: FrameworkProfile,
    rules: list[Rule],
    changed_files: list[Path] | None = None,
    api_key: str | None = None,
) -> tuple[list[RuleResult], AiStats]:
    """Run AI semantic analysis on files.

    Args:
        source_root: Project source root
        profile: Framework profile
        rules: Rules to check (only ai_checks are used)
        changed_files: If provided, only analyze these files (PR mode)
        api_key: Claude API key (or from ANTHROPIC_API_KEY env)

    Returns:
        (list of RuleResult, AiStats)
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return [], AiStats()

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
    except ImportError:
        return [], AiStats()

    stats = AiStats()
    results: list[RuleResult] = []

    # Collect source files
    if changed_files:
        source_files = changed_files
    else:
        source_files = []
        for ext in profile.file_extensions:
            source_files.extend(source_root.rglob(f"*{ext}"))

    for rule in rules:
        if not rule.ai_checks:
            continue
        if rule.applies_to and profile.framework not in rule.applies_to:
            continue

        all_violations: list[Violation] = []

        for ai_check in rule.ai_checks:
            if ai_check.type == "semantic_review":
                # Per-file analysis
                for fpath in source_files:
                    rel = str(fpath.relative_to(source_root))
                    layer = profile.classify_file(rel)
                    if layer is None:
                        continue

                    # Check cache
                    fhash = get_file_hash(fpath)
                    cached = get_cached(rule.id, fhash)
                    if cached is not None:
                        stats.cache_hits += 1
                        violations = [
                            Violation(
                                file=rel,
                                line=v["line"],
                                message=v["message"],
                                suggestion=v.get("suggestion", ""),
                                check_type=CheckType.AI,
                            )
                            for v in cached.get("violations", [])
                        ]
                        all_violations.extend(violations)
                        continue

                    # Read file
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue

                    # Skip very large files (> 50KB)
                    if len(content) > 50_000:
                        continue

                    # Build prompt
                    system, user = build_file_prompt(
                        rule, ai_check, Path(rel), content, profile
                    )

                    # Call Claude API
                    try:
                        response = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=1024,
                            system=system,
                            messages=[{"role": "user", "content": user}],
                        )
                        stats.api_calls += 1
                        stats.files_analyzed += 1
                        stats.input_tokens += response.usage.input_tokens
                        stats.output_tokens += response.usage.output_tokens

                        response_text = response.content[0].text
                        violations = parse_ai_response(response_text, rel)
                        all_violations.extend(violations)

                        # Cache result
                        cache_data = {
                            "violations": [
                                {"line": v.line, "message": v.message, "suggestion": v.suggestion}
                                for v in violations
                            ]
                        }
                        set_cached(rule.id, fhash, cache_data)

                    except Exception:
                        # API failure — skip this file, don't block
                        continue

        # Build RuleResult
        file_count = len(source_files)
        if file_count > 0:
            violating_files = len(set(v.file for v in all_violations))
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
            violations=all_violations,
            files_checked=len(source_files),
            check_type=CheckType.AI,
        ))

    return results, stats
