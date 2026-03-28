"""Test AI module (response parser, prompt builder, cache)."""
from pathlib import Path
from arch_qube.ai.response_parser import parse_ai_response, _extract_json
from arch_qube.ai.cache import get_file_hash, CACHE_DIR, clear_cache
from arch_qube.ai.prompt_builder import SYSTEM_PROMPT


def test_parse_compliant_response():
    response = '{"compliant": true, "violations": []}'
    violations = parse_ai_response(response, "test.ts")
    assert len(violations) == 0


def test_parse_violation_response():
    response = '''{
        "compliant": false,
        "violations": [
            {"line": 5, "description": "Bad import", "suggestion": "Fix it"}
        ]
    }'''
    violations = parse_ai_response(response, "test.ts")
    assert len(violations) == 1
    assert violations[0].file == "test.ts"
    assert violations[0].line == 5
    assert "Bad import" in violations[0].message


def test_parse_markdown_wrapped_json():
    response = '''Here is my analysis:
```json
{"compliant": false, "violations": [{"line": 10, "description": "issue"}]}
```
    '''
    violations = parse_ai_response(response, "src/app.ts")
    assert len(violations) == 1
    assert violations[0].line == 10


def test_parse_invalid_json_returns_empty():
    violations = parse_ai_response("this is not json", "test.ts")
    assert len(violations) == 0


def test_extract_json_direct():
    result = _extract_json('{"key": "value"}')
    assert result == {"key": "value"}


def test_extract_json_from_fences():
    result = _extract_json('```json\n{"key": "value"}\n```')
    assert result == {"key": "value"}


def test_file_hash_deterministic(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    h1 = get_file_hash(f)
    h2 = get_file_hash(f)
    assert h1 == h2
    assert len(h1) == 16


def test_file_hash_changes_with_content(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("version 1")
    h1 = get_file_hash(f)
    f.write_text("version 2")
    h2 = get_file_hash(f)
    assert h1 != h2


def test_system_prompt_has_json_schema():
    assert "compliant" in SYSTEM_PROMPT
    assert "violations" in SYSTEM_PROMPT
