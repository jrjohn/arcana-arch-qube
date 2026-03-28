"""JUnit XML reporter for Jenkins integration."""
from __future__ import annotations
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString
from arch_qube.rules.models import ScanReport


def generate_junit(report: ScanReport) -> str:
    """Generate JUnit XML — each rule is a test case."""
    suite = Element("testsuite", {
        "name": f"arch-qube-{report.framework}",
        "tests": str(len(report.rule_results)),
        "failures": str(sum(1 for r in report.rule_results if not r.passed)),
        "errors": "0",
    })

    for r in report.rule_results:
        tc = SubElement(suite, "testcase", {
            "name": r.rule_name,
            "classname": f"arch-qube.{r.category}.{r.rule_id}",
        })
        if not r.passed:
            msg_lines = [f"{v.file}:{v.line} — {v.message}" for v in r.violations]
            failure = SubElement(tc, "failure", {
                "message": f"{r.rule_name}: {len(r.violations)} violation(s)",
                "type": r.severity.value,
            })
            failure.text = "\n".join(msg_lines)

    raw = tostring(suite, encoding="unicode")
    return parseString(raw).toprettyxml(indent="  ")
