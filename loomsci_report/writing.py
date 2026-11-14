"""Bounded, evidence-constrained writing refinement.

The writer may change prose only. Claims and citations are fixed before the
loop; a candidate that drops or invents evidence is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

WEIGHTS = {
    "thesis": 20,
    "structure": 20,
    "traceability": 25,
    "readability": 15,
    "citation": 10,
    "figures": 10,
}


class WritingError(ValueError):
    pass


@dataclass
class Claim:
    id: str
    text: str
    sources: list[str]


@dataclass
class Draft:
    text: str
    claims: list[Claim]
    citations: list[str]
    issues: list[dict] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)
    hard_gate: bool = True


@dataclass
class Review:
    hard_gate: bool
    issues: list[dict]
    scores: dict[str, int]


def score(draft: Draft) -> int:
    if not draft.hard_gate:
        return -1
    return sum(WEIGHTS.get(key, 0) * max(0, min(100, int(value))) / 100
               for key, value in draft.scores.items())


def hard_gate(draft: Draft, allowed_sources: set[str]) -> bool:
    if any(not claim.sources for claim in draft.claims):
        return False
    if any(source not in allowed_sources for claim in draft.claims for source in claim.sources):
        return False
    if any(citation not in allowed_sources for citation in draft.citations):
        return False
    return True


def refine(
    draft: Draft,
    *,
    allowed_sources: set[str],
    critic: Callable[[Draft], Review],
    rewriter: Callable[[Draft, list[dict]], str],
    max_rounds: int = 3,
    threshold: int = 85,
    min_delta: float = 1.0,
) -> tuple[Draft, list[dict]]:
    """Return the best safe draft and the iteration trace.

    A candidate is accepted only when it passes the hard gate and improves the
    weighted score by at least ``min_delta``. The latest draft is never assumed
    to be the best.
    """
    if max_rounds < 0:
        raise WritingError("max_rounds must be non-negative")
    current = replace(draft)
    current.hard_gate = hard_gate(current, allowed_sources)
    best = replace(current)
    best_score = score(best)
    trace: list[dict] = []
    if not best.hard_gate:
        return best, [{"round": 0, "accepted": False, "reason": "initial_hard_gate"}]

    for round_no in range(1, max_rounds + 1):
        review = critic(current)
        current.issues = review.issues
        proposed_text = rewriter(current, review.issues)
        candidate = replace(current, text=proposed_text, issues=[], scores=review.scores)
        candidate.hard_gate = hard_gate(candidate, allowed_sources)
        candidate_score = score(candidate)
        accepted = candidate.hard_gate and candidate_score >= best_score + min_delta
        trace.append({
            "round": round_no,
            "accepted": accepted,
            "score": candidate_score,
            "best": best_score,
            "hard_gate": candidate.hard_gate,
        })
        if accepted:
            best = candidate
            best_score = candidate_score
        if not candidate.hard_gate:
            break
        if best_score >= threshold:
            break
        current = candidate
    return best, trace
