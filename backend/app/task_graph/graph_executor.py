import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.db import TaskNode as DBTaskNode
from app.task_graph.graph_models import TaskGraph, TaskNode

logger = logging.getLogger(__name__)

class TaskGraphExecutor:
    """
    Component 2: Task Graph Executor
    Coordinates loading, saving, and executing task nodes inside the DB.
    """
    def __init__(self, db: Session, session_id: str):
        self.db = db
        self.session_id = session_id

    def load_graph(self) -> Optional[TaskGraph]:
        """
        Loads the task graph nodes for this session from the database.
        """
        db_nodes = self.db.query(DBTaskNode).filter(DBTaskNode.session_id == self.session_id).all()
        if not db_nodes:
            return None
        
        nodes = []
        for db_node in db_nodes:
            nodes.append(TaskNode(
                node_id=db_node.node_id,
                description=db_node.description or "",
                prerequisites=db_node.prerequisites or [],
                validators=db_node.validators or [],
                status=db_node.status,
                metadata={}
            ))
        
        # Determine graph_id from session context or metadata
        return TaskGraph(graph_id=f"graph_{self.session_id[-4:]}", nodes=nodes)

    def initialize_graph(self, template_graph: TaskGraph) -> TaskGraph:
        """
        Persists a new task graph into the database from a template.
        """
        # Clean up existing nodes if any
        self.db.query(DBTaskNode).filter(DBTaskNode.session_id == self.session_id).delete()
        self.db.commit()

        for node in template_graph.nodes:
            db_node = DBTaskNode(
                session_id=self.session_id,
                node_id=node.node_id,
                description=node.description,
                status=node.status,
                prerequisites=node.prerequisites,
                validators=node.validators,
                updated_at=datetime.utcnow()
            )
            self.db.add(db_node)
        
        self.db.commit()
        logger.info(f"Initialized task graph {template_graph.graph_id} for session {self.session_id}")
        return template_graph

    def get_eligible_nodes(self, graph: TaskGraph) -> List[TaskNode]:
        """
        Returns all nodes whose prerequisites are fully met and are not completed/failed.
        """
        eligible = []
        for node in graph.nodes:
            if node.status in ["completed", "failed"]:
                continue
            
            # Check prerequisites
            prereqs_met = True
            for prereq_id in node.prerequisites:
                prereq_node = graph.get_node(prereq_id)
                if not prereq_node or prereq_node.status != "completed":
                    prereqs_met = False
                    break
            
            if prereqs_met:
                eligible.append(node)
        return eligible

    def get_active_nodes(self) -> List[TaskNode]:
        """
        Returns currently active nodes in database.
        """
        graph = self.load_graph()
        if not graph:
            return []
        return [node for node in graph.nodes if node.status == "active"]

    def update_node_status(self, node_id: str, status: str) -> None:
        """
        Updates a node's status in the database and activates subsequent nodes.
        """
        db_node = self.db.query(DBTaskNode).filter(
            DBTaskNode.session_id == self.session_id,
            DBTaskNode.node_id == node_id
        ).first()
        
        if db_node:
            db_node.status = status
            db_node.updated_at = datetime.utcnow()
            self.db.commit()
            logger.info(f"Updated node {node_id} status to {status}")
            
            # If completed, check and activate newly eligible nodes
            if status == "completed":
                self.activate_next_nodes()

    def activate_next_nodes(self) -> None:
        """
        Finds and activates nodes that are now eligible to execute.
        """
        graph = self.load_graph()
        if not graph:
            return
            
        eligible = self.get_eligible_nodes(graph)
        for node in eligible:
            if node.status == "pending":
                self.update_node_status(node.node_id, "active")
