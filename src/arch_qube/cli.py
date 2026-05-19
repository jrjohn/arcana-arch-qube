"""CLI entry point for arch-qube."""
from __future__ import annotations
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from arch_qube.rules.loader import load_rules
from arch_qube.profiles.loader import load_profile
from arch_qube.scanner import run_ast_scan
from arch_qube.scoring.engine import build_report
from arch_qube.reporters.json_reporter import generate_json
from arch_qube.reporters.markdown_reporter import generate_markdown
from arch_qube.reporters.sonar_reporter import generate_sonar_issues
from arch_qube.reporters.junit_reporter import generate_junit
from arch_qube.reporters.badge_generator import generate_badge_markdown

console = Console()

# Resolve bundled rules/profiles directories
# Try repo root first (dev mode), then fallback to installed package data
_SRC_ROOT = Path(__file__).parent.parent.parent  # repo root (dev)
_PKG_DATA = Path(__file__).parent  # installed package dir

def _find_data_dir(name: str) -> Path:
    """Find rules/ or profiles/ directory.

    Lookup order (first hit wins):
      1. Bundled inside installed package (_PKG_DATA / name) — production via pip install
      2. Repo root (_SRC_ROOT / name) — dev mode
      3. Docker /app/<name>
      4. CWD / name
    """
    # 1. Installed package (pip install bundles via package-data)
    candidate = _PKG_DATA / name
    if candidate.is_dir():
        return candidate
    # 2. Repo root (dev mode)
    candidate = _SRC_ROOT / name
    if candidate.is_dir():
        return candidate
    # 3. Docker /app layout
    candidate = Path("/app") / name
    if candidate.is_dir():
        return candidate
    # 4. CWD
    candidate = Path.cwd() / name
    if candidate.is_dir():
        return candidate
    return _PKG_DATA / name  # best guess (clear path in FileNotFoundError)


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Architecture Qube — AI-powered Architecture Quality Gate."""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option("--framework", "-f", required=True, help="Framework profile name")
@click.option("--rules", "rules_dir", type=click.Path(exists=True), default=None,
              help="Rules directory (default: bundled)")
@click.option("--profiles", "profiles_dir", type=click.Path(exists=True), default=None,
              help="Profiles directory (default: bundled)")
@click.option("--threshold", type=float, default=95.0, help="Pass/fail score (default: 95)")
@click.option("--output", "-o", "output_dir", type=click.Path(), default="arch-qube-reports",
              help="Output directory")
@click.option("--format", "formats", default="json,markdown", help="Output formats (comma-separated)")
@click.option("--ci", is_flag=True, help="CI mode: exit 1 on fail, minimal output")
@click.option("--no-ai", is_flag=True, help="Skip AI semantic analysis")
@click.option("--diff-only", is_flag=True, help="Only scan changed files (git diff)")
@click.option("--base-branch", default="main", help="Base branch for diff (default: main)")
@click.option("--api-key", envvar="ANTHROPIC_API_KEY", default=None, help="Claude API key")
def scan(
    path: str,
    framework: str,
    rules_dir: str | None,
    profiles_dir: str | None,
    threshold: float,
    output_dir: str,
    formats: str,
    ci: bool,
    no_ai: bool,
    diff_only: bool,
    base_branch: str,
    api_key: str | None,
):
    """Scan a project for architecture compliance."""
    source_root = Path(path).resolve()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Resolve rule and profile directories
    r_dir = Path(rules_dir) if rules_dir else _find_data_dir("rules")
    p_dir = Path(profiles_dir) if profiles_dir else _find_data_dir("profiles")

    # Load profile
    try:
        profile = load_profile(p_dir, framework)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(2)

    # Load rules
    rules = load_rules(r_dir)
    if not rules:
        console.print("[red]Error:[/red] No rules found")
        sys.exit(2)

    # Determine effective source root
    effective_root = source_root
    for sr in profile.source_roots:
        candidate = source_root / sr
        if candidate.exists():
            effective_root = candidate
            break

    if not ci:
        console.print(f"\n[bold]Architecture Qube[/bold] scanning [cyan]{framework}[/cyan]")
        console.print(f"Source: {effective_root}")
        console.print(f"Rules: {len(rules)} loaded\n")

    # Diff mode: only scan changed files
    changed_files = None
    if diff_only:
        from arch_qube.ai.diff_extractor import get_changed_files
        changed_files = get_changed_files(
            effective_root, base_branch, profile.file_extensions
        )
        if not ci:
            console.print(f"Diff mode: {len(changed_files)} changed file(s)\n")

    # Run AST scan
    results = run_ast_scan(effective_root, profile, rules)

    # Run AI scan (unless --no-ai)
    ai_stats = None
    if not no_ai and api_key:
        from arch_qube.ai.analyzer import run_ai_scan
        if not ci:
            console.print("[dim]Running AI semantic analysis...[/dim]")
        ai_results, ai_stats = run_ai_scan(
            effective_root, profile, rules,
            changed_files=changed_files,
            api_key=api_key,
        )
        # Merge AI results: update existing rules or add new
        ast_rule_ids = {r.rule_id for r in results}
        for ai_r in ai_results:
            if ai_r.rule_id in ast_rule_ids:
                # Merge violations into existing AST result
                for existing in results:
                    if existing.rule_id == ai_r.rule_id:
                        existing.violations.extend(ai_r.violations)
                        if ai_r.violations:
                            violating = len(set(v.file for v in existing.violations))
                            if existing.files_checked > 0:
                                existing.compliance = round(
                                    ((existing.files_checked - violating) / existing.files_checked) * 100.0, 1
                                )
                        break
            else:
                results.append(ai_r)

    # Count files
    file_count = sum(
        1
        for ext in profile.file_extensions
        for _ in effective_root.rglob(f"*{ext}")
    )

    # Build report
    report = build_report(results, framework, str(effective_root), file_count, threshold)

    # Display results
    if not ci:
        _print_table(report)

    # Show AI stats
    if ai_stats and not ci and ai_stats.api_calls > 0:
        console.print(
            f"\n[dim]AI: {ai_stats.api_calls} API calls, "
            f"{ai_stats.cache_hits} cache hits, "
            f"{ai_stats.input_tokens + ai_stats.output_tokens} tokens[/dim]"
        )

    # Write outputs
    fmt_list = [f.strip() for f in formats.split(",")]
    if "json" in fmt_list:
        (out_path / "arch-qube.json").write_text(generate_json(report))
    if "markdown" in fmt_list:
        (out_path / "arch-qube.md").write_text(generate_markdown(report))
    if "sonar" in fmt_list:
        (out_path / "arch-qube-sonar.json").write_text(generate_sonar_issues(report))
    if "junit" in fmt_list:
        (out_path / "arch-qube-junit.xml").write_text(generate_junit(report))
    if "badge" in fmt_list:
        (out_path / "arch-qube-badge.md").write_text(generate_badge_markdown(report))

    # CI exit code
    if report.passed:
        if not ci:
            console.print(f"\n[green bold]PASS[/green bold] — {report.total_score}/100 ({report.grade})")
        sys.exit(0)
    else:
        if not ci:
            console.print(f"\n[red bold]FAIL[/red bold] — {report.total_score}/100 ({report.grade})")
            console.print(f"  Threshold: {threshold}, Violations: {report.total_violations}")
        sys.exit(1)


def _print_table(report):
    """Print a rich table of results."""
    table = Table(title="Architecture Qube Results")
    table.add_column("Rule", style="cyan")
    table.add_column("Severity", justify="center")
    table.add_column("Compliance", justify="right")
    table.add_column("Status", justify="center")

    for r in sorted(report.rule_results, key=lambda x: x.compliance):
        sev_color = {"critical": "red", "major": "yellow", "minor": "blue", "info": "dim"}.get(
            r.severity.value, "white"
        )
        status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        table.add_row(
            r.rule_name,
            f"[{sev_color}]{r.severity.value}[/{sev_color}]",
            f"{r.compliance:.0f}%",
            status,
        )

    console.print(table)


_PRE_COMMIT_HOOK = """\
#!/bin/sh
# Architecture Qube pre-commit hook
arch-qube scan . --framework {framework} --no-ai --ci --diff-only
"""

_ARCH_QUBE_CONFIG = """\
# arch-qube.yaml — project-level configuration
framework: {framework}
threshold: 95
# rules_dir: ./custom-rules    # uncomment to add custom rules
# no_ai: true                  # uncomment to disable AI analysis
"""

FRAMEWORKS = [
    "angular", "react", "vue",
    "ios", "android", "harmonyos", "windows",
    "springboot", "python", "go", "rust", "nodejs",
    "stm32", "esp32",
]


@main.command()
@click.option("--framework", "-f", required=True,
              type=click.Choice(FRAMEWORKS, case_sensitive=False),
              help="Framework profile")
@click.option("--hook", is_flag=True, help="Also install git pre-commit hook")
def init(framework: str, hook: bool):
    """Initialize Architecture Qube in a project."""
    # Write arch-qube.yaml
    config_path = Path("arch-qube.yaml")
    config_path.write_text(_ARCH_QUBE_CONFIG.format(framework=framework))
    console.print(f"[green]Created[/green] {config_path}")

    # Add to .gitignore
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        if "arch-qube-reports" not in content:
            with open(gitignore, "a") as f:
                f.write("\n# Architecture Qube\narch-qube-reports/\n.arch-qube-cache/\n")
            console.print(f"[green]Updated[/green] .gitignore")
    else:
        gitignore.write_text("arch-qube-reports/\n.arch-qube-cache/\n")
        console.print(f"[green]Created[/green] .gitignore")

    # Install pre-commit hook
    if hook:
        hook_dir = Path(".git/hooks")
        if hook_dir.exists():
            hook_path = hook_dir / "pre-commit"
            hook_path.write_text(_PRE_COMMIT_HOOK.format(framework=framework))
            hook_path.chmod(0o755)
            console.print(f"[green]Installed[/green] pre-commit hook ({framework})")
        else:
            console.print("[yellow]Warning:[/yellow] .git/hooks not found — not a git repo?")

    console.print(f"\n[bold]Ready![/bold] Run: arch-qube scan . -f {framework}")
