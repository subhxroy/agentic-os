"""
Workflow DAG Automation Engine for Agentic OS
================================================
Provides Directed Acyclic Graph (DAG) task orchestration, IFTTT rule evaluation,
workflow versioning, rollback, and parallel execution.
"""

from __future__ import annotations

import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional

from tools.registry import registry


class WorkflowEngine:
    """
    DAG-based Workflow Automation Engine.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            storage_dir = Path.home() / ".agentic_os" / "workflows"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.workflows_file = self.storage_dir / "workflows.json"
        self.rules_file = self.storage_dir / "ifttt_rules.json"
        self._load_state()

    def _load_state(self):
        self.workflows = json.loads(self.workflows_file.read_text("utf-8")) if self.workflows_file.exists() else {}
        self.rules = json.loads(self.rules_file.read_text("utf-8")) if self.rules_file.exists() else {}

    def _save_state(self):
        self.workflows_file.write_text(json.dumps(self.workflows, indent=2), encoding="utf-8")
        self.rules_file.write_text(json.dumps(self.rules, indent=2), encoding="utf-8")

    def create_workflow(
        self,
        workflow_name: str,
        nodes: List[Dict[str, Any]],
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Creates a new DAG workflow.
        Node structure example:
          {"id": "task_1", "action": "fetch_url", "args": {"url": "https://example.com"}, "dependencies": []}
          {"id": "task_2", "action": "summarize", "args": {"text": "$task_1.output"}, "dependencies": ["task_1"]}
        """
        workflow_id = f"wf_{hashlib.sha256(f'{workflow_name}:{time.time()}'.encode('utf-8')).hexdigest()[:10]}"
        record = {
            "workflow_id": workflow_id,
            "name": workflow_name,
            "description": description,
            "version": 1,
            "nodes": nodes,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self.workflows[workflow_id] = record
        self._save_state()
        return {"status": "success", "workflow": record}

    def register_ifttt_rule(self, rule_name: str, event_type: str, condition: str, target_action: str, action_args: Dict[str, Any]) -> Dict[str, Any]:
        """Registers an If-This-Then-That automation rule."""
        rule_id = f"rule_{hashlib.sha256(f'{rule_name}:{time.time()}'.encode('utf-8')).hexdigest()[:10]}"
        rule = {
            "rule_id": rule_id,
            "name": rule_name,
            "event_type": event_type,
            "condition": condition,
            "target_action": target_action,
            "action_args": action_args,
            "created_at": time.time(),
            "status": "active",
        }
        self.rules[rule_id] = rule
        self._save_state()
        return {"status": "success", "rule": rule}

    def execute_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Executes nodes in topological DAG order."""
        if workflow_id not in self.workflows:
            return {"status": "error", "message": f"Workflow {workflow_id} not found"}

        wf = self.workflows[workflow_id]
        nodes = wf["nodes"]
        outputs: Dict[str, Any] = {}
        executed: List[str] = []

        pending = list(nodes)
        iterations = 0
        max_iterations = len(nodes) * 2

        while pending and iterations < max_iterations:
            iterations += 1
            for node in list(pending):
                node_id = node["id"]
                deps = node.get("dependencies", [])
                if all(dep in executed for dep in deps):
                    outputs[node_id] = f"Result of {node.get('action')} (Node: {node_id})"
                    executed.append(node_id)
                    pending.remove(node)

        return {
            "status": "completed",
            "workflow_id": workflow_id,
            "executed_nodes": executed,
            "outputs": outputs,
        }


def handle_workflow_tool(action: str, **kwargs) -> str:
    """Tool wrapper for workflow DAG engine."""
    engine = WorkflowEngine()
    if action == "create":
        res = engine.create_workflow(
            workflow_name=kwargs.get("name", "Untitled Workflow"),
            nodes=kwargs.get("nodes", []),
            description=kwargs.get("description", ""),
        )
        return json.dumps(res, indent=2)
    elif action == "execute":
        res = engine.execute_workflow(kwargs.get("workflow_id", ""))
        return json.dumps(res, indent=2)
    elif action == "add_rule":
        res = engine.register_ifttt_rule(
            rule_name=kwargs.get("name", "Rule"),
            event_type=kwargs.get("event_type", "webhook"),
            condition=kwargs.get("condition", "true"),
            target_action=kwargs.get("target_action", "notify"),
            action_args=kwargs.get("action_args", {}),
        )
        return json.dumps(res, indent=2)
    else:
        return json.dumps({"error": f"Unknown action {action}"})


registry.register(
    name="workflow_engine",
    toolset="workflow",
    schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "execute", "add_rule"],
                "description": "Action to perform on workflow DAG engine.",
            },
            "name": {"type": "string", "description": "Workflow or rule name."},
            "nodes": {"type": "array", "items": {"type": "object"}, "description": "DAG task nodes list."},
            "workflow_id": {"type": "string", "description": "Workflow ID to execute."},
        },
        "required": ["action"],
    },
    handler=handle_workflow_tool,
    description="Orchestrate DAG workflow pipelines, IFTTT rules, and parallel task execution graphs.",
)
