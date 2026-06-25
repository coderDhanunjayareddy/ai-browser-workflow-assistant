"""
V4.0 Unit Tests — GoalDecomposer.

Tests cover:
  - Tree structure for each ActionType
  - Root node presence
  - Leaf count > 0
  - Depth > 0
  - Topic substitution in node text
  - Unique node IDs
"""
import pytest
from app.intelligence.models import ActionType, ExecutionOpportunity
from app.intelligence.goal_decomposer import GoalDecomposer


def _make_opp(action_type: ActionType) -> ExecutionOpportunity:
    return ExecutionOpportunity(
        detected=True,
        confidence=0.9,
        action_type=action_type,
        required_entities=[],
        missing_information=[],
        workflow_candidate=True,
        raw_action_keywords=[],
    )


@pytest.fixture
def decomp():
    return GoalDecomposer()


class TestBookGoalTree:
    def test_book_tree_has_root(self, decomp):
        tree = decomp.decompose("flight to Mumbai", _make_opp(ActionType.book))
        assert tree.root_id in tree.nodes

    def test_book_root_text_contains_topic(self, decomp):
        tree = decomp.decompose("flight to Mumbai", _make_opp(ActionType.book))
        root = tree.get_root()
        assert "flight to Mumbai" in root.text

    def test_book_tree_has_leaves(self, decomp):
        tree = decomp.decompose("flight", _make_opp(ActionType.book))
        assert tree.leaf_count > 0

    def test_book_tree_depth_at_least_2(self, decomp):
        tree = decomp.decompose("flight", _make_opp(ActionType.book))
        assert tree.depth >= 2

    def test_book_leaf_texts_are_strings(self, decomp):
        tree = decomp.decompose("hotel in Goa", _make_opp(ActionType.book))
        for leaf in tree.get_leaves():
            assert isinstance(leaf.text, str)
            assert len(leaf.text) > 0


class TestPurchaseGoalTree:
    def test_purchase_root_text(self, decomp):
        tree = decomp.decompose("iPhone 15", _make_opp(ActionType.purchase))
        root = tree.get_root()
        assert "iPhone 15" in root.text

    def test_purchase_has_checkout_step(self, decomp):
        tree = decomp.decompose("laptop", _make_opp(ActionType.purchase))
        texts = [n.text.lower() for n in tree.nodes.values()]
        assert any("checkout" in t or "cart" in t for t in texts)


class TestRegisterGoalTree:
    def test_register_root_text(self, decomp):
        tree = decomp.decompose("Python course", _make_opp(ActionType.register))
        root = tree.get_root()
        assert "Python course" in root.text

    def test_register_has_form_step(self, decomp):
        tree = decomp.decompose("newsletter", _make_opp(ActionType.register))
        texts = [n.text.lower() for n in tree.nodes.values()]
        assert any("form" in t or "registration" in t for t in texts)


class TestScheduleGoalTree:
    def test_schedule_root_text(self, decomp):
        tree = decomp.decompose("doctor appointment", _make_opp(ActionType.schedule))
        root = tree.get_root()
        assert "doctor appointment" in root.text

    def test_schedule_has_slot_step(self, decomp):
        tree = decomp.decompose("meeting", _make_opp(ActionType.schedule))
        texts = [n.text.lower() for n in tree.nodes.values()]
        assert any("slot" in t or "availability" in t for t in texts)


class TestUnknownGoalTree:
    def test_unknown_produces_generic_tree(self, decomp):
        tree = decomp.decompose("something complex", _make_opp(ActionType.unknown))
        assert tree.root_id in tree.nodes
        assert tree.leaf_count > 0


class TestNodeUniqueness:
    def test_all_node_ids_unique(self, decomp):
        tree = decomp.decompose("flight", _make_opp(ActionType.book))
        ids = list(tree.nodes.keys())
        assert len(ids) == len(set(ids))


class TestParentChildLinks:
    def test_root_has_no_parent(self, decomp):
        tree = decomp.decompose("test", _make_opp(ActionType.book))
        root = tree.get_root()
        assert root.parent_id is None

    def test_children_exist_in_nodes(self, decomp):
        tree = decomp.decompose("test", _make_opp(ActionType.book))
        for node in tree.nodes.values():
            for child_id in node.children:
                assert child_id in tree.nodes

    def test_leaves_have_no_children(self, decomp):
        tree = decomp.decompose("test", _make_opp(ActionType.purchase))
        for leaf in tree.get_leaves():
            assert leaf.children == []
