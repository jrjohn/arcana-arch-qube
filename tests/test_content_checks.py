"""Each new check gets a pair: a real violation it must catch, and a look-alike it must leave alone.
The second half matters as much as the first — three of these guard critical rules, where a single
false positive fails a repo's whole gate."""
from pathlib import Path

from arch_qube.profiles.loader import load_profile
from arch_qube.rules.loader import load_rules
from arch_qube.scanner import run_ast_scan

PROFILES = Path(__file__).parent.parent / "src" / "arch_qube" / "profiles"
RULES = Path(__file__).parent.parent / "src" / "arch_qube" / "rules"


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def _scan(root: Path, framework: str, rule_id: str, src: str = "src"):
    rules = [r for r in load_rules(RULES) if r.id == rule_id]
    [res] = run_ast_scan(root / src, load_profile(PROFILES, framework), rules, project_root=root)
    assert res.evaluated, f"{rule_id} did not run"
    return res


# ---- 05 dto-entity-separation ----

def test_controller_importing_entity_is_caught(tmp_path):
    _write(tmp_path, {"src/main/java/com/a/controller/UserController.java":
                      "import com.a.domain.entity.User;\nclass UserController {}\n"})
    res = _scan(tmp_path, "springboot", "dto-entity-separation", "src/main/java")
    assert len(res.violations) == 1


def test_controller_importing_dto_is_fine(tmp_path):
    _write(tmp_path, {"src/main/java/com/a/controller/UserController.java":
                      "import com.a.dto.UserDto;\nimport com.a.service.UserService;\n"
                      "import org.springframework.http.ResponseEntity;\nclass UserController {}\n"})
    assert _scan(tmp_path, "springboot", "dto-entity-separation", "src/main/java").violations == []


def test_entity_rule_is_backend_only():
    rule = next(r for r in load_rules(RULES) if r.id == "dto-entity-separation")
    assert set(rule.applies_to) == {"springboot", "python", "go", "rust", "nodejs"}


# ---- 06 no-business-logic-in-boundary ----

def test_long_controller_method_is_caught(tmp_path):
    body = "\n".join(f"    int x{i} = {i};" for i in range(30))
    _write(tmp_path, {"src/main/java/com/a/controller/C.java":
                      f"class C {{\n  public int handle(int a) {{\n{body}\n    return a;\n  }}\n}}\n"})
    res = _scan(tmp_path, "springboot", "no-business-logic-in-boundary", "src/main/java")
    assert len(res.violations) == 1 and "handle" in res.violations[0].message


def test_short_delegating_method_and_long_service_are_fine(tmp_path):
    long_body = "\n".join(f"    int x{i} = {i};" for i in range(30))
    _write(tmp_path, {
        "src/main/java/com/a/controller/C.java":
            "class C {\n  public User get(long id) {\n    return service.get(id);\n  }\n}\n",
        # long methods outside the boundary are not this rule's business
        "src/main/java/com/a/service/S.java":
            f"class S {{\n  public int work() {{\n{long_body}\n    return 1;\n  }}\n}}\n"})
    assert _scan(tmp_path, "springboot", "no-business-logic-in-boundary", "src/main/java").violations == []


def test_declarative_ui_blocks_are_not_methods(tmp_path):
    layout = "\n".join(f"      Text('row {i}')" for i in range(30))
    logic = "\n".join(f"    this.x{i} = {i};" for i in range(25))
    _write(tmp_path, {"entry/src/main/ets/pages/Home.ets":
        "@Component\nstruct Home {\n  build() {\n    Column() {\n" + layout + "\n    }\n  }\n"
        "  aboutToAppear(): void {\n" + logic + "\n  }\n}\n"})
    res = _scan(tmp_path, "harmonyos", "no-business-logic-in-boundary", "entry/src/main/ets")
    # the 30-line layout is ignored; the 25-line lifecycle method full of assignments is not
    assert [v.message.split("'")[1] for v in res.violations] == ["aboutToAppear"]


