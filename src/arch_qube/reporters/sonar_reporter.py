"""SonarQube Generic Issue Import format reporter."""
from __future__ import annotations
import json
from arch_qube.rules.models import ScanReport, Severity

_SEVERITY_MAP = {
    Severity.CRITICAL: "CRITICAL",
    Severity.MAJOR: "MAJOR",
    Severity.MINOR: "MINOR",
    Severity.INFO: "INFO",
}


def generate_sonar_issues(report: ScanReport) -> str:
    """Generate SonarQube Generic Issue Import JSON."""
    issues = []
    for r in report.rule_results:
        for v in r.violations:
            issues.append({
                "engineId": "arch-qube",
                "ruleId": r.rule_id,
                "severity": _SEVERITY_MAP.get(r.severity, "MAJOR"),
                "type": "CODE_SMELL",
                "primaryLocation": {
                    "message": v.message,
                    "filePath": v.file,
                    "textRange": {"startLine": max(v.line, 1)},
                },
            })
    return json.dumps({"issues": issues}, indent=2, ensure_ascii=False)
