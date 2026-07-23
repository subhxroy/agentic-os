"""
Federated Agent Negotiation & Swarm Protocol for Agentic OS
============================================================
Implements peer-to-peer federated agent network protocols, multi-agent negotiation contracts,
subagent swarm delegation, and skill marketplace reputation scoring.
"""

from __future__ import annotations

import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional


class FederatedNetwork:
    """
    Federated Agent Network Protocol Manager.
    Manages peer agent discovery, multi-agent negotiation contracts, and skill reputation scoring.
    """

    def __init__(self, node_id: Optional[str] = None, storage_dir: Optional[Path] = None):
        if node_id is None:
            node_id = f"node_{hashlib.sha256(str(time.time()).encode('utf-8')).hexdigest()[:8]}"
        self.node_id = node_id
        if storage_dir is None:
            storage_dir = Path.home() / ".agentic_os" / "federated"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.peers_file = self.storage_dir / "peers.json"
        self.contracts_file = self.storage_dir / "contracts.json"
        self.reputation_file = self.storage_dir / "reputation.json"
        self._load_state()

    def _load_state(self):
        self.peers = json.loads(self.peers_file.read_text("utf-8")) if self.peers_file.exists() else {}
        self.contracts = json.loads(self.contracts_file.read_text("utf-8")) if self.contracts_file.exists() else {}
        self.reputation = json.loads(self.reputation_file.read_text("utf-8")) if self.reputation_file.exists() else {}

    def _save_state(self):
        self.peers_file.write_text(json.dumps(self.peers, indent=2), encoding="utf-8")
        self.contracts_file.write_text(json.dumps(self.contracts, indent=2), encoding="utf-8")
        self.reputation_file.write_text(json.dumps(self.reputation, indent=2), encoding="utf-8")

    def register_peer(self, peer_id: str, endpoint: str, capabilities: List[str]) -> Dict[str, Any]:
        """Registers a remote peer Agentic OS instance."""
        record = {
            "peer_id": peer_id,
            "endpoint": endpoint,
            "capabilities": capabilities,
            "last_seen": time.time(),
            "status": "online",
        }
        self.peers[peer_id] = record
        self._save_state()
        return {"status": "success", "peer": record}

    def propose_contract(
        self,
        target_peer_id: str,
        task_description: str,
        requirements: List[str],
        token_grant: int = 5000,
    ) -> Dict[str, Any]:
        """Initiates a multi-agent negotiation contract for subtask delegation."""
        contract_id = f"contract_{hashlib.sha256(f'{self.node_id}:{target_peer_id}:{time.time()}'.encode('utf-8')).hexdigest()[:12]}"
        contract = {
            "contract_id": contract_id,
            "initiator": self.node_id,
            "assignee": target_peer_id,
            "task": task_description,
            "requirements": requirements,
            "token_grant": token_grant,
            "status": "proposed",
            "created_at": time.time(),
        }
        self.contracts[contract_id] = contract
        self._save_state()
        return {"status": "success", "contract": contract}

    def rate_skill(self, skill_name: str, score: float, feedback: str = ""):
        """Submits a reputation score (0.0 to 5.0) for a skill or agent capability."""
        score = max(0.0, min(5.0, score))
        if skill_name not in self.reputation:
            self.reputation[skill_name] = {"ratings_count": 0, "average_score": 0.0, "reviews": []}

        rep = self.reputation[skill_name]
        total_score = (rep["average_score"] * rep["ratings_count"]) + score
        rep["ratings_count"] += 1
        rep["average_score"] = round(total_score / rep["ratings_count"], 2)
        rep["reviews"].append({"rater": self.node_id, "score": score, "feedback": feedback, "timestamp": time.time()})
        self._save_state()
        return rep

    def get_skill_reputation(self, skill_name: str) -> Dict[str, Any]:
        return self.reputation.get(skill_name, {"ratings_count": 0, "average_score": 0.0, "reviews": []})