def test_viewmodels_and_build_scripts_are_not_the_boundary(tmp_path):
    logic = "\n".join(f"        x{i} = {i}" for i in range(30))
    _write(tmp_path, {"Sources/Presentation/UserListViewModel.swift":
                      "final class UserListViewModel {\n    func load() {\n" + logic + "\n    }\n}\n"})
    assert _scan(tmp_path, "ios", "no-business-logic-in-boundary", "Sources").violations == []
    rs = tmp_path / "rs"
    body = "\n".join(f"    let x{i} = {i};" for i in range(30))
    _write(rs, {"crates/arcana-grpc/build.rs": "fn main() {\n" + body + "\n}\n"})
    assert _scan(rs, "rust", "no-business-logic-in-boundary", "crates").violations == []


def test_python_method_length_uses_indentation(tmp_path):
    long_body = "\n".join(f"    x{i} = {i}" for i in range(25))
    _write(tmp_path, {"app/controller/users.py":
                      f"def short():\n    return 1\n\ndef long_one():\n{long_body}\n    return 2\n"})
    res = _scan(tmp_path, "python", "no-business-logic-in-boundary", "app")
    assert [v.message.split("'")[1] for v in res.violations] == ["long_one"]


# ---- 08 test-coverage (test suite exists) ----

def test_missing_test_suite_is_caught_and_scores_zero(tmp_path):
    _write(tmp_path, {"src/app/x.ts": "export const x = 1;\n"})
    res = _scan(tmp_path, "angular", "test-coverage", "src/app")
    assert len(res.violations) == 1 and res.compliance == 0.0


def test_spec_files_or_test_dirs_count_as_a_suite(tmp_path):
    _write(tmp_path, {"src/app/x.ts": "export const x = 1;\n", "src/app/x.spec.ts": "it('x',()=>{});\n"})
    assert _scan(tmp_path, "angular", "test-coverage", "src/app").violations == []
    other = tmp_path / "rust"
    _write(other, {"src/lib.rs": "pub fn a() {}\n#[cfg(test)]\nmod t { #[test] fn x() {} }\n"})
    assert _scan(other, "rust", "test-coverage").violations == []


# ---- 12 view-no-service ----

def test_view_importing_domain_service_is_caught(tmp_path):
    _write(tmp_path, {"src/app/domain/services/user.service.ts": "export interface UserService {}\n",
                      "src/app/presentation/user.component.ts":
                          "import { UserService } from '../domain/services/user.service';\n"})
    res = _scan(tmp_path, "angular", "view-no-service", "src/app")
    assert len(res.violations) == 1


def test_viewmodel_and_ui_core_services_are_fine(tmp_path):
    _write(tmp_path, {
        "src/app/domain/services/user.service.ts": "export interface UserService {}\n",
        "src/app/core/services/toast.service.ts": "export class ToastService {}\n",
        "src/app/domain/services/i18n.service.ts": "export class I18nService {}\n",
        "src/app/domain/services/nav-graph.service.ts": "export class NavGraphService {}\n",
        # a translate pipe / header legitimately use translation and navigation services
        "src/app/presentation/shared/translate.pipe.ts":
            "import { I18nService } from '../../domain/services/i18n.service';\n"
            "import { NavGraphService } from '../../domain/services/nav-graph.service';\n",
        # the ViewModel is exactly where domain services belong
        "src/app/presentation/user.view-model.ts":
            "import { UserService } from '../domain/services/user.service';\n",
        # a UI service in core/ is not a domain service
        "src/app/presentation/user.component.ts":
            "import { ToastService } from '../core/services/toast.service';\n"
            "import { User } from '../domain/models/user';\n"})
    assert _scan(tmp_path, "angular", "view-no-service", "src/app").violations == []


# ---- 14 navgraph-typesafe ----

def test_missing_route_table_is_caught(tmp_path):
    _write(tmp_path, {"src/app/presentation/a.component.ts": "export class A {}\n"})
    assert len(_scan(tmp_path, "angular", "navgraph-typesafe", "src/app").violations) == 1


