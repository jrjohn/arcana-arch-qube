<p align="center">
  <img src="https://img.shields.io/badge/Architecture_Qube-AI--powered-gold?style=for-the-badge" alt="Architecture Qube">
  <img src="https://img.shields.io/badge/Rules-21-blue?style=for-the-badge" alt="Rules">
  <img src="https://img.shields.io/badge/Profiles-14-blue?style=for-the-badge" alt="Profiles">
  <img src="https://img.shields.io/badge/Tests-19_passing-brightgreen?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

<h1 align="center">Architecture Qube</h1>

<p align="center">
  <strong>AI-powered Architecture Quality Gate for CI/CD</strong><br>
  Detect MVVM, Clean Architecture, and GoF pattern violations automatically.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#rules">Rules</a> &bull;
  <a href="#profiles">Profiles</a> &bull;
  <a href="#ci-integration">CI Integration</a> &bull;
  <a href="#ai-analysis">AI Analysis</a>
</p>

---

## Quick Start

```bash
pip install -e .

# AST-only scan (free, ~0.5s)
arch-qube scan ./src --framework angular

# AST + AI semantic analysis
arch-qube scan ./src --framework springboot --api-key $ANTHROPIC_API_KEY

# PR mode: only scan changed files
arch-qube scan ./src --framework react --diff-only --ci
```

### Example Output

```
                      Architecture Qube Results
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┓
┃ Rule                             ┃ Severity ┃ Compliance ┃ Status ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━┩
│ Layer Direction Enforcement      │ critical │       100% │  PASS  │
│ Only DI Container Imports Impl   │ critical │       100% │  PASS  │
│ MVVM I/O/E Structure             │ critical │       100% │  PASS  │
│ Backend Layer Chain              │ critical │       100% │  PASS  │
│ Interface/Impl Colocation        │  major   │       100% │  PASS  │
│ Implementation Naming Convention │  minor   │       100% │  PASS  │
└──────────────────────────────────┴──────────┴────────────┴────────┘

PASS — 100.0/100 (A+)
```

---

## How It Works

```
arch-qube scan ./src --framework angular --ci
        │
        ├── Stage 1: AST Scanner (free, ~0.5s)
        │   ├── Import graph → layer direction violations
        │   ├── File structure → impl/ colocation
        │   ├── Naming → *Impl convention
        │   └── Annotations → @Transactional placement
        │
        ├── Stage 2: AI Analyzer (Claude API, ~$0.01/PR)
        │   ├── Semantic analysis (business logic in boundary?)
        │   ├── MVVM I/O/E pattern compliance
        │   ├── Cache strategy verification
        │   └── Results cached by file hash
        │
        └── Output
            ├── JSON report
            ├── Markdown summary
            ├── SonarQube Generic Issue Import
            ├── JUnit XML (Jenkins)
            └── Badge (shields.io)
```

---

## Rules

### Common (All Platforms)

| # | Rule | Severity | Weight | Check |
|---|------|----------|--------|-------|
| 1 | Layer Direction | Critical | 15 | AST |
| 2 | Interface/Impl Colocation | Major | 5 | AST |
| 3 | Impl Import Restriction | Critical | 8 | AST |
| 4 | Impl Naming Convention | Minor | 3 | AST |
| 5 | DTO/Entity Separation | Major | 7 | AI |
| 6 | No Business Logic in Boundary | Major | 8 | AI |
| 7 | Defense-in-Depth Security | Critical | 5 | AI |
| 8 | Test Coverage >= 95% | Major | 5 | AST |

### Client (Web + Mobile + Desktop)

| # | Rule | Severity | Weight | Check |
|---|------|----------|--------|-------|
| 9 | MVVM I/O/E Structure | Critical | 3 | AI |
| 10 | MVVM I/O/E Models | Major | 3 | AI |
| 11 | Unidirectional Data Flow | Critical | 3 | AST+AI |
| 12 | View Cannot Call Service | Critical | 3 | AST |
| 13 | 4-Layer Progressive Cache | Major | 3 | AI |
| 14 | Type-Safe NavGraph | Major | 3 | AST+AI |
| 15 | Offline-First Design | Major | 3 | AI |

### Backend (Cloud Services)

