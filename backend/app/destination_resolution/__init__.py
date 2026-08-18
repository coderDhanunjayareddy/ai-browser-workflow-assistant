"""Natural-language destination discovery and capability matching."""

from app.destination_resolution.resolver import (
    DestinationDecision,
    DestinationObjective,
    decompose_destination_objectives,
    known_app_entry_url,
    resolve_destination,
)

__all__ = [
    "DestinationDecision",
    "DestinationObjective",
    "decompose_destination_objectives",
    "known_app_entry_url",
    "resolve_destination",
]
