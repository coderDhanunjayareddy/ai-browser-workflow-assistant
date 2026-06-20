from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class TaskNode(BaseModel):
    """
    Component 2: Task Graph Engine - Single Node
    Represents a specific subtask within a workflow.
    """
    node_id: str
    description: str
    prerequisites: List[str] = Field(default_factory=list)
    validators: List[str] = Field(default_factory=list)
    status: str = "pending"  # pending | active | completed | failed
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TaskGraph(BaseModel):
    """
    Represents a full directed acyclic graph (DAG) of task steps.
    """
    graph_id: str
    nodes: List[TaskNode] = Field(default_factory=list)

    def get_node(self, node_id: str) -> Optional[TaskNode]:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def is_completed(self) -> bool:
        return all(node.status == "completed" for node in self.nodes)
