"""Agent Scheduler — custom priority task queue with concurrency control."""

import uuid
import time
import json
import threading
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional
from database import pg_query, pg_execute


# ============================================================
# Task Management
# ============================================================
def create_task(org_id: str, task_type: str, payload: dict = None,
                priority: int = 5, user_id: str = None,
                scheduled_at: datetime = None, max_retries: int = 3) -> dict:
    task_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO scheduler_tasks
           (id, org_id, user_id, task_type, payload, priority, max_retries, scheduled_at)
           VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)""",
        (task_id, org_id, user_id, task_type, json.dumps(payload or {}),
         priority, max_retries, scheduled_at or datetime.utcnow())
    )
    return get_task(task_id)


def get_task(task_id: str) -> dict:
    rows = pg_query("SELECT * FROM scheduler_tasks WHERE id = %s", (task_id,))
    return rows[0] if rows else None


def list_tasks(org_id: str = None, status: str = None, task_type: str = None,
               limit: int = 50) -> list:
    where = []
    params = []
    if org_id:
        where.append("org_id = %s")
        params.append(org_id)
    if status:
        where.append("status = %s")
        params.append(status)
    if task_type:
        where.append("task_type = %s")
        params.append(task_type)
    params.append(limit)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    return pg_query(
        f"""SELECT * FROM scheduler_tasks {where_clause}
            ORDER BY priority DESC, scheduled_at ASC LIMIT %s""",
        params
    )


def claim_task(worker_id: str, task_type: str = None) -> Optional[dict]:
    """Claim the highest-priority pending task for a worker."""
    where = ["status = 'pending'", "scheduled_at <= datetime('now')"]
    params = []
    if task_type:
        where.append("task_type = ?")
        params.append(task_type)

    # First find the task, then update it
    pending = pg_query(
        f"""SELECT id FROM scheduler_tasks
            WHERE {' AND '.join(where)}
            ORDER BY priority DESC, scheduled_at ASC
            LIMIT 1""",
        params
    )
    if not pending:
        return None

    task_id = pending[0]["id"]
    pg_execute(
        """UPDATE scheduler_tasks SET status = 'running', worker_id = %s,
           started_at = NOW(), retry_count = retry_count + 1
           WHERE id = %s""",
        (worker_id, task_id)
    )
    return get_task(task_id)


def complete_task(task_id: str) -> dict:
    pg_execute(
        "UPDATE scheduler_tasks SET status = 'completed', completed_at = NOW() WHERE id = %s",
        (task_id,)
    )
    return get_task(task_id)


def fail_task(task_id: str, error: str) -> dict:
    task = get_task(task_id)
    if not task:
        return None
    if task["retry_count"] < task["max_retries"]:
        # SQLite: use datetime to add exponential backoff
        import math
        backoff_minutes = int(math.pow(2, task["retry_count"]))
        pg_execute(
            """UPDATE scheduler_tasks SET status = 'retry', last_error = ?,
               scheduled_at = datetime('now', '+' || ? || ' minutes')
               WHERE id = ?""",
            (error, backoff_minutes, task_id)
        )
    else:
        pg_execute(
            "UPDATE scheduler_tasks SET status = 'failed', last_error = %s WHERE id = %s",
            (error, task_id)
        )
    return get_task(task_id)


def cancel_task(task_id: str) -> dict:
    pg_execute(
        "UPDATE scheduler_tasks SET status = 'cancelled' WHERE id = %s AND status = 'pending'",
        (task_id,)
    )
    return get_task(task_id)


# ============================================================
# Workers
# ============================================================
def register_worker(worker_id: str, org_id: str = None, max_concurrency: int = 5) -> dict:
    pg_execute(
        """INSERT INTO scheduler_workers (id, org_id, max_concurrency)
           VALUES (%s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET status = 'idle', last_heartbeat = NOW()""",
        (worker_id, org_id, max_concurrency)
    )
    return get_worker(worker_id)


def get_worker(worker_id: str) -> dict:
    rows = pg_query("SELECT * FROM scheduler_workers WHERE id = %s", (worker_id,))
    return rows[0] if rows else None


def heartbeat(worker_id: str) -> dict:
    pg_execute(
        "UPDATE scheduler_workers SET last_heartbeat = datetime('now') WHERE id = ?",
        (worker_id,)
    )
    return get_worker(worker_id)


def get_available_workers(org_id: str = None) -> list:
    where = ["status != 'offline'"]
    params = []
    if org_id:
        where.append("org_id = ?")
        params.append(org_id)
    cutoff = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    where.append("(last_heartbeat IS NULL OR last_heartbeat > ?)")
    params.append(cutoff)
    return pg_query(
        f"""SELECT * FROM scheduler_workers WHERE {' AND '.join(where)}
            ORDER BY active_count ASC""",
        params
    )


# ============================================================
# Scheduler Loop (simplified in-process)
# ============================================================
_handlers: Dict[str, Callable] = {}
_scheduler_running = False


def register_handler(task_type: str, handler: Callable):
    """Register a handler function for a task type."""
    _handlers[task_type] = handler


def process_next_task(worker_id: str = "default") -> Optional[dict]:
    """Claim and execute the next available task."""
    task = claim_task(worker_id)
    if not task:
        return None

    task_type = task["task_type"]
    handler = _handlers.get(task_type)

    if not handler:
        fail_task(task["id"], f"No handler registered for task type: {task_type}")
        return {"task": task, "error": f"No handler for {task_type}"}

    try:
        result = handler(task["payload"])
        complete_task(task["id"])
        return {"task": task, "result": result}
    except Exception as e:
        fail_task(task["id"], str(e))
        return {"task": task, "error": str(e)}


def get_queue_stats(org_id: str = None) -> dict:
    where = []
    params = []
    if org_id:
        where.append("org_id = ?")
        params.append(org_id)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    stats = pg_query(
        f"""SELECT status, COUNT(*) as count FROM scheduler_tasks
            {where_clause} GROUP BY status""",
        params
    )
    by_type = pg_query(
        f"""SELECT task_type, COUNT(*) as count, AVG(
                CASE WHEN completed_at IS NOT NULL AND started_at IS NOT NULL
                THEN EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000 END
            ) as avg_ms
            FROM scheduler_tasks {where_clause} GROUP BY task_type""",
        params
    )
    result = {s["status"]: s["count"] for s in stats}
    result["by_type"] = by_type
    return result
