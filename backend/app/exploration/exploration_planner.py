from app.exploration.candidate_evaluator import CandidateEvaluator
from app.exploration.candidate_generator import CandidateGenerator


class ExplorationPlanner:
    """Top-3 selector exploration, intended only after normal recovery fails."""

    def __init__(self):
        self.generator = CandidateGenerator()
        self.evaluator = CandidateEvaluator()

    def explore(self, failed_action: dict, relevant_elements: list[dict]) -> dict | None:
        return self.evaluator.select(self.generator.generate(failed_action, relevant_elements))
