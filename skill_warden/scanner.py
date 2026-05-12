"""Scanner orchestrator - ties fetching, template running, and scoring together."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from skill_warden.ai_signals import SlopSignal, compute_ai_slop_score
from skill_warden.fetcher import SkillData, SkillFileData, fetch_from_github, fetch_from_local
from skill_warden.template_runner import (
    DetectorResult,
    Violation,
    load_templates,
    run_template,
)


@dataclass
class QualityViolation:
    message: str
    file: Optional[str]
    line: Optional[int]


@dataclass
class QualityResult:
    id: str
    name: str
    passed: bool
    violations: list[QualityViolation] = field(default_factory=list)


@dataclass
class ScanResult:
    skill_name: str
    skill_path: str
    github_url: str
    commit_sha: str
    detector_results: list[DetectorResult]
    quality_results: list[QualityResult]
    ai_slop_score: int
    ai_slop_signals: list[SlopSignal]
    hard_passed: bool
    all_passed: bool
    has_advisory_violations: bool


def _detector_to_quality(dr: DetectorResult) -> QualityResult:
    return QualityResult(
        id=dr.id,
        name=dr.name,
        passed=dr.passed,
        violations=[
            QualityViolation(message=v.snippet, file=v.file, line=v.line_start)
            for v in dr.violations
        ],
    )


def _scan_files(
    files: list[SkillFileData],
    skill_name: str,
    skill_path: str,
    github_url: str,
    commit_sha: str,
    run_quality: bool,
    run_ai_score: bool,
    template_filter: Optional[list[str]],
) -> ScanResult:
    all_templates = load_templates()
    if template_filter:
        all_templates = [t for t in all_templates if t.id in template_filter]

    security_templates = [t for t in all_templates if t.category in ("security", "advisory")]
    quality_templates = [t for t in all_templates if t.category == "quality"]

    detector_results: list[DetectorResult] = []
    quality_results: list[QualityResult] = []

    for tmpl in security_templates:
        result = run_template(tmpl, files)
        detector_results.append(result)

    if run_quality:
        for tmpl in quality_templates:
            result = run_template(tmpl, files)
            quality_results.append(_detector_to_quality(result))

    ai_slop_score = 0
    ai_slop_signals: list[SlopSignal] = []
    if run_ai_score:
        ai_slop_score, ai_slop_signals = compute_ai_slop_score(files)

    # hard_passed: no non-advisory (hard) violations
    hard_failed = any(
        not dr.passed and not dr.advisory for dr in detector_results
    )
    hard_passed = not hard_failed

    # has_advisory_violations: any advisory detectors triggered
    has_advisory_violations = any(
        not dr.passed and dr.advisory for dr in detector_results
    )

    all_passed = hard_passed and not has_advisory_violations and all(qr.passed for qr in quality_results)

    return ScanResult(
        skill_name=skill_name,
        skill_path=skill_path,
        github_url=github_url,
        commit_sha=commit_sha,
        detector_results=detector_results,
        quality_results=quality_results,
        ai_slop_score=ai_slop_score,
        ai_slop_signals=ai_slop_signals,
        hard_passed=hard_passed,
        all_passed=all_passed,
        has_advisory_violations=has_advisory_violations,
    )


def scan_github(
    url: str,
    token: Optional[str] = None,
    run_quality: bool = True,
    run_ai_score: bool = True,
    template_filter: Optional[list[str]] = None,
) -> list[ScanResult]:
    """Fetch skills from GitHub and scan them."""
    skills = fetch_from_github(url, token=token)
    results = []
    for skill in skills:
        result = _scan_files(
            files=skill.files,
            skill_name=skill.name,
            skill_path=skill.skill_path,
            github_url=skill.github_url,
            commit_sha=skill.commit_sha,
            run_quality=run_quality,
            run_ai_score=run_ai_score,
            template_filter=template_filter,
        )
        results.append(result)
    return results


def _has_skill_md(directory: Path) -> bool:
    return any(f.name.upper() == "SKILL.MD" for f in directory.iterdir() if f.is_file())


def _detect_skill_dirs(base: Path) -> list[Path]:
    """
    Return a list of directories to scan as individual skills.
    - If base itself contains SKILL.md -> [base]
    - If base contains subdirs that have SKILL.md -> one entry per such subdir
    - Otherwise -> [base] (flat scan)
    """
    if not base.is_dir():
        return [base]
    if _has_skill_md(base):
        return [base]
    skill_subdirs = [d for d in sorted(base.iterdir()) if d.is_dir() and _has_skill_md(d)]
    if skill_subdirs:
        return skill_subdirs
    return [base]


def scan_local(
    path: str,
    run_quality: bool = True,
    run_ai_score: bool = True,
    template_filter: Optional[list[str]] = None,
) -> list[ScanResult]:
    """Scan a local path, returning one ScanResult per skill folder found."""
    base = Path(path)
    skill_dirs = _detect_skill_dirs(base)
    results = []
    for skill_dir in skill_dirs:
        files = fetch_from_local(str(skill_dir))
        result = _scan_files(
            files=files,
            skill_name=skill_dir.name,
            skill_path=str(skill_dir),
            github_url="",
            commit_sha="local",
            run_quality=run_quality,
            run_ai_score=run_ai_score,
            template_filter=template_filter,
        )
        results.append(result)
    return results
