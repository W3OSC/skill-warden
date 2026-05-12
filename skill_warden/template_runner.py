"""Load YAML detector templates and run them against skill files."""

from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from skill_warden.fetcher import SkillFileData
from skill_warden.settings import TEMPLATES_DIR


@dataclass
class Template:
    id: str
    version: str
    name: str
    severity: str
    category: str
    advisory: bool
    description: str
    impact: str
    action_items: list[str]
    references: list[str]
    patterns: list[re.Pattern]
    check: Optional[str]
    raw: dict


@dataclass
class Violation:
    snippet: str
    file: str
    line_start: int
    line_end: int
    char_offset: int


@dataclass
class DetectorResult:
    id: str
    name: str
    severity: str
    category: str
    advisory: bool
    passed: bool
    violations: list[Violation] = field(default_factory=list)


def load_template(template_id: str) -> Template:
    """Load a single template by its ID (filename without .yaml)."""
    path = TEMPLATES_DIR / f"{template_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return _parse_template(path)


def load_templates() -> list[Template]:
    """Load all YAML templates from the templates directory."""
    templates = []
    for path in sorted(TEMPLATES_DIR.glob("*.yaml")):
        templates.append(_parse_template(path))
    return templates


def _parse_template(path: Path) -> Template:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    patterns: list[re.Pattern] = []
    for p in raw.get("patterns", []):
        try:
            patterns.append(re.compile(p, re.MULTILINE))
        except re.error as exc:
            raise ValueError(f"Invalid regex in {path}: {p!r} - {exc}") from exc

    return Template(
        id=raw["id"],
        version=raw.get("version", "1.0.0"),
        name=raw["name"],
        severity=raw.get("severity", "info"),
        category=raw.get("category", "quality"),
        advisory=raw.get("advisory", True),
        description=raw.get("description", ""),
        impact=raw.get("impact", ""),
        action_items=raw.get("action-items", []),
        references=raw.get("references", []),
        patterns=patterns,
        check=raw.get("check"),
        raw=raw,
    )


def run_template(template: Template, files: list[SkillFileData]) -> DetectorResult:
    """Run a template against a list of skill files."""
    if template.check:
        return _run_quality_check(template, files)

    if template.id == "obfuscation":
        return _run_obfuscation(template, files)

    return _run_pattern_template(template, files)


# ---------------------------------------------------------------------------
# Pattern-based scanning
# ---------------------------------------------------------------------------

def _run_pattern_template(template: Template, files: list[SkillFileData]) -> DetectorResult:
    violations: list[Violation] = []
    for f in files:
        violations.extend(_scan_file_patterns(template.patterns, f))
    return DetectorResult(
        id=template.id,
        name=template.name,
        severity=template.severity,
        category=template.category,
        advisory=template.advisory,
        passed=len(violations) == 0,
        violations=violations,
    )


