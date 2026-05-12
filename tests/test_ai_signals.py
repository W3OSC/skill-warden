"""Tests for the AI slop scorer."""

import pytest

from skill_warden.ai_signals import compute_ai_slop_score
from skill_warden.fetcher import SkillFileData


def make_file(content: str) -> SkillFileData:
    return SkillFileData(filename="SKILL.md", content=content, file_type="text")


class TestAiSlopScore:
    def test_zero_em_dashes_score_zero(self):
        f = make_file("This skill analyzes code for vulnerabilities.")
        score, signals = compute_ai_slop_score([f])
        assert score == 0
        assert len(signals) == 0

    def test_one_em_dash_scores_five(self):
        f = make_file("This skill \u2014 the best one \u2014 only has one.")
        # Actually there are 2 em-dashes above, let's use exactly one
        f = make_file("This skill \u2014 is great.")
        score, signals = compute_ai_slop_score([f])
        assert score == 5

    def test_two_em_dashes_scores_ten(self):
        f = make_file("Feature one \u2014 and feature two \u2014 are great.")
        score, signals = compute_ai_slop_score([f])
        assert score == 10

    def test_three_em_dashes_scores_twenty(self):
        content = "A \u2014 B \u2014 C \u2014 D"
        f = make_file(content)
        score, signals = compute_ai_slop_score([f])
        assert score == 20

    def test_four_em_dashes_scores_thirty(self):
        content = "\u2014 " * 4
        f = make_file(content)
        score, signals = compute_ai_slop_score([f])
        assert score == 30

    def test_six_em_dashes_scores_forty_five(self):
        content = "\u2014 " * 6
        f = make_file(content)
        score, signals = compute_ai_slop_score([f])
        assert score == 45

    def test_nine_em_dashes_scores_fifty_five(self):
        content = "\u2014 " * 9
        f = make_file(content)
        score, signals = compute_ai_slop_score([f])
        assert score == 55

    def test_thirteen_em_dashes_scores_seventy(self):
        content = "\u2014 " * 13
        f = make_file(content)
        score, signals = compute_ai_slop_score([f])
        assert score == 70

    def test_many_em_dashes_capped_at_100(self):
        content = "\u2014 " * 100
        f = make_file(content)
        score, signals = compute_ai_slop_score([f])
        assert score <= 100

    def test_signals_populated_when_em_dashes_found(self):
        f = make_file("Text \u2014 with \u2014 em dashes.")
        score, signals = compute_ai_slop_score([f])
        assert len(signals) == 1
        assert signals[0].name == "em_dash_frequency"
        assert "em-dash" in signals[0].detail

    def test_multiple_files_aggregated(self):
        f1 = make_file("File one \u2014 has one em dash.")
        f2 = make_file("File two \u2014 also \u2014 has two em dashes.")
        # Total: 3 em dashes
        score, signals = compute_ai_slop_score([f1, f2])
        assert score == 20  # 3 em dashes = 20

    def test_score_is_integer(self):
        f = make_file("Content \u2014 with dash.")
        score, _ = compute_ai_slop_score([f])
        assert isinstance(score, int)
