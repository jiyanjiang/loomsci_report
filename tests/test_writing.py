from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loomsci_report.writing import Claim, Draft, Review, hard_gate, refine


class WritingLoopTest(unittest.TestCase):
    def test_best_draft_is_retained(self) -> None:
        claims = [Claim("c1", "claim", ["src-1"])]
        draft = Draft("seed", claims, ["src-1"])
        scores = iter([
            {"thesis": 60, "structure": 60, "traceability": 80, "readability": 60, "citation": 60, "figures": 50},
            {"thesis": 80, "structure": 80, "traceability": 80, "readability": 80, "citation": 80, "figures": 70},
        ])
        def critic(_draft):
            current = next(scores)
            return Review(True, [], current)
        def rewriter(_draft, _issues):
            return "better"
        best, trace = refine(draft, allowed_sources={"src-1"}, critic=critic, rewriter=rewriter, max_rounds=2)
        self.assertEqual(best.text, "better")
        self.assertEqual(len(trace), 2)

    def test_bad_candidate_does_not_replace_best(self) -> None:
        claims = [Claim("c1", "claim", ["src-1"])]
        draft = Draft("seed", claims, ["src-1"], scores={"thesis": 90, "structure": 90, "traceability": 90, "readability": 90, "citation": 90, "figures": 90})
        def critic(_draft):
            return Review(True, [], {"thesis": 80, "structure": 80, "traceability": 80, "readability": 80, "citation": 80, "figures": 80})
        def rewriter(_draft, _issues):
            return "worse"
        best, trace = refine(draft, allowed_sources={"src-1"}, critic=critic, rewriter=rewriter,
                             max_rounds=1, threshold=100, min_delta=1)
        self.assertEqual(best.text, "seed")
        self.assertFalse(trace[0]["accepted"])

    def test_citation_drift_fails_gate(self) -> None:
        claims = [Claim("c1", "claim", ["src-1"])]
        draft = Draft("seed", claims, ["src-1", "src-x"])
        self.assertFalse(hard_gate(draft, {"src-1"}))


if __name__ == "__main__":
    unittest.main()
