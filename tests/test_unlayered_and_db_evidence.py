"""2026-11-16: a flat Rust crate (no controller/service/repository) with raw SQL in db.rs scored
100 PASS — every layer rule looked at nothing. And `exec.execute(` on an MCP tool executor was
reported as database access in the service layer."""
from pathlib import Path

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import run_ast_scan
from arch_qube.scoring.engine import build_report

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"


def _scan(name: str):
    profile = load_profile(PROFILES_DIR, "rust")
    rules = load_rules(RULES_DIR)
    root = FIXTURES / name
    return {r.rule_id: r for r in run_ast_scan(root, profile, rules)}


def test_flat_crate_fails_layer_chain_instead_of_free_hundred():
    res = _scan("rust_flat")
    chain = res["controller-service-repo-dao"]
    assert chain.evaluated and chain.compliance == 0.0
    assert any("未分層" in v.message for v in chain.violations)


def test_flat_crate_flags_raw_sql_outside_repository():
    db = _scan("rust_flat")["service-no-db"]
    assert db.evaluated
    assert any(v.file.endswith("db.rs") for v in db.violations)
    assert not any(v.file.endswith("dealer.rs") for v in db.violations)


def test_flat_crate_layer_dependent_rules_are_not_evaluated():
    res = _scan("rust_flat")
    for rid in ("layer-direction", "controller-no-dao", "transaction-at-service",
                "repository-no-service", "impl-import-restriction"):
        if rid in res:
            assert res[rid].evaluated is False, rid


def test_flat_crate_report_fails():
    profile = load_profile(PROFILES_DIR, "rust")
    results = run_ast_scan(FIXTURES / "rust_flat", profile, load_rules(RULES_DIR))
    report = build_report(results, framework="rust", source_root=str(FIXTURES / "rust_flat"),
                          files_scanned=3, threshold=95.0)
    assert not report.passed


def test_tool_executor_execute_is_not_database_access():
    db = _scan("rust_exec_service")["service-no-db"]
    assert db.evaluated and db.violations == []


def test_real_sqlx_in_service_is_flagged():
    db = _scan("rust_sqlx_service")["service-no-db"]
    assert any(v.file.endswith("user_service.rs") for v in db.violations)
