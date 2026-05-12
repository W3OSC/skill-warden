"""Tests for the obfuscation detector."""

import pytest

from skill_warden.fetcher import SkillFileData
from skill_warden.template_runner import load_template, run_template

TEMPLATE_ID = "obfuscation"


def make_file(content: str, filename: str = "SKILL.md") -> SkillFileData:
    return SkillFileData(filename=filename, content=content, file_type="text")


class TestObfuscation:
    def setup_method(self):
        self.template = load_template(TEMPLATE_ID)

    def test_detects_zero_width_space(self):
        f = make_file("Normal\u200Btext with zero-width space")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_zero_width_non_joiner(self):
        f = make_file("Text with\u200Czero-width non-joiner")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_soft_hyphen(self):
        f = make_file("Text with soft\u00ADhyphen character")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_bom(self):
        f = make_file("Text with\uFEFFBOM character")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_fullwidth_digits(self):
        f = make_file("Use \uFF11\uFF12\uFF13 fullwidth digits")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_fullwidth_latin(self):
        f = make_file("\uFF41\uFF42\uFF43 fullwidth latin chars")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_mathematical_bold(self):
        f = make_file("\U0001D400 mathematical bold capital A")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_cyrillic_homoglyphs(self):
        # Cyrillic 'а' (U+0430) looks like Latin 'a'
        f = make_file("p\u0430ssword contains Cyrillic homoglyph")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_greek_homoglyphs(self):
        # Greek 'ο' (U+03BF) looks like Latin 'o'
        f = make_file("p\u03BFssword contains Greek homoglyph")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_tag_unicode_block(self):
        f = make_file("Hidden\U000E0048\U000E0065\U000E006Ctag characters")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_base64_blob(self):
        # Valid base64, >160 chars (176), has mixed case + digits
        blob = "dGhpcyBpcyBhIHZlcnkgbG9uZyBiYXNlNjQgc3RyaW5nIHRoYXQgc2hvdWxkIHRyaWdnZXIgdGhlIGJhc2U2NCBkZXRlY3RvciBiZWNhdXNlIGl0IGlzIG92ZXIgb25lIGh1bmRyZWQgYW5kIHNpeHR5IGNoYXJhY3RlcnMgbG9uZyE="
        f = make_file(f"Some text\n{blob}\nMore text")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_clean_skill_passes(self):
        f = make_file(
            "This skill analyzes smart contracts for vulnerabilities.\n"
            "All content is in plain ASCII text with no special characters."
        )
        result = run_template(self.template, [f])
        assert result.passed

    def test_short_base64_does_not_trigger(self):
        # Base64 under 160 chars should not trigger
        short_b64 = "dGhpcyBpcyBzaG9ydA=="
        f = make_file(f"Short base64: {short_b64}")
        result = run_template(self.template, [f])
        assert result.passed

    def test_hex_string_does_not_trigger_as_base64(self):
        # All-hex strings should not be flagged as base64 blobs
        hex_str = "a" * 80 + "b" * 80  # 160 chars, all hex-valid lowercase
        f = make_file(f"Hash: {hex_str}")
        result = run_template(self.template, [f])
        assert result.passed

    def test_template_metadata(self):
        assert self.template.severity == "medium"
        assert self.template.advisory is True
        assert self.template.category == "advisory"
