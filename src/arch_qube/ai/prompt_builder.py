"""Build prompts for Claude API analysis."""
from __future__ import annotations
from pathlib import Path
from arch_qube.rules.models import Rule, AiCheck
from arch_qube.profiles.loader import FrameworkProfile


SYSTEM_PROMPT = """\
You are Architecture Qube, an architecture compliance analyzer.
You evaluate code against the Arcana Architecture Suite rules.

IMPORTANT: Respond ONLY with valid JSON. No explanation outside the JSON.

Response schema:
{{
  "compliant": true or false,
  "violations": [
    {{
      "line": <line number or 0>,
      "description": "<what is wrong>",
      "suggestion": "<how to fix>"
    }}
  ]
}}

If compliant, return: {{"compliant": true, "violations": []}}
"""


def build_file_prompt(
    rule: Rule,
    ai_check: AiCheck,
    file_path: Path,
    file_content: str,
    profile: FrameworkProfile,
) -> tuple[str, str]:
    """Build system + user prompt for a single file check.

    Returns (system_prompt, user_prompt).
    """
    layer_name = profile.classify_file(str(file_path)) or "unknown"
    allowed = profile.allowed_dependencies.get(layer_name, [])

    template = ai_check.prompt_template
    user_prompt = template.format(
        file_path=str(file_path),
        file_content=file_content,
        layer_name=layer_name,
        allowed_layers=", ".join(allowed),
        framework_profile=profile.framework,
        file_list=str(file_path),
    )

    system = SYSTEM_PROMPT.format()
    system += f"\nFramework: {profile.framework}"
    system += f"\nRule: {rule.id} — {rule.name}"
    system += f"\nRule description: {rule.description}"

    return system, user_prompt


def build_project_prompt(
    rule: Rule,
    ai_check: AiCheck,
    file_list: list[str],
    profile: FrameworkProfile,
) -> tuple[str, str]:
    """Build prompt for project-level checks (e.g., security, offline-first)."""
    template = ai_check.prompt_template
    user_prompt = template.format(
        file_list="\n".join(file_list),
        framework_profile=profile.framework,
        file_path="(project-level)",
        file_content="(see file list)",
        layer_name="(project)",
        allowed_layers="(all)",
    )

    system = SYSTEM_PROMPT.format()
    system += f"\nFramework: {profile.framework}"
    system += f"\nRule: {rule.id} — {rule.name}"

    return system, user_prompt
