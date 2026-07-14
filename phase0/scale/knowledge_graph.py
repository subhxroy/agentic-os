"""Knowledge Graph — entity/relationship memory graph with traversal."""

import uuid
import json
from collections import defaultdict, deque
from typing import List, Dict, Optional, Set
from database import pg_query, pg_execute


# ============================================================
# Entities
# ============================================================
def create_entity(org_id: str, entity_type: str, name: str,
                  description: str = None, properties: dict = None,
                  user_id: str = None) -> dict:
    entity_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO kg_entities (id, org_id, user_id, entity_type, name, description, properties)
           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (entity_id, org_id, user_id, entity_type, name, description, json.dumps(properties or {}))
    )
    return get_entity(entity_id)


def get_entity(entity_id: str) -> dict:
    rows = pg_query("SELECT * FROM kg_entities WHERE id = %s", (entity_id,))
    return rows[0] if rows else None


def search_entities(org_id: str, query: str = None, entity_type: str = None,
                    limit: int = 50) -> list:
    where = ["org_id = %s"]
    params = [org_id]
    if query:
        where.append("name ILIKE %s")
        params.append(f"%{query}%")
    if entity_type:
        where.append("entity_type = %s")
        params.append(entity_type)
    params.append(limit)
    return pg_query(
        f"""SELECT * FROM kg_entities WHERE {' AND '.join(where)}
            ORDER BY created_at DESC LIMIT %s""",
        params
    )


