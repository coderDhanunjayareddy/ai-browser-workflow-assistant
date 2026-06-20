class CandidateGenerator:
    def generate(self, failed_action: dict, relevant_elements: list[dict]) -> list[dict]:
        candidates = []
        intended = " ".join(str(failed_action.get(k) or "") for k in ("description", "target_selector", "value")).lower()
        for element in relevant_elements:
            label = " ".join(str(element.get(k) or "") for k in ("text", "aria_label", "accessibility_name")).lower()
            score = sum(1 for term in intended.split() if len(term) > 2 and term in label)
            if score:
                candidates.append({**failed_action, "target_selector": element.get("selector", ""), "exploration_score": score})
        return sorted(candidates, key=lambda item: item["exploration_score"], reverse=True)[:3]
