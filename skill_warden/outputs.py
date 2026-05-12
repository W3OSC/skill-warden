"""Output formatters: pretty (rich), JSON, SARIF 2.1.0."""

from __future__ import annotations

import json
import sys
from typing import IO, Optional

from skill_warden.scanner import ScanResult
from skill_warden.settings import SARIF_SCHEMA, SEVERITY_TO_SARIF_LEVEL, VERSION

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    from rich.text import Text
    _RICH = True
except ImportError:
    _RICH = False


# ---------------------------------------------------------------------------
# Pretty output
# ---------------------------------------------------------------------------

_SEVERITY_COLORS = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "cyan",
    "info": "blue",
}

BANNER = r"""
 _____ _    _ _ _    _    _  _____  _____  _____  _____ _   _
/  ___| | _(_) | |  | |  | |/  _  ||  _  ||  _  \|  _  | \ | |
\ `--.| |/ / | | |  | |  | || | | || |/' || |/' /| | | |  \| |
 `--. \   <| | | |  | |/\| || | | ||  /| ||  /| || | | | . ` |
/\__/ / |\ \ | | |  \  /\  /\ \_/ /\ |_/ /\ |_/ /\ \_/ / |\  |
\____/\_| \_/_|_|_|   \/  \/  \___/  \___/  \___/  \___/\_| \_/
"""


def _severity_icon(severity: str, passed: bool, advisory: bool) -> str:
    if passed:
        return ""
    if advisory:
        return ""
    return ""


def write_pretty(results: list[ScanResult], out: IO = sys.stdout) -> None:
    if _RICH:
        _write_pretty_rich(results, out)
    else:
        _write_pretty_plain(results, out)


def _write_pretty_rich(results: list[ScanResult], out: IO) -> None:
    console = Console(file=out, highlight=False)

    console.print(
        Panel.fit(
            "[bold #e040fb]skill-warden[/] [dim]v{}[/]  •  [dim]AI Skill Security Scanner[/]".format(VERSION),
            border_style="#6a0dad",
            padding=(0, 2),
        )
    )
    console.print()

    for result in results:
        _print_skill_rich(console, result)

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.hard_passed)
    failed = total - passed
    advisories = sum(1 for r in results if r.has_advisory_violations)

    summary_text = (
        f"[green]{passed} passed[/]  "
        f"[red]{failed} failed[/]  "
        f"[yellow]{advisories} advisory[/]  "
        f"[dim]{total} skill(s) scanned[/]"
    )
    console.print(Panel(summary_text, title="[bold]Summary[/]", border_style="dim"))


def _print_skill_rich(console, result: ScanResult) -> None:
    from rich.text import Text

    title = f"[bold cyan]{result.skill_name}[/]"
    if result.commit_sha and result.commit_sha != "local":
        title += f" [dim]@ {result.commit_sha}[/]"
    if result.skill_path:
        title += f" [dim]({result.skill_path})[/]"

    console.print(Panel(title, border_style="cyan", padding=(0, 1)))

    for dr in result.detector_results:
        icon = _severity_icon(dr.severity, dr.passed, dr.advisory)
        if dr.passed:
            status = f"[green]{icon} PASS[/]"
        elif dr.advisory:
            status = f"[yellow]{icon} ADVISORY[/]"
        else:
            status = f"[red]{icon} FAIL[/]"

        sev_color = _SEVERITY_COLORS.get(dr.severity, "white")
        console.print(
            f"  {status}  [{sev_color}]{dr.severity.upper():8}[/]  {dr.name}"
        )
        for v in dr.violations[:5]:
            console.print(f"      [dim]{v.file}:{v.line_start}[/]  [italic]{v.snippet}[/]")
        if len(dr.violations) > 5:
            console.print(f"      [dim]… and {len(dr.violations) - 5} more violation(s)[/]")

    if result.quality_results:
        console.print()
        console.print("  [dim]Quality checks:[/]")
        for qr in result.quality_results:
            icon = "" if qr.passed else ""
            color = "green" if qr.passed else "yellow"
            console.print(f"    [{color}]{icon}[/]  {qr.name}")
            for v in qr.violations[:3]:
                loc = f"{v.file}:{v.line}" if v.file else ""
                console.print(f"        [dim]{loc}[/]  {v.message}")

    console.print(
        f"\n  [dim]AI Slop Score:[/] [bold]{result.ai_slop_score}/100[/]"
    )
    console.print()


