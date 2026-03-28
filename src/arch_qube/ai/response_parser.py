"""Parse Claude API responses into structured results."""
from __future__ import annotations
import json
import re
from arch_qube.rules.models import Violation, CheckType


def parse_ai_response(response_text: str, source_file: str = "") -> list[Violation]:
    """Parse Claude's JSON response into Violation objects."""
    data = _extract_json(response_text)
    if data is None:
        return []

    if data.get("compliant", True):
        return []

    violations = []
    for v in data.get("violations", []):
        violations.append(Violation(
            file=source_file,
            line=v.get("line", 0),
            message=v.get("description", "AI-detected violation"),
            suggestion=v.get("suggestion", ""),
            check_type=CheckType.AI,
        ))
    return violations


def _extract_json(text: str) -> dict | None:
    """Extract JSON from text, handling markdown code fences."""
    # Try direct parse
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ```
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