def _scan_file_patterns(
    patterns: list[re.Pattern], f: SkillFileData
) -> list[Violation]:
    violations: list[Violation] = []
    lines = f.content.splitlines()
    for pattern in patterns:
        for m in pattern.finditer(f.content):
            start_char = m.start()
            # Compute line number
            line_num = f.content.count("\n", 0, start_char) + 1
            snippet = m.group(0)[:80].replace("\n", " ")
            if len(m.group(0)) > 80:
                snippet += "…"
            violations.append(
                Violation(
                    snippet=snippet,
                    file=f.filename,
                    line_start=line_num,
                    line_end=line_num,
                    char_offset=start_char,
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Obfuscation detector (special logic)
# ---------------------------------------------------------------------------

_B64_RE = re.compile(r"[A-Za-z0-9+/=]{160,}")

_OBFUSC_PATTERNS: list[re.Pattern] = [
    re.compile(r"[\u200B\u200C\u200D\u00AD\uFEFF\u2060\u180E\u034F]"),
    re.compile(r"[\uFF10-\uFF19\uFF21-\uFF3A\uFF41-\uFF5A]"),
    re.compile(r"[\U0001D400-\U0001D7FF]"),
    re.compile(r"[\u0430\u0435\u043E\u0440\u0441\u0445\u0443\u0456\u0455\u0501]"),
    re.compile(r"[\u03B1\u03BF\u03C1\u03BD\u03B5\u03BA]"),
    re.compile(r"\u0131"),
    re.compile(r"[\U000E0000-\U000E007F]"),
    re.compile(r"(?:^|[^a-zA-Z0-9_])!`[^`\n]+`"),
]


def _is_valid_base64_blob(candidate: str) -> bool:
    """Return True if candidate looks like a meaningful base64 blob."""
    if len(candidate) % 4 != 0:
        return False
    padding = candidate.count("=")
    if padding > 2:
        return False
    # Must have diversity: lowercase, uppercase, digit, non-alpha
    has_lower = bool(re.search(r"[a-z]", candidate))
    has_upper = bool(re.search(r"[A-Z]", candidate))
    has_digit = bool(re.search(r"[0-9]", candidate))
    has_symbol = "+" in candidate or "/" in candidate
    if not (has_lower and has_upper and has_digit):
        return False
    # Reject if it's all hex
    if re.fullmatch(r"[0-9a-fA-F]+", candidate.replace("=", "")):
        return False
    try:
        base64.b64decode(candidate)
        return True
    except Exception:
        return False


def _is_instruction_file(filename: str) -> bool:
    name = Path(filename).name.upper()
    return name.endswith(".MD") or name.endswith(".TXT")


def _non_ascii_block_scan(f: SkillFileData) -> list[Violation]:
    violations: list[Violation] = []
    is_instruction = _is_instruction_file(f.filename)
    for i, line in enumerate(f.content.splitlines(), start=1):
        non_ws = line.replace(" ", "").replace("\t", "")
        if not non_ws:
            continue
        non_ascii_chars = sum(1 for c in non_ws if ord(c) > 127)
        ratio = non_ascii_chars / len(non_ws) if non_ws else 0

        triggered = False
        if len(non_ws) >= 120 and ratio >= 0.70:
            triggered = True
        elif is_instruction and non_ascii_chars >= 12 and ratio >= 0.45:
            triggered = True

        if triggered:
            snippet = line[:80].replace("\n", " ")
            if len(line) > 80:
                snippet += "…"
            violations.append(
                Violation(
                    snippet=snippet,
                    file=f.filename,
                    line_start=i,
                    line_end=i,
                    char_offset=0,
                )
            )
    return violations


def _run_obfuscation(template: Template, files: list[SkillFileData]) -> DetectorResult:
    violations: list[Violation] = []
    for f in files:
        # Run standard regex patterns
        violations.extend(_scan_file_patterns(_OBFUSC_PATTERNS, f))
        # Base64 blob scan
        for m in _B64_RE.finditer(f.content):
            if _is_valid_base64_blob(m.group(0)):
                line_num = f.content.count("\n", 0, m.start()) + 1
                snippet = m.group(0)[:80] + "…"
                violations.append(
                    Violation(
                        snippet=snippet,
                        file=f.filename,
                        line_start=line_num,
                        line_end=line_num,
                        char_offset=m.start(),
                    )
                )
        # Non-ASCII block scan
        violations.extend(_non_ascii_block_scan(f))

    return DetectorResult(
        id=template.id,
        name=template.name,
        severity=template.severity,
        category=template.category,
        advisory=template.advisory,
        passed=len(violations) == 0,
        violations=violations,
    )


# ---------------------------------------------------------------------------
# Quality check dispatcher
# ---------------------------------------------------------------------------

def _run_quality_check(template: Template, files: list[SkillFileData]) -> DetectorResult:
    from skill_warden import quality_checks

    fn: Optional[Callable] = getattr(quality_checks, template.check, None)
    if fn is None:
        raise ValueError(f"Quality check function not found: {template.check}")

    violations = fn(files)
    return DetectorResult(
        id=template.id,
        name=template.name,
        severity=template.severity,
        category=template.category,
        advisory=template.advisory,
        passed=len(violations) == 0,
        violations=violations,
    )
