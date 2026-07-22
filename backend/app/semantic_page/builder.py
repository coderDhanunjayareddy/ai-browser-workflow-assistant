from __future__ import annotations

from typing import Any

from app.schemas.request import ContentBlock, InteractiveElement, PageContext
from app.semantic_page.classifiers import (
    classify_element_node_type,
    classify_page_type,
    classify_target_role,
    normalize_text,
)
from app.semantic_page.graph import (
    SemanticEdge,
    SemanticFact,
    SemanticNode,
    SemanticPageGraph,
    SemanticTarget,
)
from app.semantic_page.serializers import stable_hash


BUILDER_VERSION = "v1"


class SemanticPageGraphBuilder:
    def build(self, page_context: PageContext) -> SemanticPageGraph:
        input_hash = observation_hash(page_context)
        observation_id = f"obs.{input_hash}"
        page_node_id = "node.page"
        nodes: list[SemanticNode] = [
            SemanticNode(
                node_id=page_node_id,
                node_type="page",
                label=normalize_text(page_context.title, max_length=120),
                text=normalize_text(page_context.visible_text, max_length=300),
                metadata={"url_hash": stable_hash(page_context.url)},
            )
        ]
        edges: list[SemanticEdge] = []
        facts: list[SemanticFact] = []
        targets: list[SemanticTarget] = []

        for index, heading in enumerate(page_context.headings):
            node_id = f"node.section.{index + 1}"
            nodes.append(
                SemanticNode(
                    node_id=node_id,
                    node_type="section",
                    label=normalize_text(heading),
                    text=normalize_text(heading),
                )
            )
            edges.append(_edge("contains", page_node_id, node_id, index))

        if page_context.content_blocks:
            result_set_id = "node.result_set.1"
            nodes.append(
                SemanticNode(
                    node_id=result_set_id,
                    node_type="result_set",
                    label="Visible content",
                    metadata={"count": len(page_context.content_blocks)},
                )
            )
            edges.append(_edge("contains", page_node_id, result_set_id, 0))
            for index, block in enumerate(page_context.content_blocks):
                block_node = _content_block_node(block, index)
                nodes.append(block_node)
                edges.append(_edge("contains", result_set_id, block_node.node_id, index))
                if block_node.text:
                    fact = SemanticFact(
                        fact_id=f"fact.content.{index + 1}",
                        label="visible_content",
                        value=block_node.text,
                        source_node_id=block_node.node_id,
                        confidence=0.75,
                    )
                    facts.append(fact)
                    edges.append(_edge("has_fact", block_node.node_id, fact.fact_id, index))

        for index, element in enumerate(page_context.interactive_elements):
            if not element.visible:
                continue
            node = _element_node(element, index)
            target = _element_target(element, node.node_id, index)
            nodes.append(node)
            targets.append(target)
            edges.append(_edge("contains", page_node_id, node.node_id, index))
            edges.append(_edge("represents", node.node_id, target.target_id, index))

        for index, (key, value) in enumerate(sorted(page_context.metadata.items())):
            if not value:
                continue
            facts.append(
                SemanticFact(
                    fact_id=f"fact.metadata.{index + 1}",
                    label=normalize_text(key, max_length=80),
                    value=normalize_text(value, max_length=160),
                    source_node_id=page_node_id,
                    confidence=0.9,
                )
            )

        metadata: dict[str, Any] = {
            "source": "dom_a11y",
            "build_ms": 0,
            "input_hash": input_hash,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "fact_count": len(facts),
            "target_count": len(targets),
        }
        graph_seed = {
            "schema_version": "semantic_page_graph.v1",
            "builder_version": BUILDER_VERSION,
            "input_hash": input_hash,
            "nodes": [node.model_dump(mode="json") for node in nodes],
            "edges": [edge.model_dump(mode="json") for edge in edges],
            "facts": [fact.model_dump(mode="json") for fact in facts],
            "targets": [target.model_dump(mode="json") for target in targets],
        }
        return SemanticPageGraph(
            graph_id=f"graph.{stable_hash(graph_seed, length=20)}",
            observation_id=observation_id,
            builder_version=BUILDER_VERSION,
            url=page_context.url,
            title=page_context.title,
            page_type=classify_page_type(page_context),
            nodes=nodes,
            edges=edges,
            facts=facts,
            targets=targets,
            metadata=metadata,
        )


def observation_hash(page_context: PageContext) -> str:
    return stable_hash(
        {
            "url": page_context.url,
            "title": page_context.title,
            "metadata": dict(sorted(page_context.metadata.items())),
            "headings": page_context.headings,
            "visible_text": normalize_text(page_context.visible_text, max_length=2000),
            "content_blocks": [
                {"selector": block.selector, "text": normalize_text(block.text, max_length=500)}
                for block in page_context.content_blocks
            ],
            "interactive_elements": [
                {
                    "type": element.type,
                    "text": normalize_text(element.text),
                    "selector": element.selector,
                    "visible": element.visible,
                    "input_type": element.input_type,
                    "placeholder": normalize_text(element.placeholder),
                    "role": element.role,
                    "aria_label": normalize_text(element.aria_label),
                    "accessibility_name": normalize_text(element.accessibility_name),
                    "state": element.state,
                }
                for element in page_context.interactive_elements
            ],
        },
        length=20,
    )


def _content_block_node(block: ContentBlock, index: int) -> SemanticNode:
    return SemanticNode(
        node_id=f"node.result_item.{index + 1}",
        node_type="result_item",
        label=normalize_text(block.text, max_length=80),
        text=normalize_text(block.text, max_length=300),
        selector=block.selector,
    )


def _element_node(element: InteractiveElement, index: int) -> SemanticNode:
    label = normalize_text(
        element.accessibility_name or element.aria_label or element.text or element.placeholder,
        max_length=120,
    )
    return SemanticNode(
        node_id=f"node.element.{index + 1}",
        node_type=classify_element_node_type(element),
        label=label,
        text=normalize_text(element.text),
        selector=element.selector,
        metadata={
            "type": element.type,
            "role": element.role,
            "input_type": element.input_type,
            "state": element.state,
        },
    )


def _element_target(element: InteractiveElement, node_id: str, index: int) -> SemanticTarget:
    role = classify_target_role(element)
    label = normalize_text(
        element.accessibility_name or element.aria_label or element.text or element.placeholder,
        max_length=120,
    )
    return SemanticTarget(
        target_id=f"target.{role}.{index + 1}",
        target_type=element.type or "element",
        semantic_role=role,
        label=label,
        entity_ref=node_id,
        locator_candidates=[element.selector] if element.selector else [],
        confidence=0.85 if label else 0.65,
    )


def _edge(edge_type: str, source_id: str, target_id: str, index: int) -> SemanticEdge:
    return SemanticEdge(
        edge_id=f"edge.{edge_type}.{stable_hash({'s': source_id, 't': target_id, 'i': index}, length=12)}",
        edge_type=edge_type,  # type: ignore[arg-type]
        source_id=source_id,
        target_id=target_id,
    )
