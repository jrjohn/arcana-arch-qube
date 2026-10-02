# Changelog

## [0.2.0](https://github.com/jrjohn/arcana-arch-qube/compare/v0.1.1...v0.2.0) (2026-10-02)


### Features

* Architecture Qube MVP — AI-powered Architecture Quality Gate ([73ef324](https://github.com/jrjohn/arcana-arch-qube/commit/73ef324a278bd401f96805c6a7cdae7cc62ec611))
* Phase 2 — full 21 rules + 14 profiles + SonarQube/JUnit/Badge reporters ([97432f6](https://github.com/jrjohn/arcana-arch-qube/commit/97432f6aa9b2e6004e85918232a01f71d1abb5bc))
* Phase 3 — Claude AI semantic analysis engine ([f1d6e83](https://github.com/jrjohn/arcana-arch-qube/commit/f1d6e83026c4d2043bae8c7a6e8898c773b9f1b2))
* Phase 4 — README, init command, pre-commit hook, profile update ([d64ff33](https://github.com/jrjohn/arcana-arch-qube/commit/d64ff331adb9f9523f2aa60c46e528dc02c99563))


### Bug Fixes

* Android data/worker + data/analytics added to DI whitelist ([e764342](https://github.com/jrjohn/arcana-arch-qube/commit/e764342f9bc624921ed0bcdec030914a27f40fc8))
* basename ** wildcard bug + improved DI pattern matching ([2268617](https://github.com/jrjohn/arcana-arch-qube/commit/2268617d253530f1ca99ccde708b5349182fab6d))
* Docker path resolution for rules/profiles directories ([40452d7](https://github.com/jrjohn/arcana-arch-qube/commit/40452d7e8bd757dbb2f26206eedd12a03c4a1deb))
* eliminate ~85% false positives in architecture scanning ([f88acf8](https://github.com/jrjohn/arcana-arch-qube/commit/f88acf838d2cc63a796795eefcbb401b56392c88))
* eliminate remaining false positives — fnmatch→PurePath, DI patterns ([121a549](https://github.com/jrjohn/arcana-arch-qube/commit/121a549a41627eb6ce5dad1bcbebeeba20f664d3))
* exclude mod.rs and __init__.py from impl-naming check ([99489fd](https://github.com/jrjohn/arcana-arch-qube/commit/99489fd0185141761caba4bc0f43e9264b43f1cf))
* exclude test/spec files from impl-import-restriction rule ([53bb42a](https://github.com/jrjohn/arcana-arch-qube/commit/53bb42a19eb04fb5f49e1d7b12289d40a1988185))
* **go profile:** put domain layer first to avoid domain/repository/ misclassification ([ec6ebe0](https://github.com/jrjohn/arcana-arch-qube/commit/ec6ebe0f395d2d0061f3a27e27dab03b50448440))
* **packaging:** bundle profile + rules YAMLs in pip package ([1e9c7ab](https://github.com/jrjohn/arcana-arch-qube/commit/1e9c7abdcb13eb3635f4c2030979a17e000dfa8f))
* **python profile:** add adapters/tasks/decorators/routes as DI container files ([29030b0](https://github.com/jrjohn/arcana-arch-qube/commit/29030b0b645636a8af133d081b4878abd19d4b4f))
* Rust workspace crate layer paths + HarmonyOS impl colocation ([ce45699](https://github.com/jrjohn/arcana-arch-qube/commit/ce45699b600f4dd6fa9bf11401c7532f1a83d818))
* **stm32:** correct source_roots to Targets/*/Main + register AppContainer.cpp as DI container ([aba46c8](https://github.com/jrjohn/arcana-arch-qube/commit/aba46c82403589b52055c16af11bf5441d0e52a6))
