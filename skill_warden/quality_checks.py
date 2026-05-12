"""Code-based quality check functions referenced by YAML templates."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from skill_warden.fetcher import SkillFileData
from skill_warden.template_runner import Violation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIRST_SECOND_PERSON_RE = re.compile(
    r"(?i)\b(I\s+can|I\s+will|I\s+am|I'll|I've|"
    r"you\s+can\s+use\s+this|you\s+can\s+use\s+me|you\s+will)\b"
)

_SKILL_MD_NAMES = {"SKILL.MD", "SKILL.md"}

_MARKDOWN_LINK_RE = re.compile(r"\[.*?\]\(([^)#]+)\)")
_PROSE_REF_RE = re.compile(r"(?i)\bread\s+([A-Za-z0-9_\-]+\.[A-Za-z]+)")
_FILE_REF_RE = re.compile(r"(?i)\b([A-Za-z0-9_\-]+\.(md|txt|sh|py|json|yaml|yml))\b")

_TOC_MARKERS = [
    "# Contents",
    "## Contents",
    "# Table of Contents",
    "## Table of Contents",
    "- [",
]


def _get_skill_md(files: list[SkillFileData]) -> Optional[SkillFileData]:
    for f in files:
        if Path(f.filename).name.upper() == "SKILL.MD":
            return f
    return None


def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            return content[end + 4 :]
    return content


def _parse_frontmatter_field(content: str, field: str) -> Optional[str]:
    """Quick YAML frontmatter field extraction."""
    import yaml

    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    fm_text = content[3:end].strip()
    try:
        fm = yaml.safe_load(fm_text) or {}
        val = fm.get(field)
        return str(val) if val is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# description_correctness
# ---------------------------------------------------------------------------

def description_correctness(files: list[SkillFileData]) -> list[Violation]:
    violations: list[Violation] = []
    skill_md = _get_skill_md(files)
    target_file = skill_md.filename if skill_md else (files[0].filename if files else "SKILL.md")
    content = skill_md.content if skill_md else ""

    description = _parse_frontmatter_field(content, "description")

    if not description:
        violations.append(
            Violation(
                snippet="Missing description field in frontmatter",
                file=target_file,
                line_start=1,
                line_end=1,
                char_offset=0,
            )
        )
        return violations

    if len(description) > 1024:
        violations.append(
            Violation(
                snippet=f"Description is {len(description)} chars (max 1024)",
                file=target_file,
                line_start=1,
                line_end=1,
                char_offset=0,
            )
        )

    m = _FIRST_SECOND_PERSON_RE.search(description)
    if m:
        violations.append(
            Violation(
                snippet=f"First/second person language in description: '{m.group(0)}'",
                file=target_file,
                line_start=1,
                line_end=1,
                char_offset=0,
            )
        )

    return violations


# ---------------------------------------------------------------------------
# skill_md_length
# ---------------------------------------------------------------------------

def skill_md_length(files: list[SkillFileData]) -> list[Violation]:
    violations: list[Violation] = []
    skill_md = _get_skill_md(files)
    if skill_md is None:
        return violations

    line_count = skill_md.content.count("\n") + 1
    if line_count > 500:
        violations.append(
            Violation(
                snippet=f"SKILL.md has {line_count} lines (max 500)",
                file=skill_md.filename,
                line_start=500,
                line_end=line_count,
                char_offset=0,
            )
        )
    return violations


# ---------------------------------------------------------------------------
# nested_references
# ---------------------------------------------------------------------------

def _extract_references(content: str) -> list[str]:
    """Extract referenced filenames from markdown content."""
    refs = set()
    for m in _MARKDOWN_LINK_RE.finditer(content):
        target = m.group(1).strip()
        if not target.startswith("http"):
            refs.add(Path(target).name)
    for m in _PROSE_REF_RE.finditer(content):
        refs.add(m.group(1))
    return list(refs)


def nested_references(files: list[SkillFileData]) -> list[Violation]:
    violations: list[Violation] = []
    skill_md = _get_skill_md(files)
    if skill_md is None:
        return violations

    body = _strip_frontmatter(skill_md.content)
    first_level_refs = _extract_references(body)

    file_map = {Path(f.filename).name: f for f in files}

    for ref_name in first_level_refs:
        ref_file = file_map.get(ref_name)
        if ref_file is None:
            continue
        # Look for further references inside the referenced file
        nested = _extract_references(ref_file.content)
        for nested_ref in nested:
            if nested_ref != Path(skill_md.filename).name:
                violations.append(
                    Violation(
                        snippet=f"'{ref_name}' references '{nested_ref}' (nested reference)",
                        file=ref_file.filename,
                        line_start=1,
                        line_end=1,
                        char_offset=0,
                    )
                )

    return violations


# ---------------------------------------------------------------------------
# large_reference_without_toc
# ---------------------------------------------------------------------------

def large_reference_without_toc(files: list[SkillFileData]) -> list[Violation]:
    violations: list[Violation] = []
    skill_md = _get_skill_md(files)
    if skill_md is None:
        return violations

    body = _strip_frontmatter(skill_md.content)
    refs = _extract_references(body)
    file_map = {Path(f.filename).name: f for f in files}

    for ref_name in refs:
        ref_file = file_map.get(ref_name)
        if ref_file is None:
            continue
        line_count = ref_file.content.count("\n") + 1
        if line_count <= 100:
            continue
        has_toc = any(marker in ref_file.content for marker in _TOC_MARKERS)
        if not has_toc:
            violations.append(
                Violation(
                    snippet=f"'{ref_name}' is {line_count} lines but has no table of contents",
                    file=ref_file.filename,
                    line_start=1,
                    line_end=1,
                    char_offset=0,
                )
            )

    return violations