def update_entity(entity_id: str, **kwargs) -> dict:
    allowed = {"name", "description", "properties", "entity_type"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_entity(entity_id)
    set_parts = []
    values = []
    for k, v in updates.items():
        if k == "properties":
            set_parts.append(f"{k} = %s::jsonb")
            values.append(json.dumps(v))
        else:
            set_parts.append(f"{k} = %s")
            values.append(v)
    pg_execute(f"UPDATE kg_entities SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s",
               values + [entity_id])
    return get_entity(entity_id)


def delete_entity(entity_id: str) -> bool:
    pg_execute("DELETE FROM kg_entities WHERE id = %s", (entity_id,))
    return True


def get_entity_neighbors(entity_id: str, direction: str = "both", rel_type: str = None,
                         limit: int = 50) -> dict:
    """Get neighbors of an entity (outgoing, incoming, or both)."""
    neighbors = {"outgoing": [], "incoming": []}

    if direction in ("outgoing", "both"):
        where = ["r.source_id = %s"]
        params = [entity_id]
        if rel_type:
            where.append("r.relationship_type = %s")
            params.append(rel_type)
        params.append(limit)
        neighbors["outgoing"] = pg_query(
            f"""SELECT r.*, t.name as target_name, t.entity_type as target_type
                FROM kg_relationships r JOIN kg_entities t ON r.target_id = t.id
                WHERE {' AND '.join(where)} ORDER BY r.weight DESC LIMIT %s""",
            params
        )

    if direction in ("incoming", "both"):
        where = ["r.target_id = %s"]
        params = [entity_id]
        if rel_type:
            where.append("r.relationship_type = %s")
            params.append(rel_type)
        params.append(limit)
        neighbors["incoming"] = pg_query(
            f"""SELECT r.*, s.name as source_name, s.entity_type as source_type
                FROM kg_relationships r JOIN kg_entities s ON r.source_id = s.id
                WHERE {' AND '.join(where)} ORDER BY r.weight DESC LIMIT %s""",
            params
        )

    return neighbors


# ============================================================
# Relationships
# ============================================================
def create_relationship(source_id: str, target_id: str, relationship_type: str,
                        weight: float = 1.0, properties: dict = None) -> dict:
    rel_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO kg_relationships (id, source_id, target_id, relationship_type, weight, properties)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb)
           ON CONFLICT (source_id, target_id, relationship_type)
           DO UPDATE SET weight = EXCLUDED.weight, properties = EXCLUDED.properties""",
        (rel_id, source_id, target_id, relationship_type, weight, json.dumps(properties or {}))
    )
    rows = pg_query("SELECT * FROM kg_relationships WHERE source_id = %s AND target_id = %s AND relationship_type = %s",
                     (source_id, target_id, relationship_type))
    return rows[0] if rows else {"id": rel_id}


def delete_relationship(source_id: str, target_id: str, relationship_type: str) -> bool:
    pg_execute(
        "DELETE FROM kg_relationships WHERE source_id = %s AND target_id = %s AND relationship_type = %s",
        (source_id, target_id, relationship_type)
    )
    return True


# ============================================================
# Graph Traversal
# ============================================================
def traverse_bfs(start_id: str, max_depth: int = 3, rel_type: str = None,
                 limit: int = 100) -> dict:
    """BFS traversal from a starting entity. Returns nodes and edges visited."""
    visited_nodes: Set[str] = set()
    visited_edges: list = []
    queue = deque([(start_id, 0)])
    node_map = {}

    while queue and len(visited_nodes) < limit:
        current_id, depth = queue.popleft()
        if current_id in visited_nodes or depth > max_depth:
            continue

        entity = get_entity(current_id)
        if not entity:
            continue
        visited_nodes.add(current_id)
        node_map[current_id] = entity

        neighbors = get_entity_neighbors(current_id, direction="both", rel_type=rel_type, limit=20)
        for edge in neighbors["outgoing"]:
            edge_id = edge["id"]
            visited_edges.append({
                "id": edge_id,
                "source": current_id,
                "target": edge["target_id"],
                "type": edge["relationship_type"],
                "weight": float(edge["weight"]),
            })
            if edge["target_id"] not in visited_nodes:
                queue.append((edge["target_id"], depth + 1))

        for edge in neighbors["incoming"]:
            edge_id = edge["id"]
            visited_edges.append({
                "id": edge_id,
                "source": edge["source_id"],
                "target": current_id,
                "type": edge["relationship_type"],
                "weight": float(edge["weight"]),
            })
            if edge["source_id"] not in visited_nodes:
                queue.append((edge["source_id"], depth + 1))

    return {"nodes": list(node_map.values()), "edges": visited_edges}


def find_path(source_id: str, target_id: str, max_depth: int = 5) -> list:
    """Find shortest path between two entities using BFS."""
    if source_id == target_id:
        return [source_id]

    visited = {source_id}
    queue = deque([(source_id, [source_id])])

    while queue:
        current_id, path = queue.popleft()
        if len(path) > max_depth:
            continue

        neighbors = get_entity_neighbors(current_id, direction="outgoing", limit=50)
        for edge in neighbors["outgoing"]:
            next_id = edge["target_id"]
            if next_id == target_id:
                return path + [next_id]
            if next_id not in visited:
                visited.add(next_id)
                queue.append((next_id, path + [next_id]))

    return []


# ============================================================
# Stats & Snapshots
# ============================================================
def get_graph_stats(org_id: str) -> dict:
    entity_count = pg_query(
        "SELECT COUNT(*) as c FROM kg_entities WHERE org_id = %s", (org_id,)
    )
    rel_count = pg_query(
        """SELECT COUNT(*) as c FROM kg_relationships r
           JOIN kg_entities e ON r.source_id = e.id WHERE e.org_id = %s""", (org_id,)
    )
    types = pg_query(
        """SELECT entity_type, COUNT(*) as count FROM kg_entities
           WHERE org_id = %s GROUP BY entity_type ORDER BY count DESC""", (org_id,)
    )
    rel_types = pg_query(
        """SELECT r.relationship_type, COUNT(*) as count
           FROM kg_relationships r JOIN kg_entities e ON r.source_id = e.id
           WHERE e.org_id = %s GROUP BY r.relationship_type ORDER BY count DESC""", (org_id,)
    )
    return {
        "entity_count": entity_count[0]["c"] if entity_count else 0,
        "relationship_count": rel_count[0]["c"] if rel_count else 0,
        "entity_types": types,
        "relationship_types": rel_types,
    }


def create_snapshot(org_id: str) -> dict:
    stats = get_graph_stats(org_id)
    snapshot_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO kg_snapshots (id, org_id, entity_count, relationship_count, snapshot_data)
           VALUES (%s, %s, %s, %s, %s::jsonb)""",
        (snapshot_id, org_id, stats["entity_count"], stats["relationship_count"],
         json.dumps(stats))
    )
    return {"id": snapshot_id, **stats}
