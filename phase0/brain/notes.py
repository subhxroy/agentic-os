import uuid
import json
import re
from datetime import datetime
from typing import Optional
from database import pg_query, pg_execute, pg_execute_returning


def create_note(user_id: str, title: str, content: str = "",
                tags: list = None, org_id: str = None) -> dict:
    note_id = str(uuid.uuid4())
    links = _extract_wikilinks(content)
    pg_execute(
        """INSERT INTO brain_notes (id, user_id, org_id, title, content, tags, links)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (note_id, user_id, org_id, title, content,
         json.dumps(tags or []), json.dumps(links))
    )
    _sync_backlinks(note_id, links, user_id)
    return get_note(note_id)


def get_note(note_id: str) -> Optional[dict]:
    rows = pg_query(
        """SELECT id, user_id, org_id, title, content, tags, links,
                  word_count, created_at, updated_at
           FROM brain_notes WHERE id = %s""",
        (note_id,)
    )
    if not rows:
        return None
    note = rows[0]
    note["backlinks"] = get_backlinks(note_id)
    return note


def update_note(note_id: str, user_id: str, title: str = None,
                content: str = None, tags: list = None) -> Optional[dict]:
    note = pg_query(
        "SELECT user_id, links FROM brain_notes WHERE id = %s", (note_id,)
    )
    if not note or note[0]["user_id"] != user_id:
        return None
    updates, params = [], []
    if title is not None:
        updates.append("title = %s")
        params.append(title)
    if content is not None:
        updates.append("content = %s")
        params.append(content)
        links = _extract_wikilinks(content)
        updates.append("links = %s")
        params.append(json.dumps(links))
    if tags is not None:
        updates.append("tags = %s")
        params.append(json.dumps(tags))
    if not updates:
        return get_note(note_id)
    updates.append("updated_at = NOW()")
    params.append(note_id)
    pg_execute(f"UPDATE brain_notes SET {', '.join(updates)} WHERE id = %s", params)
    if content is not None:
        _sync_backlinks(note_id, _extract_wikilinks(content), user_id)
    return get_note(note_id)


def delete_note(note_id: str, user_id: str) -> bool:
    pg_execute(
        "DELETE FROM brain_notes WHERE id = %s AND user_id = %s",
        (note_id, user_id)
    )
    return True


def list_notes(user_id: str, org_id: str = None, tag: str = None,
               limit: int = 50, offset: int = 0) -> list[dict]:
    where = ["user_id = %s"]
    params = [user_id]
    if org_id:
        where.append("org_id = %s")
        params.append(org_id)
    if tag:
        where.append("tags LIKE ?")
        params.append(f'%"{tag}"%')
    params.append(limit)
    params.append(offset)
    where_clause = " AND ".join(where)
    return pg_query(
        f"""SELECT id, title, tags, links, word_count, created_at, updated_at
            FROM brain_notes WHERE {where_clause}
            ORDER BY updated_at DESC LIMIT %s OFFSET %s""",
        params
    )


def search_notes(user_id: str, query: str, limit: int = 20) -> list[dict]:
    q = f"%{query}%"
    rows = pg_query(
        """SELECT id, title, substr(content, 1, 200) as preview, tags, 0 as rank
           FROM brain_notes
           WHERE user_id = ?
             AND (title LIKE ? OR content LIKE ?)
           ORDER BY updated_at DESC LIMIT ?""",
        (user_id, q, q, limit)
    )
    return rows


def get_graph_data(user_id: str, org_id: str = None) -> dict:
    where = ["user_id = %s"]
    params = [user_id]
    if org_id:
        where.append("org_id = %s")
        params.append(org_id)
    where_clause = " AND ".join(where)

    notes = pg_query(
        f"""SELECT id, title, tags, links FROM brain_notes
            WHERE {where_clause} ORDER BY title""",
        params
    )

    nodes = []
    edges = []
    note_map = {n["id"]: n for n in notes}

    for note in notes:
        nodes.append({
            "id": note["id"],
            "label": note["title"],
            "tags": note.get("tags", []),
        })
        for link_title in (note.get("links") or []):
            target = _find_note_by_title(notes, link_title)
            if target:
                edges.append({
                    "source": note["id"],
                    "target": target["id"],
                    "label": link_title,
                    "type": "wikilink",
                })

    return {"nodes": nodes, "edges": edges}


def get_backlinks(note_id: str) -> list[dict]:
    title = _get_note_title(note_id)
    if not title:
        return []
    rows = pg_query(
        """SELECT id, title FROM brain_notes
           WHERE links LIKE ?""",
        (f'%"{title}"%',)
    )
    return rows


def _extract_wikilinks(content: str) -> list[str]:
    if not content:
        return []
    return list(set(re.findall(r'\[\[([^\]]+)\]\]', content)))


def _find_note_by_title(notes: list, title: str) -> Optional[dict]:
    for n in notes:
        if n["title"].lower() == title.lower():
            return n
    return None


def _get_note_title(note_id: str) -> str:
    rows = pg_query("SELECT title FROM brain_notes WHERE id = %s", (note_id,))
    return rows[0]["title"] if rows else ""


def _sync_backlinks(note_id: str, links: list[str], user_id: str):
    for link_title in links:
        existing = pg_query(
            "SELECT id FROM brain_notes WHERE user_id = %s AND title = %s",
            (user_id, link_title)
        )
        if not existing:
            create_note(user_id, link_title, content="", org_id=None)
