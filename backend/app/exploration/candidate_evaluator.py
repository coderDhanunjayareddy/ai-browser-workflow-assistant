class CandidateEvaluator:
    def select(self, candidates: list[dict]) -> dict | None:
        valid = [item for item in candidates if item.get("target_selector")]
        return max(valid, key=lambda item: item.get("exploration_score", 0), default=None)
