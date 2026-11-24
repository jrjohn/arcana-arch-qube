"""2026-11-24: rule 03 "Only DI Container Imports Impl" could never fire on ESP32.

The esp32 profile listed `main/**` (every ESP-IDF source lives in main/) and `**/*Impl.cpp` as DI
containers, and the check itself exempted any source with "impl" in its path. In
arcana-embedded-esp32, HttpUploadServiceImpl.cpp includes AtsStorageServiceImpl.hpp,
RegistrationServiceImpl.hpp and IoServiceImpl.hpp (a breach of its AGENTS.md R2) and the rule
still scored 100. An Impl may include its own header; only the composition root may include
other Impls."""
from pathlib import Path

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import run_ast_scan
from arch_qube.scanners.import_graph import ImportEdge, check_impl_import_restriction

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"


def _rule03():
    results = run_ast_scan(FIXTURES / "esp32_impl_di", load_profile(PROFILES_DIR, "esp32"),
                           load_rules(RULES_DIR))
    return {r.rule_id: r for r in results}["impl-import-restriction"]


def test_impl_including_another_impl_is_reported():
    r = _rule03()
    assert r.evaluated
    hits = [(v.file, v.message) for v in r.violations]
    assert any(f.endswith("IoServiceImpl.cpp") and "LedServiceImpl" in m for f, m in hits), hits
    assert r.compliance < 100


def test_impl_including_its_own_header_is_not_reported():
    r = _rule03()
    own = [v for v in r.violations
           if v.file.endswith("LedServiceImpl.cpp")
           or (v.file.endswith("IoServiceImpl.cpp") and "IoServiceImpl" in v.message)]
    assert own == []


def test_app_container_including_impls_is_not_reported():
    r = _rule03()
    assert not [v for v in r.violations if "AppContainer" in v.file or v.file.endswith("App.cpp")]
    assert len(r.violations) == 1


def test_esp32_di_containers_are_only_the_composition_root():
    p = load_profile(PROFILES_DIR, "esp32")
    assert p.is_di_container("share/AppContainer.cpp")
    assert p.is_di_container("App.cpp")
    assert not p.is_di_container("share/service/impl/HttpUploadServiceImpl.cpp")
    assert not p.is_di_container("main/share/view/main/MainViewModel.hpp")


def test_impl_dir_helpers_are_not_other_implementations():
    """Go/Java impl packages import their own private helpers (impl/mongo/document,
    impl/mybatis/mapper) and libraries ship org.quartz.impl.*: none of these is another Impl."""
    p = load_profile(PROFILES_DIR, "go")
    edges = [
        ImportEdge("domain/dao/impl/mongo/user_dao_impl.go",
                   "github.com/x/internal/domain/dao/impl/mongo/document", "dao", "dao", 12),
        ImportEdge("domain/dao/impl/mongo/user_dao_impl.go",
                   "github.com/x/internal/domain/dao/impl/mongo/plugin_dao_impl", "dao", "dao", 13),
    ]
    v = check_impl_import_restriction(edges, p)
    assert [x.line for x in v] == [13]

