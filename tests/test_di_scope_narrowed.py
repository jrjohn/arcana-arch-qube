"""0.5.7: rule 03 "Only DI Container Imports Impl" had DI scopes far wider than the templates'
composition roots (harmonyos core/sync/** and data/repository/**, android core/**, python
**/__init__.py, go **/grpc/**, rust **/mod.rs ...), so an Impl import planted there scored 100.
di_container_files is now only the composition root; the old globs moved to wiring_files, which
the layer / boundary / impl-location checks still honour but rule 03 does not.

Control (a) -- the real templates score the same on rule 03 -- is run against template clones
outside this suite; control (b) -- a planted Impl import outside the root IS reported -- is here."""
from pathlib import Path

import pytest

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import run_ast_scan
from arch_qube.scanners.import_graph import ImportEdge, check_impl_import_restriction

PROFILES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES_DIR = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"


def _rule03(root: Path, framework: str):
    results = run_ast_scan(root, load_profile(PROFILES_DIR, framework), load_rules(RULES_DIR))
    return {r.rule_id: r for r in results}["impl-import-restriction"]


def _write(root: Path, rel: str, text: str) -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


# (framework, planted source file outside the composition root, Impl import, a real root file)
PLANTED = [
    ("harmonyos", "core/sync/SyncManager.ets", "../../data/repository/UserRepositoryImpl",
     "core/di/AppContainer.ets"),
    ("harmonyos", "data/repository/UserRepository.ets", "../api/impl/UserApiServiceImpl",
     "core/di/modules.ets"),
    ("harmonyos", "core/http/ApiClient.ets", "../logging/impl/LoggerServiceImpl",
     "core/di/ContainerInitializer.ets"),
    ("android", "com/example/arcana/core/sync/Syncer.kt",
     "com.example.arcana.data.repository.impl.UserRepositoryImpl",
     "com/example/arcana/di/RepositoryModule.kt"),
    ("android", "com/example/arcana/data/worker/SyncWorker.kt",
     "com.example.arcana.domain.service.impl.UserServiceImpl",
     "com/example/arcana/di/ServiceModule.kt"),
    ("python", "controllers/__init__.py", "app.services.impl.user_service_impl",
     "di_container.py"),
    ("python", "tasks/cleanup.py", "app.repositories.impl.user_repository_impl",
     "communication/factory.py"),
    ("go", "controller/grpc/service/user_service.go",
     "github.com/x/internal/domain/service/impl/user_service_impl", "di/service.go"),
    ("rust", "arcana-api/src/handlers/mod.rs", "arcana-service/src/impl/user_service_impl",
     "arcana-server/src/di.rs"),
    ("rust-desktop", "crates/arcana-ui/src/lib.rs",
     "crates/arcana-infra/src/impl/settings_store_impl", "crates/arcana-infra/src/wiring.rs"),
]


@pytest.mark.parametrize("fw,src,target,root", PLANTED)
def test_impl_import_outside_composition_root_is_reported(fw, src, target, root):
    p = load_profile(PROFILES_DIR, fw)
    assert p.is_di_container(root), f"{fw}: {root} is the template's composition root"
    assert not p.is_di_container(src), f"{fw}: {src} must not count as a DI container"
    v = check_impl_import_restriction([ImportEdge(src, target, None, None, 7)], p)
    assert [(x.file, x.line) for x in v] == [(src, 7)]
    # the composition root itself may still import it
    assert check_impl_import_restriction([ImportEdge(root, target, None, None, 7)], p) == []


@pytest.mark.parametrize("fw,src", [(fw, src) for fw, src, _, _ in PLANTED
                                    if fw in ("harmonyos", "android", "python", "go")
                                    # android "core/**" never matched com/example/... paths
                                    and not src.endswith("Syncer.kt")])
def test_old_globs_still_exempt_from_the_other_rules(fw, src):
    """The globs that used to be DI scope still silence layer-direction / boundary / impl-location,
    so the templates do not go red on rules this fix did not touch."""
    assert load_profile(PROFILES_DIR, fw).is_wiring_file(src)


def test_harmonyos_end_to_end_core_sync_and_data_repository(tmp_path):
    ets = tmp_path / "entry/src/main/ets"
    _write(ets, "data/repository/impl/UserRepositoryImpl.ets", "export class UserRepositoryImpl {}\n")
    _write(ets, "core/di/AppContainer.ets",
           "import { UserRepositoryImpl } from '../../data/repository/impl/UserRepositoryImpl';\n")
    _write(ets, "core/sync/SyncManager.ets",
           "import { UserRepositoryImpl } from '../../data/repository/impl/UserRepositoryImpl';\n")
    _write(ets, "data/repository/Other.ets",
           "import { UserRepositoryImpl } from './impl/UserRepositoryImpl';\n")
    _write(ets, "domain/Ok.ets", "export const x = 1;\n")
    r = _rule03(ets, "harmonyos")
    flagged = sorted(v.file for v in r.violations)
    assert flagged == ["core/sync/SyncManager.ets", "data/repository/Other.ets"]


def test_ios_impl_reference_outside_di_is_reported(tmp_path):
    """Swift files never import each other, so the import graph saw nothing and ios scored 100."""
    src = tmp_path / "Sources"
    _write(src, "ArcanaData/Repository/impl/UserRepositoryImpl.swift",
           "final class UserRepositoryImpl: UserRepository {\n  init() {}\n}\n")
    _write(src, "ArcanaCore/DI/AppDependencies.swift", "let repo = UserRepositoryImpl()\n")
    _write(src, "ArcanaPresentation/Screens/UserViewModel.swift",
           "// UserRepositoryImpl in a comment is fine\n"
           "let s = \"UserRepositoryImpl in a string is fine\"\n"
           "guard let r = repo as? UserRepositoryImpl else { return }\n")
    r = _rule03(src, "ios")
    assert r.evaluated
    assert [(v.file, v.line) for v in r.violations] == [
        ("ArcanaPresentation/Screens/UserViewModel.swift", 3)]


def test_ios_no_impl_reference_is_clean(tmp_path):
    src = tmp_path / "Sources"
    _write(src, "ArcanaData/Repository/impl/UserRepositoryImpl.swift",
           "final class UserRepositoryImpl: UserRepository {}\n")
    _write(src, "ArcanaCore/DI/AppDependencies.swift", "let repo = UserRepositoryImpl()\n")
    _write(src, "ArcanaPresentation/Screens/UserViewModel.swift", "let r: UserRepository = repo\n")
    assert _rule03(src, "ios").violations == []


def test_rust_pub_use_raw_impl_reexport_is_structure(tmp_path):
    """`pub use r#impl::FooImpl;` in lib.rs re-exports a child module; it is not a DI breach,
    which is why lib.rs / mod.rs no longer need to be DI containers."""
    crates = tmp_path / "crates"
    _write(crates, "arcana-service/Cargo.toml", "[package]\nname = \"arcana-service\"\n")
    _write(crates, "arcana-service/src/lib.rs", "mod r#impl;\npub use r#impl::UserServiceImpl;\n")
    _write(crates, "arcana-service/src/impl/mod.rs", "mod user_service_impl;\n")
    _write(crates, "arcana-service/src/impl/user_service_impl.rs", "pub struct UserServiceImpl;\n")
    _write(crates, "arcana-service/src/service.rs", "pub trait UserService {}\n")
    assert _rule03(crates, "rust").violations == []