| # | Rule | Severity | Weight | Check |
|---|------|----------|--------|-------|
| 16 | Controller->Service->Repo->DAO | Critical | 5 | AST |
| 17 | Service Cannot Access DB | Critical | 5 | AST |
| 18 | Controller Cannot Use DAO | Critical | 4 | AST |
| 19 | Transaction at Service Only | Critical | 4 | AST |
| 20 | Controller Uses DTO | Major | 3 | AI |
| 21 | Repository Cannot Call Service | Critical | 2 | AST |

**Add a rule = add a YAML file.** No code changes needed.

---

## Profiles

14 framework profiles with platform-specific layer definitions:

| Platform | Frameworks |
|----------|-----------|
| **Web** | Angular, React, Vue |
| **Mobile** | iOS (SwiftUI), Android (Compose), HarmonyOS (ArkUI) |
| **Desktop** | Windows (WinUI 3) |
| **Backend** | Spring Boot, Python/Flask, Go, Rust, Node.js |
| **Embedded** | STM32, ESP32 |

Each profile defines: layer paths, allowed dependencies, import patterns, file extensions, DI container files, naming conventions.

---

## CI Integration

### Jenkins Pipeline

```groovy
stage('Architecture Qube') {
    steps {
        sh '''
            arch-qube scan ./src \
                --framework ${FRAMEWORK} \
                --ci \
                --diff-only \
                --format json,markdown,sonar,junit
        '''
    }
    post {
        always {
            junit 'arch-qube-reports/arch-qube-junit.xml'
            archiveArtifacts 'arch-qube-reports/**'
        }
    }
}
```

### SonarQube Integration

```properties
# sonar-project.properties
sonar.externalIssuesReportPaths=arch-qube-reports/arch-qube-sonar.json
```

### Pre-commit Hook

```bash
#!/bin/sh
# .git/hooks/pre-commit
arch-qube scan ./src --framework angular --no-ai --ci --diff-only
```

### GitHub Actions

```yaml
- name: Architecture Qube
  run: arch-qube scan ./src -f react --ci --diff-only
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

---

## AI Analysis

Stage 2 uses Claude API for semantic checks that AST cannot detect:

- **Business logic in Controller** — is this `if/else` domain logic or routing?
- **MVVM I/O/E compliance** — does the ViewModel have proper input/output/effect segments?
- **DTO leakage** — does the Entity leak through the API boundary?
- **Cache strategy** — is the 4-layer cascade implemented?

**Cost control:**
- Only scans changed files in PR mode (`--diff-only`)
- Results cached by file SHA-256 hash
- Skip files > 50KB
- Uses claude-sonnet-4 for fast, cost-effective analysis
- ~$0.01 per PR

---

## CLI Reference

```
arch-qube scan <path> [options]

Options:
  -f, --framework TEXT    Framework profile (required)
  --rules PATH            Custom rules directory
  --profiles PATH         Custom profiles directory
  --threshold FLOAT       Pass/fail score 0-100 (default: 95)
  -o, --output PATH       Output directory (default: arch-qube-reports/)
  --format TEXT           json,markdown,sonar,junit,badge (default: json,markdown)
  --ci                    CI mode: exit 1 on fail
  --no-ai                 Skip AI analysis (AST only)
  --diff-only             Only scan git-changed files
  --base-branch TEXT      Base branch for diff (default: main)
  --api-key TEXT          Claude API key (or ANTHROPIC_API_KEY env)

Exit codes:
  0  PASS (score >= threshold)
  1  FAIL (score < threshold or critical violation)
  2  ERROR (config/setup issue)
```

---

## Scoring

```
Score = Sum(rule_weight * compliance%) / total_weight * 100

A+: 98-100    A: 95-97    B: 85-94    C: 70-84    D: 50-69    F: 0-49
```

Any **critical** rule failure = automatic FAIL regardless of score.

---

## Adding Custom Rules

```yaml
# rules/custom/my-rule.yaml
id: my-custom-rule
name: "My Custom Architecture Rule"
category: common
severity: major
weight: 5

ast_checks:
  - type: import_direction
    check: "no_upward_imports"

ai_checks:
  - type: semantic_review
    prompt_template: |
      Check this file for my custom pattern...
      {file_content}
      Respond JSON: {"compliant": true/false, "violations": [...]}

scoring:
  method: percentage
  pass_threshold: 100
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>SonarQube manages code quality. Architecture Qube manages architecture quality.</strong>
</p>
