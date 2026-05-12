"""skill-warden CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from skill_warden import __version__
from skill_warden.outputs import write_json, write_pretty, write_sarif
from skill_warden.scanner import ScanResult, scan_github, scan_local


def _is_local_path(target: str) -> bool:
    p = Path(target)
    return p.exists() or target.startswith("./") or target.startswith("/")


def _open_output(path: Optional[str]):
    if path:
        return open(path, "w", encoding="utf-8")
    return sys.stdout


def _run_scan(args: argparse.Namespace) -> int:
    target: str = args.target
    output_format: str = args.output
    output_file: Optional[str] = args.output_file
    fail_on_advisory: bool = args.fail_on_advisory
    github_token: Optional[str] = args.github_token
    no_quality: bool = args.no_quality
    no_ai_score: bool = args.no_ai_score
    template_ids: Optional[list[str]] = args.template or None

    results: list[ScanResult] = []

    try:
        if _is_local_path(target):
            results = scan_local(
                path=target,
                run_quality=not no_quality,
                run_ai_score=not no_ai_score,
                template_filter=template_ids,
            )
        else:
            results = scan_github(
                url=target,
                token=github_token,
                run_quality=not no_quality,
                run_ai_score=not no_ai_score,
                template_filter=template_ids,
            )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not results:
        print("No skills found at the given target.", file=sys.stderr)
        return 1

    out = _open_output(output_file)
    try:
        if output_format == "json":
            write_json(results, out)
        elif output_format == "sarif":
            write_sarif(results, out)
        else:
            write_pretty(results, out)
    finally:
        if output_file:
            out.close()

    # Determine exit code
    any_hard_fail = any(not r.hard_passed for r in results)
    any_advisory = any(r.has_advisory_violations for r in results)

    if any_hard_fail:
        return 1
    if fail_on_advisory and any_advisory:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-warden",
        description="Security scanner for GitHub Copilot skills.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  skill-warden scan owner/repo\n"
            "  skill-warden scan https://github.com/owner/repo/tree/main/skills/my-skill\n"
            "  skill-warden scan ./my-local-skill/ --output json\n"
            "  skill-warden scan owner/repo --output sarif --output-file results.sarif\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"skill-warden {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)
    scan_cmd = sub.add_parser("scan", help="Scan skill(s) for security threats")
    scan_cmd.add_argument("target", help="GitHub URL, owner/repo shorthand, or local path")
    scan_cmd.add_argument(
        "--output",
        choices=["pretty", "json", "sarif"],
        default="pretty",
        help="Output format (default: pretty)",
    )
    scan_cmd.add_argument("--output-file", metavar="FILE", help="Write output to file")
    scan_cmd.add_argument(
        "--fail-on-advisory",
        action="store_true",
        default=False,
        help="Exit code 2 if advisory violations found",
    )
    scan_cmd.add_argument("--github-token", metavar="TOKEN", help="GitHub personal access token")
    scan_cmd.add_argument("--no-quality", action="store_true", help="Skip quality checks")
    scan_cmd.add_argument("--no-ai-score", action="store_true", help="Skip AI slop scoring")
    scan_cmd.add_argument(
        "--template",
        metavar="TEMPLATE_ID",
        action="append",
        help="Run only specific template(s) - repeatable",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "scan":
        sys.exit(_run_scan(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
