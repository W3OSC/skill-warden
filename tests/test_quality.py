"""Tests for quality check detectors."""

import pytest

from skill_warden.fetcher import SkillFileData
from skill_warden.template_runner import load_template, run_template


def make_file(content: str, filename: str = "SKILL.md") -> SkillFileData:
    return SkillFileData(filename=filename, content=content, file_type="text")


# ---------------------------------------------------------------------------
# description_correctness
# ---------------------------------------------------------------------------

class TestDescriptionCorrectness:
    def setup_method(self):
        self.template = load_template("description-correctness")

    def test_detects_missing_description(self):
        f = make_file("---\nname: test-skill\n---\n\n# Skill")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_no_frontmatter(self):
        f = make_file("# My Skill\n\nThis skill does things.")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_description_too_long(self):
        long_desc = "A" * 1025
        f = make_file(f"---\nname: test\ndescription: {long_desc}\n---\n\n# Skill")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_i_can(self):
        f = make_file("---\nname: test\ndescription: I can help you analyze code.\n---\n\n# Skill")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_i_will(self):
        f = make_file("---\nname: test\ndescription: I will assist with your requests.\n---\n\n# Skill")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_i_am(self):
        f = make_file("---\nname: test\ndescription: I am a helpful assistant skill.\n---\n\n# Skill")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_you_can_use_this(self):
        f = make_file("---\nname: test\ndescription: You can use this to analyze code.\n---\n\n# Skill")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_you_will(self):
        f = make_file("---\nname: test\ndescription: You will receive a detailed report.\n---\n\n# Skill")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_clean_description_passes(self):
        f = make_file(
            "---\nname: test\n"
            "description: Analyzes Solidity contracts for common security vulnerabilities.\n"
            "---\n\n# Skill"
        )
        result = run_template(self.template, [f])
        assert result.passed

    def test_template_metadata(self):
        assert self.template.severity == "info"
        assert self.template.advisory is True


# ---------------------------------------------------------------------------
# skill_md_length
# ---------------------------------------------------------------------------

class TestSkillMdLength:
    def setup_method(self):
        self.template = load_template("skill-md-length")

    def test_detects_too_long(self):
        long_content = "---\nname: test\ndescription: Test.\n---\n\n" + "\n".join(
            f"Line {i}" for i in range(502)
        )
        f = make_file(long_content)
        result = run_template(self.template, [f])
        assert not result.passed

    def test_passes_exactly_500_lines(self):
        content = "---\nname: test\ndescription: Test.\n---\n\n" + "\n".join(
            f"Line {i}" for i in range(494)
        )
        f = make_file(content)
        result = run_template(self.template, [f])
        assert result.passed

    def test_passes_short_file(self):
        f = make_file("---\nname: test\ndescription: Short.\n---\n\n# Skill\n\nContent.")
        result = run_template(self.template, [f])
        assert result.passed

    def test_no_skill_md_passes(self):
        f = make_file("Some content", filename="helper.md")
        result = run_template(self.template, [f])
        assert result.passed


# ---------------------------------------------------------------------------
# nested_references
# ---------------------------------------------------------------------------

class TestNestedReferences:
    def setup_method(self):
        self.template = load_template("nested-references")

    def test_detects_nested_reference(self):
        skill_md = make_file(
            "---\nname: test\ndescription: Test.\n---\n\nSee [HELPER.md](HELPER.md)",
            filename="SKILL.md",
        )
        helper = make_file(
            "# Helper\n\nSee [DEEP.md](DEEP.md) for more details.",
            filename="HELPER.md",
        )
        result = run_template(self.template, [skill_md, helper])
        assert not result.passed

    def test_clean_references_pass(self):
        skill_md = make_file(
            "---\nname: test\ndescription: Test.\n---\n\nSee [HELPER.md](HELPER.md)",
            filename="SKILL.md",
        )
        helper = make_file(
            "# Helper\n\nThis is the helper content with no further references.",
            filename="HELPER.md",
        )
        result = run_template(self.template, [skill_md, helper])
        assert result.passed


# ---------------------------------------------------------------------------
# large_reference_without_toc
# ---------------------------------------------------------------------------

class TestLargeReferenceWithoutToc:
    def setup_method(self):
        self.template = load_template("large-reference-without-toc")

    def test_detects_large_ref_without_toc(self):
        skill_md = make_file(
            "---\nname: test\ndescription: Test.\n---\n\nSee [LARGE.md](LARGE.md)",
            filename="SKILL.md",
        )
        large = make_file(
            "\n".join(f"Line {i}" for i in range(101)),
            filename="LARGE.md",
        )
        result = run_template(self.template, [skill_md, large])
        assert not result.passed

    def test_large_ref_with_toc_passes(self):
        skill_md = make_file(
            "---\nname: test\ndescription: Test.\n---\n\nSee [LARGE.md](LARGE.md)",
            filename="SKILL.md",
        )
        large = make_file(
            "## Contents\n- [Section 1](#section-1)\n\n"
            + "\n".join(f"Line {i}" for i in range(101)),
            filename="LARGE.md",
        )
        result = run_template(self.template, [skill_md, large])
        assert result.passed

    def test_small_ref_without_toc_passes(self):
        skill_md = make_file(
            "---\nname: test\ndescription: Test.\n---\n\nSee [SMALL.md](SMALL.md)",
            filename="SKILL.md",
        )
        small = make_file(
            "\n".join(f"Line {i}" for i in range(50)),
            filename="SMALL.md",
        )
        result = run_template(self.template, [skill_md, small])
        assert result.passed