def _write_pretty_plain(results: list[ScanResult], out: IO) -> None:
    print("=== skill-warden v{} ===".format(VERSION), file=out)
    print()

    for result in results:
        print(f"Skill: {result.skill_name}  ({result.skill_path})", file=out)
        print("-" * 60, file=out)
        for dr in result.detector_results:
            icon = _severity_icon(dr.severity, dr.passed, dr.advisory)
            status = "PASS" if dr.passed else ("ADVISORY" if dr.advisory else "FAIL")
            print(f"  {icon} {status:8}  {dr.severity.upper():8}  {dr.name}", file=out)
            for v in dr.violations[:5]:
                print(f"      {v.file}:{v.line_start}  {v.snippet}", file=out)
        for qr in result.quality_results:
            icon = "" if qr.passed else ""
            print(f"  {icon} QUALITY           {qr.name}", file=out)
        print(f"  AI Slop Score: {result.ai_slop_score}/100", file=out)
        print()

    passed = sum(1 for r in results if r.hard_passed)
    failed = len(results) - passed
    print(f"Summary: {passed} passed, {failed} failed - {len(results)} skill(s)", file=out)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def write_json(results: list[ScanResult], out: IO = sys.stdout) -> None:
    data = [_scan_result_to_dict(r) for r in results]
    json.dump(data, out, indent=2, default=str)
    out.write("\n")


def _scan_result_to_dict(r: ScanResult) -> dict:
    return {
        "skill_name": r.skill_name,
        "skill_path": r.skill_path,
        "github_url": r.github_url,
        "commit_sha": r.commit_sha,
        "hard_passed": r.hard_passed,
        "all_passed": r.all_passed,
        "has_advisory_violations": r.has_advisory_violations,
        "ai_slop_score": r.ai_slop_score,
        "ai_slop_signals": [
            {"name": s.name, "score": s.score, "detail": s.detail}
            for s in r.ai_slop_signals
        ],
        "detector_results": [
            {
                "id": dr.id,
                "name": dr.name,
                "severity": dr.severity,
                "category": dr.category,
                "advisory": dr.advisory,
                "passed": dr.passed,
                "violations": [
                    {
                        "snippet": v.snippet,
                        "file": v.file,
                        "line_start": v.line_start,
                        "line_end": v.line_end,
                        "char_offset": v.char_offset,
                    }
                    for v in dr.violations
                ],
            }
            for dr in r.detector_results
        ],
        "quality_results": [
            {
                "id": qr.id,
                "name": qr.name,
                "passed": qr.passed,
                "violations": [
                    {"message": v.message, "file": v.file, "line": v.line}
                    for v in qr.violations
                ],
            }
            for qr in r.quality_results
        ],
    }


# ---------------------------------------------------------------------------
# SARIF 2.1.0 output
# ---------------------------------------------------------------------------

def write_sarif(results: list[ScanResult], out: IO = sys.stdout) -> None:
    from skill_warden.template_runner import load_templates

    all_templates = load_templates()
    rules = [_template_to_sarif_rule(t) for t in all_templates]

    run_results = []
    artifacts = set()

    for scan in results:
        for dr in scan.detector_results:
            for v in dr.violations:
                artifacts.add(v.file)
                run_results.append(_violation_to_sarif_result(dr, v))
        for qr in scan.quality_results:
            for qv in qr.violations:
                if qv.file:
                    artifacts.add(qv.file)
                run_results.append(_quality_violation_to_sarif_result(qr, qv))

    sarif = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "skill-warden",
                        "version": VERSION,
                        "informationUri": "https://github.com/W3OSC/skill-warden",
                        "rules": rules,
                    }
                },
                "results": run_results,
                "artifacts": [
                    {"location": {"uri": a}} for a in sorted(artifacts)
                ],
            }
        ],
    }
    json.dump(sarif, out, indent=2, default=str)
    out.write("\n")


def _template_to_sarif_rule(t) -> dict:
    level = SEVERITY_TO_SARIF_LEVEL.get(t.severity, "note")
    # Convert id to PascalCase for name
    name = "".join(word.capitalize() for word in t.id.replace("-", "_").split("_"))
    ref = t.references[0] if t.references else "https://github.com/W3OSC/skill-warden"
    return {
        "id": t.id,
        "name": name,
        "shortDescription": {"text": t.name},
        "fullDescription": {"text": t.description},
        "defaultConfiguration": {"level": level},
        "helpUri": ref,
        "properties": {"tags": ["security", "skill-warden", t.category]},
    }


def _violation_to_sarif_result(dr, v) -> dict:
    level = SEVERITY_TO_SARIF_LEVEL.get(dr.severity, "note")
    return {
        "ruleId": dr.id,
        "level": level,
        "message": {"text": v.snippet},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": v.file},
                    "region": {"startLine": v.line_start, "endLine": v.line_end},
                }
            }
        ],
    }


def _quality_violation_to_sarif_result(qr, qv) -> dict:
    result: dict = {
        "ruleId": qr.id,
        "level": "note",
        "message": {"text": qv.message},
        "locations": [],
    }
    if qv.file:
        result["locations"].append(
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": qv.file},
                    "region": {"startLine": qv.line or 1, "endLine": qv.line or 1},
                }
            }
        )
    return result
