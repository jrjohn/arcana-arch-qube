"""2026-11-17: 14 domain crates matched no layer path, so no rule examined them and the scan said
99.5 PASS. arch-qube.yaml `layer_paths` lets a project put such code under a layer — only as a
fallback, so it can add code to the rules but never move code out of its path-given layer."""
import pytest
from pathlib import Path

from arch_qube.profiles.loader import apply_project_layers, find_project_config, load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import run_ast_scan

PROFILES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"


def _profile():
    return load_profile(PROFILES_DIR, "rust")


def _cfg(tmp_path, body):
    (tmp_path / ".git").mkdir(exist_ok=True)
    p = tmp_path / "arch-qube.yaml"
    p.write_text(body)
    return p


def test_unlayered_crate_gets_the_declared_layer(tmp_path):
    prof = _profile()
    assert prof.classify_specific("vault-index/src/search.rs") is None
    apply_project_layers(prof, _cfg(tmp_path, "layer_paths:\n  service: [vault-index]\n"))
    assert prof.classify_specific("vault-index/src/search.rs") == "service"


def test_built_in_layer_wins_over_declared_one(tmp_path):
    prof = _profile()
    apply_project_layers(prof, _cfg(tmp_path, "layer_paths:\n  service: [vault-index/]\n"))
    assert prof.classify_specific("vault-index/src/repository/store.rs") == "repository"


def test_unknown_layer_is_an_error_not_a_silent_skip(tmp_path):
    with pytest.raises(ValueError, match="unknown layer"):
        apply_project_layers(_profile(), _cfg(tmp_path, "layer_paths:\n  servce: [x/]\n"))


def test_config_found_above_scanned_dir_but_not_past_repo_root(tmp_path):
    cfg = _cfg(tmp_path, "layer_paths: {}\n")
    (tmp_path / "crates").mkdir()
    assert find_project_config(tmp_path / "crates") == cfg
    inner = tmp_path / "sub"
    (inner / ".git").mkdir(parents=True)
    assert find_project_config(inner) is None


def test_declared_service_crate_is_checked_by_service_rules(tmp_path):
    # 對照組:沒宣告時這段 SQL 沒人看;宣告成 service 後 service-no-db 抓到。
    # 跟 Desktop KM 一樣:範本 crate 有分層(所以專案不算「整個未分層」),domain crate 沒有。
    import shutil
    shutil.copytree(Path(__file__).parent / "fixtures" / "rust_layered_plus_flat", tmp_path,
                    dirs_exist_ok=True)
    shutil.rmtree(tmp_path / "crates" / "vault-web")
    src = tmp_path / "crates" / "vault-index" / "src"
    src.mkdir(parents=True)
    (src / "search.rs").write_text(
        'use sqlx::PgPool;\npub async fn f(p: &PgPool) { sqlx::query("SELECT 1 FROM t").execute(p).await; }\n')
    root = tmp_path / "crates"
    rules = load_rules(RULES_DIR)

    def db_hits(prof):
        res = {r.rule_id: r for r in run_ast_scan(root, prof, rules)}
        return [v for v in res["service-no-db"].violations if v.file.endswith("search.rs")]

    assert db_hits(_profile()) == []
    prof = _profile()
    apply_project_layers(prof, _cfg(tmp_path, "layer_paths:\n  service: [vault-index]\n"))
    assert db_hits(prof)


def test_dip_ports_is_project_opt_in(tmp_path):
    prof = _profile()
    assert prof.dip_ports == []
    applied = apply_project_layers(prof, _cfg(tmp_path, "dip_ports: [repository]\n"))
    assert prof.dip_ports == ["repository"] and applied["dip_ports"] == ["repository"]
    with pytest.raises(ValueError, match="dip_ports"):
        apply_project_layers(_profile(), _cfg(tmp_path, "dip_ports: [repo]\n"))

