import pytest
from app.task_graph.graph_models import TaskGraph, TaskNode
from app.task_graph.graph_executor import TaskGraphExecutor

def test_task_graph_traversal():
    nodes = [
        TaskNode(node_id="step_1", description="Navigate to page", status="completed"),
        TaskNode(node_id="step_2", description="Click Search input", prerequisites=["step_1"], status="pending"),
        TaskNode(node_id="step_3", description="Type Query", prerequisites=["step_2"], status="pending")
    ]
    graph = TaskGraph(graph_id="test_graph", nodes=nodes)
    executor = TaskGraphExecutor(None, "test_session")
    
    # Prerequisite step_1 is completed, so step_2 should be eligible
    eligible = executor.get_eligible_nodes(graph)
    assert len(eligible) == 1
    assert eligible[0].node_id == "step_2"

    # If step_2 is not completed, step_3 should NOT be eligible
    # Let's confirm
    assert all(n.node_id != "step_3" for n in eligible)
