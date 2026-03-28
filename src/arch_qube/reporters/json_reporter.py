"""JSON report generator."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from arch_qube.rules.models import ScanReport


def generate_json(report: ScanReport) -> str:
    """Generate a machine-readable JSON report."""
    data = {
        "meta": {
            "tool": "arch-qube",
            "version": "0.1.0",
            "framework": report.framework,
            "scan_date": datetime.now(timezone.utc).isoformat(),
            "source_root": report.source_root,
            "files_scanned": report.files_scanned,
        },
        "score": {
            "total": report.total_score,
            "grade": report.grade,
            "pass": report.passed,
            "threshold": report.threshold,
        },
        "rules": [
            {
                "id": r.rule_id,
                "name": r.rule_name,
                "category": r.category,
                "severity": r.severity.value,
                "weight": r.weight,
                "compliance": r.compliance,
                "weighted_score": round(r.weighted_score, 2),
                "violations": [
                    {
                        "file": v.file,
                        "line": v.line,
                        "message": v.message,
                        "suggestion": v.suggestion,
                        "check_type": v.check_type.value,
                    }
                    for v in r.violations
                ],
                "files_checked": r.files_checked,
            }
            for r in report.rule_results
        ],
        "summary": {
            "critical_violations": report.critical_violations,
            "total_violations": report.total_violations,
            "rules_passed": sum(1 for r in report.rule_results if r.passed),
            "rules_failed": sum(1 for r in report.rule_results if not r.passed),
            "rules_total": len(report.rule_results),
        },
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