def test_route_table_and_firmware_scope(tmp_path):
    _write(tmp_path, {"src/app/app.routes.ts": "export const routes = [];\n"})
    assert _scan(tmp_path, "angular", "navgraph-typesafe", "src/app").violations == []
    vue = tmp_path / "vue"  # routes in a router/ directory, file named index.ts
    _write(vue, {"src/router/index.ts": "export default createRouter({});\n",
                 "src/presentation/A.vue": "<template/>\n"})
    assert _scan(vue, "vue", "navgraph-typesafe").violations == []
    rule = next(r for r in load_rules(RULES) if r.id == "navgraph-typesafe")
    assert "esp32" not in rule.applies_to and "stm32" not in rule.applies_to


# ---- 17 service-no-db ----

def test_sql_in_service_is_caught(tmp_path):
    _write(tmp_path, {"src/main/java/com/a/service/UserService.java":
                      'class UserService {\n  String q = "SELECT id FROM users";\n}\n'})
    assert len(_scan(tmp_path, "springboot", "service-no-db", "src/main/java").violations) == 1


def test_sql_in_repository_and_in_comments_is_fine(tmp_path):
    _write(tmp_path, {
        "src/main/java/com/a/repository/UserRepository.java":
            'interface UserRepository {\n  @Query("SELECT u FROM User u")\n  List<User> all();\n}\n',
        "src/main/java/com/a/service/UserService.java":
            "class UserService {\n  // SELECT * FROM users is done by the repository\n"
            "  /* DELETE FROM x happens in the DAO */\n  List<User> all() { return repo.all(); }\n}\n"})
    assert _scan(tmp_path, "springboot", "service-no-db", "src/main/java").violations == []


def test_sql_in_rust_service_lib_rs_is_caught(tmp_path):
    # rust's profile calls lib.rs a DI container; that must not hide SQL in the service crate
    _write(tmp_path, {"crates/arcana-service/src/lib.rs":
                      'pub fn f() { let _ = sqlx::query("SELECT 1"); }\n',
                      "crates/arcana-service/src/cache.rs":
                      "pub fn g() { let _ = redis::cmd(\"GET\").query_async(&mut c); }\n"})
    res = _scan(tmp_path, "rust", "service-no-db", "crates")
    assert [v.file for v in res.violations] == ["arcana-service/src/lib.rs"]


def test_go_service_under_domain_is_still_the_service_layer(tmp_path):
    _write(tmp_path, {"internal/domain/service/user_service.go":
                      'func f(db *sql.DB) { db.QueryContext(ctx, "SELECT 1") }\n',
                      # dao and entity under domain/ are not service files
                      "internal/domain/dao/user_dao.go": 'func g(db *sql.DB) { db.QueryContext(ctx, "x") }\n',
                      # a gRPC handler under controller/.../service/ belongs to the controller
                      "internal/controller/grpc/service/auth.go":
                      'func h(db *sql.DB) { db.QueryContext(ctx, "y") }\n'})
    res = _scan(tmp_path, "go", "service-no-db", "internal")
    assert [v.file for v in res.violations] == ["domain/service/user_service.go"]


# ---- 19 transaction-at-service ----

def test_transactional_on_controller_is_caught(tmp_path):
    _write(tmp_path, {"src/main/java/com/a/controller/C.java":
                      "class C {\n  @Transactional\n  public void save() {}\n}\n"})
    assert len(_scan(tmp_path, "springboot", "transaction-at-service", "src/main/java").violations) == 1


def test_transactional_on_service_is_fine(tmp_path):
    _write(tmp_path, {"src/main/java/com/a/service/S.java":
                      "class S {\n  @Transactional\n  public void save() {}\n}\n",
                      "src/main/java/com/a/controller/C.java":
                      "class C {\n  // @Transactional belongs on the service\n  public void save() {}\n}\n"})
    assert _scan(tmp_path, "springboot", "transaction-at-service", "src/main/java").violations == []
