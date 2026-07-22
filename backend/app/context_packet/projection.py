from __future__ import annotations

from typing import Any

from app.context_packet.budget import ContextPacketBudget, trim_items
from app.semantic_page.graph import SemanticNode, SemanticPageGraph


def project_semantic_graph(
    graph: SemanticPageGraph,
    budget: ContextPacketBudget,
) -> tuple[dict[str, Any], dict[str, int], dict[str, int]]:
    targets = _project_targets(graph)
    facts = _project_facts(graph)
    controls = _project_nodes(graph, {"control", "field", "upload", "download", "navigation", "dialog"})
    entities = _project_nodes(graph, {"entity", "result_item", "section", "result_set", "form", "table", "error_state"})
    original = {
        "targets": len(targets),
        "facts": len(facts),
        "controls": len(controls),
        "entities": len(entities),
    }
    targets, trimmed_targets = trim_items(targets, budget.max_targets)
    facts, trimmed_facts = trim_items(facts, budget.max_facts)
    controls, trimmed_controls = trim_items(controls, budget.max_controls)
    entities, trimmed_entities = trim_items(entities, budget.max_entities)
    trimmed = {
        "targets": trimmed_targets,
        "facts": trimmed_facts,
        "controls": trimmed_controls,
        "entities": trimmed_entities,
    }
    projection = {
        "graph_id": graph.graph_id,
        "observation_id": graph.observation_id,
        "page_type": graph.page_type,
        "semantic_targets": targets,
        "facts": facts,
        "controls": controls,
        "entities": entities,
        "landmarks": _project_nodes(graph, {"page", "section", "navigation", "dialog"})[:10],
    }
    return projection, original, trimmed


def _project_targets(graph: SemanticPageGraph) -> list[dict[str, Any]]:
    return [
        {
            "target_id": target.target_id,
            "target_type": target.target_type,
            "semantic_role": target.semantic_role,
            "label": target.label,
            "entity_ref": target.entity_ref,
            "confidence": target.confidence,
            "locator_count": len(target.locator_candidates),
        }
        for target in sorted(graph.targets, key=lambda item: (item.semantic_role, item.target_id))
    ]


def _project_facts(graph: SemanticPageGraph) -> list[dict[str, Any]]:
    return [
        {
            "fact_id": fact.fact_id,
            "label": fact.label,
            "value": fact.value,
            "source_node_id": fact.source_node_id,
            "confidence": fact.confidence,
        }
        for fact in sorted(graph.facts, key=lambda item: (item.label, item.fact_id))
    ]


def _project_nodes(graph: SemanticPageGraph, node_types: set[str]) -> list[dict[str, Any]]:
    nodes = [node for node in graph.nodes if node.node_type in node_types]
    return [_node_summary(node) for node in sorted(nodes, key=lambda item: (item.node_type, item.node_id))]


def _node_summary(node: SemanticNode) -> dict[str, Any]:
    return {
        "node_id": node.node_id,
        "node_type": node.node_type,
        "label": node.label,
        "text": node.text,
        "has_selector": bool(node.selector),
    }
