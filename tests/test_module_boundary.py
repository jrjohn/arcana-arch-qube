"""Rule 22 (Fowler: domain-oriented modules, internally layered): a module may use another module
only through its public API. Not evaluated where there are no modules."""
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


def _scan(root: Path, framework: str, src: str):
    rules = [r for r in load_rules(RULES) if r.id == "module-boundary"]
    [res] = run_ast_scan(root / src, load_profile(PROFILES, framework), rules, project_root=root)
    return res


FEATURES = {
    "src/app/presentation/features/users/user-list.component.ts": "export class UserList {}\n",
    "src/app/presentation/features/users/internal/user-cache.ts": "export const cache = {};\n",
    "src/app/presentation/features/users/index.ts": "export * from './user-list.component';\n",
    "src/app/presentation/features/shared/button.component.ts": "export class Button {}\n",
}


def test_reaching_into_another_modules_internals_is_caught(tmp_path):
    _write(tmp_path, {**FEATURES, "src/app/presentation/features/home/home.component.ts":
                      "import { cache } from '../users/internal/user-cache';\n"})
    res = _scan(tmp_path, "angular", "src/app")
    assert res.evaluated
    assert [v.file for v in res.violations] == ["presentation/features/home/home.component.ts"]


def test_public_api_shared_modules_and_own_files_are_fine(tmp_path):
    _write(tmp_path, {**FEATURES, "src/app/presentation/features/home/home.component.ts":
                      "import { UserList } from '../users';\n"            # the module's index
                      "import { UserList as U } from '../users/index';\n"
                      "import { Button } from '../shared/button.component';\n"  # shared module
                      "import { x } from './home.helpers';\n",                  # own module
                      "src/app/app.routes.ts":                                   # app shell
                      "import { UserList } from './presentation/features/users/user-list.component';\n"})
    res = _scan(tmp_path, "angular", "src/app")
    assert res.evaluated and res.violations == []


def test_not_evaluated_without_modules(tmp_path):
    _write(tmp_path, {"src/app/presentation/a.component.ts": "export class A {}\n"})
    res = _scan(tmp_path, "angular", "src/app")
    assert res.evaluated is False and res.not_applicable is True          # no modules found
    _write(tmp_path, {"src/main/java/com/a/controller/C.java": "class C {}\n"})
    assert _scan(tmp_path, "springboot", "src/main/java").evaluated is False  # no module roots


def test_flat_screen_files_are_not_modules(tmp_path):
    _write(tmp_path, {"app/src/main/java/com/x/ui/screens/HomeScreen.kt":
                      "import com.x.ui.screens.UserScreen\n",
                      "app/src/main/java/com/x/ui/screens/UserScreen.kt": "class UserScreen\n"})
    assert _scan(tmp_path, "android", "app/src/main/java").evaluated is False
