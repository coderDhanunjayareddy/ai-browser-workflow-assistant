from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DecisionPolicy:
    name: str = "balanced"
    continue_bias: float = 1.0
    wait_bias: float = 1.0
    recovery_bias: float = 1.0
    replan_bias: float = 1.0
    user_bias: float = 1.0
    fail_bias: float = 1.0

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)

    @classmethod
    def from_name(cls, name: str | None) -> DecisionPolicy:
        normalized = str(name or "balanced").lower()
        if normalized == "conservative":
            return cls(
                name="conservative",
                continue_bias=0.9,
                wait_bias=1.1,
                recovery_bias=0.95,
                replan_bias=1.15,
                user_bias=1.2,
                fail_bias=1.1,
            )
        if normalized == "aggressive":
            return cls(
                name="aggressive",
                continue_bias=1.2,
                wait_bias=0.85,
                recovery_bias=1.1,
                replan_bias=0.9,
                user_bias=0.9,
                fail_bias=0.85,
            )
        return cls()
