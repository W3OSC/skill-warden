"""AI slop scorer - heuristic signal that content may be AI-generated."""

from __future__ import annotations

from dataclasses import dataclass

from skill_warden.fetcher import SkillFileData

EM_DASH = "\u2014"

_EM_DASH_SCORE_MAP = [
    (0, 0),
    (1, 5),
    (2, 10),
    (3, 20),
    (5, 30),   # 4-5
    (8, 45),   # 6-8
    (12, 55),  # 9-12
    (float("inf"), 70),  # 13+
]


def _em_dash_score(count: int) -> int:
    score = 0
    for threshold, value in _EM_DASH_SCORE_MAP:
        if count <= threshold:
            score = value
            break
    return score


@dataclass
class SlopSignal:
    name: str
    score: int
    detail: str


def compute_ai_slop_score(files: list[SkillFileData]) -> tuple[int, list[SlopSignal]]:
    """
    Compute the AI slop score (0–100) for a set of skill files.
    Returns (final_score, list_of_signals).
    """
    all_content = "\n".join(f.content for f in files)
    signals: list[SlopSignal] = []

    em_count = all_content.count(EM_DASH)
    em_score = _em_dash_score(em_count)
    if em_count > 0:
        signals.append(
            SlopSignal(
                name="em_dash_frequency",
                score=em_score,
                detail=f"Found {em_count} em-dash(es) - common in AI-generated prose",
            )
        )

    total = min(sum(s.score for s in signals), 100)
    return total, signals
