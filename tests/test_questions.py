from __future__ import annotations
import json
import unittest
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "questions.json"

class QuestionSetTest(unittest.TestCase):
    def test_question_set_shape(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(data["format"], "loomsci-report-questions/1")
        questions = data["questions"]
        self.assertGreaterEqual(len(questions), 20)
        self.assertEqual(len({q["id"] for q in questions}), len(questions))
        categories = {q["category"] for q in questions}
        self.assertTrue({"academic", "life", "business", "general"} <= categories)
        for q in questions:
            self.assertTrue(q["question"].strip())
            self.assertTrue(q["expected_sources"])

if __name__ == "__main__":
    unittest.main()
