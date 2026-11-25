"""0.5.7: `--ci` FAIL printed nothing (CI logs never said why) and `--version` printed a
hardcoded 0.1.0."""
import re
from pathlib import Path

import tomllib
from click.testing import CliRunner

import arch_qube
from arch_qube.cli import format_ci_failure, main
from arch_qube.rules.models import RuleResult, ScanReport, Severity, Violation

ROOT = Path(__file__).parent.parent


def _packaged_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_version_is_the_packaged_version():
    out = CliRunner().invoke(main, ["--version"])
    assert out.exit_code == 0
    assert out.output.strip() == f"arch-qube, version {_packaged_version()}"
    assert arch_qube.__version__ == _packaged_version() == arch_qube.package_version()


def _rule(rid, sev, n, compliance=90.0):
    return RuleResult(rule_id=rid, rule_name=rid.title(), category="common", severity=sev,
                      weight=3, compliance=compliance,
                      violations=[Violation(file=f"src/{rid}.py", line=i + 1, message=f"m{i}")
                                  for i in range(n)], files_checked=10)


def test_ci_failure_summary_lists_critical_first_and_caps_locations():
    report = ScanReport(framework="python", source_root="app", files_scanned=10, total_score=91.2,
                        grade="A-", passed=False, threshold=95.0, rule_results=[
                            _rule("minor-thing", Severity.MINOR, 1),
                            _rule("major-thing", Severity.MAJOR, 5),
                            _rule("crit-thing", Severity.CRITICAL, 1),
                            _rule("clean", Severity.CRITICAL, 0, 100.0),
                        ])
    text = format_ci_failure(report, max_locations=2)
    lines = text.splitlines()
    assert lines[0].startswith("arch-qube FAIL: 91.2/100 (A-), threshold 95.0")
    assert "score 91.2 < threshold 95.0" in text and "1 critical rule(s)" in text
    heads = [ln for ln in lines if ln.startswith("[")]
    assert [h.split("]")[0] for h in heads] == ["[CRITICAL", "[MAJOR", "[MINOR"]
    assert "clean" not in text
    assert "src/major-thing.py:1  m0" in text and "src/major-thing.py:2  m1" in text
    assert "src/major-thing.py:3" not in text and "... and 3 more" in text
    assert "\x1b[" not in text  # plain text for CI logs


def _write(root: Path, rel: str, text: str):
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


def _harmony_project(tmp_path: Path, bad: bool) -> Path:
    ets = tmp_path / "entry/src/main/ets"
    _write(ets, "data/repository/impl/UserRepositoryImpl.ets", "export class UserRepositoryImpl {}\n")
    _write(ets, "core/di/AppContainer.ets",
           "import { UserRepositoryImpl } from '../../data/repository/impl/UserRepositoryImpl';\n")
    _write(ets, "domain/repository/UserRepository.ets", "export interface UserRepository {}\n")
    _write(ets, "presentation/viewmodel/UserViewModel.ets",
           ("import { UserRepositoryImpl } from '../../data/repository/impl/UserRepositoryImpl';\n"
            if bad else "import { UserRepository } from '../../domain/repository/UserRepository';\n"))
    return tmp_path


def test_ci_fail_prints_why(tmp_path):
    proj = _harmony_project(tmp_path / "p", bad=True)
    out = CliRunner().invoke(main, ["scan", str(proj), "-f", "harmonyos", "--no-ai", "--ci",
                                    "-o", str(tmp_path / "out")])
    assert out.exit_code == 1
    assert out.output.startswith("arch-qube FAIL: ")
    assert re.search(r"\[CRITICAL\] Only DI Container Imports Impl", out.output)
    assert "presentation/viewmodel/UserViewModel.ets:1" in out.output


def test_ci_pass_stays_quiet(tmp_path):
    proj = _harmony_project(tmp_path / "p", bad=False)
    out = CliRunner().invoke(main, ["scan", str(proj), "-f", "harmonyos", "--no-ai", "--ci",
                                    "--threshold", "0", "-o", str(tmp_path / "out")])
    assert out.exit_code == 0, out.output
    assert out.output == ""
