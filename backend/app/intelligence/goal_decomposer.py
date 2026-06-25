"""
V4.0 Component 2 — GoalDecomposer.

Converts a user objective into a structured GoalTree.
All decomposition is deterministic pattern-based — no LLM.

Each ActionType maps to a canonical goal tree template.
The root node represents the top-level goal; leaf nodes are the
individual steps the workflow engine would execute.
"""
from __future__ import annotations

import uuid

from app.intelligence.models import ActionType, ExecutionOpportunity, GoalNode, GoalTree

# ── Goal tree templates per ActionType ───────────────────────────────────────
# Each template is a list of (depth, label) tuples.
# Depth 0 = root, depth 1 = subgoal, depth 2 = leaf.

_TEMPLATES: dict[ActionType, list[tuple[int, str]]] = {
    ActionType.book: [
        (0, "Book {topic}"),
        (1, "Research available options"),
        (2, "Compare prices"),
        (2, "Verify timing and availability"),
        (2, "Select best option"),
        (1, "Complete booking"),
        (2, "Fill in traveler details"),
        (2, "Confirm and finalize booking"),
    ],
    ActionType.purchase: [
        (0, "Purchase {topic}"),
        (1, "Find the product"),
        (2, "Search for {topic}"),
        (2, "Check specifications and reviews"),
        (1, "Complete purchase"),
        (2, "Add to cart"),
        (2, "Proceed to checkout"),
    ],
    ActionType.register: [
        (0, "Register for {topic}"),
        (1, "Prepare registration information"),
        (2, "Gather email and personal details"),
        (1, "Complete registration"),
        (2, "Fill registration form"),
        (2, "Confirm registration"),
    ],
    ActionType.schedule: [
        (0, "Schedule {topic}"),
        (1, "Identify date and time"),
        (2, "Check availability"),
        (2, "Select preferred slot"),
        (1, "Confirm scheduling"),
        (2, "Fill scheduling form"),
        (2, "Send confirmation"),
    ],
    ActionType.download: [
        (0, "Download {topic}"),
        (1, "Locate download source"),
        (2, "Find official download page"),
        (1, "Complete download"),
        (2, "Select version and platform"),
        (2, "Initiate download"),
    ],
    ActionType.communicate: [
        (0, "Send message about {topic}"),
        (1, "Prepare message"),
        (2, "Identify recipient"),
        (2, "Compose message content"),
        (1, "Send message"),
        (2, "Review before sending"),
        (2, "Confirm send"),
    ],
    ActionType.navigate: [
        (0, "Navigate to {topic}"),
        (1, "Open page"),
        (2, "Enter URL or search"),
        (1, "Verify destination"),
        (2, "Confirm correct page loaded"),
    ],
    ActionType.rent: [
        (0, "Rent {topic}"),
        (1, "Find rental options"),
        (2, "Search available listings"),
        (2, "Compare options"),
        (1, "Complete rental"),
        (2, "Fill booking details"),
        (2, "Confirm rental"),
    ],
    ActionType.apply: [
        (0, "Apply for {topic}"),
        (1, "Prepare application"),
        (2, "Gather required documents"),
        (2, "Fill application form"),
        (1, "Submit application"),
        (2, "Review application"),
        (2, "Submit and confirm"),
    ],
    ActionType.search: [
        (0, "Search for {topic}"),
        (1, "Execute search"),
        (2, "Enter search query"),
        (2, "Review results"),
    ],
    ActionType.unknown: [
        (0, "Complete task: {topic}"),
        (1, "Analyze requirements"),
        (2, "Identify necessary steps"),
        (1, "Execute task"),
        (2, "Follow through to completion"),
    ],
}


def _build_tree(template: list[tuple[int, str]], topic: str) -> GoalTree:
    """Convert a flat depth-label template into a GoalTree."""
    nodes: dict[str, GoalNode] = {}
    stack: list[str] = []   # stack of node_ids by depth
    root_id: str = ""

    for depth, label in template:
        node_id = str(uuid.uuid4())[:8]
        text = label.format(topic=topic)
        is_leaf = True  # will be reset if children are added

        parent_id: str | None = None
        if depth == 0:
            root_id = node_id
            stack = [node_id]
        else:
            # Parent is the last node at depth-1
            while len(stack) > depth:
                stack.pop()
            parent_id = stack[-1] if stack else None
            if parent_id:
                parent_node = nodes.get(parent_id)
                if parent_node:
                    parent_node.children.append(node_id)
                    parent_node.is_leaf = False

            # Extend stack to current depth
            while len(stack) < depth:
                stack.append(stack[-1])
            if len(stack) == depth:
                stack.append(node_id)
            else:
                stack[depth] = node_id

        node = GoalNode(
            node_id=node_id,
            text=text,
            parent_id=parent_id,
            children=[],
            is_leaf=is_leaf,
        )
        nodes[node_id] = node

    max_depth = max((t[0] for t in template), default=0)
    leaf_count = sum(1 for n in nodes.values() if n.is_leaf)

    return GoalTree(
        root_id=root_id,
        nodes=nodes,
        depth=max_depth,
        leaf_count=leaf_count,
    )


class GoalDecomposer:
    """
    Decomposes user objectives into structured GoalTrees using pattern templates.
    Deterministic — same action_type always produces the same tree shape.
    """

    def decompose(
        self,
        topic: str,
        opportunity: ExecutionOpportunity,
    ) -> GoalTree:
        """
        Build a GoalTree for the given topic and detected opportunity.

        Args:
            topic: the research topic or user goal text
            opportunity: the detected execution opportunity
        """
        template = _TEMPLATES.get(opportunity.action_type, _TEMPLATES[ActionType.unknown])
        return _build_tree(template, topic)


# Module-level singleton
decomposer = GoalDecomposer()
