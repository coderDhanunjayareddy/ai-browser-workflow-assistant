from __future__ import annotations

from typing import Any

from app.context_packet.models import PlannerPacket


class PlannerV2Adapter:
    """Compatibility adapter for Planner Contract V2.

    V3.1B builds packets in shadow mode but preserves the external planner
    interface. This adapter makes the compatibility boundary explicit without
    changing planner behavior.
    """

    def to_legacy_inputs(
        self,
        *,
        packet: PlannerPacket,
        task: str,
        page_context: Any,
        prior_steps: list[Any],
        supplemental_context: str,
        verified_state: dict[str, Any],
        compressed_context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "task": task,
            "page_context": page_context,
            "prior_steps": prior_steps,
            "supplemental_context": supplemental_context,
            "verified_state": verified_state,
            "compressed_context": compressed_context,
            "output_contract": packet.output_contract,
        }
