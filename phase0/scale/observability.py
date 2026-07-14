"""Observability — traces, metrics, logs, anomaly detection."""

import uuid
import json
import time
from datetime import datetime, timedelta
from typing import Optional
from database import pg_query, pg_execute


# ============================================================
# Traces
# ============================================================
def create_trace(org_id: str, operation: str, user_id: str = None,
                 service: str = "agentos", metadata: dict = None) -> dict:
    trace_id = str(uuid.uuid4()).replace("-", "")[:16]
    span_id = str(uuid.uuid4()).replace("-", "")[:8]
    pg_execute(
        """INSERT INTO observability_traces
           (id, trace_id, span_id, org_id, user_id, operation, service, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (str(uuid.uuid4()), trace_id, span_id, org_id, user_id,
         operation, service, json.dumps(metadata or {}))
    )
    return {"trace_id": trace_id, "span_id": span_id}


def finish_trace(trace_id: str, span_id: str, duration_ms: int,
                 status: str = "ok", metadata: dict = None) -> dict:
    pg_execute(
        """UPDATE observability_traces SET duration_ms = %s, status = %s,
           metadata = metadata || %s::jsonb WHERE trace_id = %s AND span_id = %s""",
        (duration_ms, status, json.dumps(metadata or {}), trace_id, span_id)
    )
    return {"trace_id": trace_id, "span_id": span_id, "duration_ms": duration_ms, "status": status}


def add_span(trace_id: str, parent_span_id: str, operation: str,
             org_id: str = None, duration_ms: int = None,
             status: str = "ok", metadata: dict = None) -> dict:
    span_id = str(uuid.uuid4()).replace("-", "")[:8]
    pg_execute(
        """INSERT INTO observability_traces
           (id, trace_id, span_id, parent_span_id, org_id, operation, duration_ms, status, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (str(uuid.uuid4()), trace_id, span_id, parent_span_id, org_id,
         operation, duration_ms, status, json.dumps(metadata or {}))
    )
    return {"trace_id": trace_id, "span_id": span_id}


def get_trace(trace_id: str) -> list:
    return pg_query(
        """SELECT * FROM observability_traces WHERE trace_id = %s
           ORDER BY created_at ASC""",
        (trace_id,)
    )


def get_slow_traces(org_id: str = None, min_duration_ms: int = 1000,
                    limit: int = 20) -> list:
    where = ["duration_ms >= %s"]
    params = [min_duration_ms]
    if org_id:
        where.append("org_id = %s")
        params.append(org_id)
    params.append(limit)
    return pg_query(
        f"""SELECT * FROM observability_traces WHERE {' AND '.join(where)}
            ORDER BY duration_ms DESC LIMIT %s""",
        params
    )


# ============================================================
# Metrics
# ============================================================
def record_metric(org_id: str, metric_name: str, value: float,
                  metric_type: str = "gauge", labels: dict = None) -> dict:
    metric_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO observability_metrics (id, org_id, metric_name, metric_value, metric_type, labels)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
        (metric_id, org_id, metric_name, value, metric_type, json.dumps(labels or {}))
    )
    return {"id": metric_id, "metric_name": metric_name, "value": value}


def get_metrics(org_id: str, metric_name: str = None,
                since_minutes: int = 60, limit: int = 100) -> list:
    cutoff = (datetime.utcnow() - timedelta(minutes=since_minutes)).isoformat()
    where = ["created_at > ?"]
    params = [cutoff]
    if org_id:
        where.append("org_id = %s")
        params.append(org_id)
    if metric_name:
        where.append("metric_name = %s")
        params.append(metric_name)
    params.append(limit)
    return pg_query(
        f"""SELECT * FROM observability_metrics WHERE {' AND '.join(where)}
            ORDER BY created_at DESC LIMIT %s""",
        params
    )


def get_metric_summary(org_id: str, metric_name: str, since_minutes: int = 60) -> dict:
    cutoff = (datetime.utcnow() - timedelta(minutes=since_minutes)).isoformat()
    rows = pg_query(
        """SELECT AVG(metric_value) as avg, MIN(metric_value) as min,
           MAX(metric_value) as max, COUNT(*) as count, SUM(metric_value) as total
           FROM observability_metrics
           WHERE org_id = ? AND metric_name = ? AND created_at > ?""",
        (org_id, metric_name, cutoff)
    )
    r = rows[0] if rows else {}
    return {
        "avg": float(r["avg"]) if r.get("avg") else 0,
        "min": float(r["min"]) if r.get("min") else 0,
        "max": float(r["max"]) if r.get("max") else 0,
        "count": r.get("count", 0),
        "total": float(r["total"]) if r.get("total") else 0,
    }


# ============================================================
# Logs
# ============================================================
def write_log(org_id: str, message: str, level: str = "info",
              trace_id: str = None, source: str = None,
              metadata: dict = None) -> dict:
    log_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO observability_logs (id, org_id, trace_id, level, message, source, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (log_id, org_id, trace_id, level, message, source, json.dumps(metadata or {}))
    )
    return {"id": log_id}


def get_logs(org_id: str = None, level: str = None, trace_id: str = None,
             since_minutes: int = 60, limit: int = 100) -> list:
    cutoff = (datetime.utcnow() - timedelta(minutes=since_minutes)).isoformat()
    where = ["created_at > ?"]
    params = [cutoff]
    if org_id:
        where.append("org_id = %s")
        params.append(org_id)
    if level:
        where.append("level = %s")
        params.append(level)
    if trace_id:
        where.append("trace_id = %s")
        params.append(trace_id)
    params.append(limit)
    return pg_query(
        f"""SELECT * FROM observability_logs WHERE {' AND '.join(where)}
            ORDER BY created_at DESC LIMIT %s""",
        params
    )


def get_error_rate(org_id: str, since_minutes: int = 60) -> dict:
    cutoff = (datetime.utcnow() - timedelta(minutes=since_minutes)).isoformat()
    total = pg_query(
        "SELECT COUNT(*) as c FROM observability_logs WHERE org_id = ? AND created_at > ?",
        (org_id, cutoff)
    )
    errors = pg_query(
        """SELECT COUNT(*) as c FROM observability_logs
           WHERE org_id = ? AND level IN ('error', 'fatal') AND created_at > ?""",
        (org_id, cutoff)
    )
    t = total[0]["c"] if total else 0
    e = errors[0]["c"] if errors else 0
    return {"total": t, "errors": e, "rate": e / t if t > 0 else 0}


# ============================================================
# Anomaly Detection
# ============================================================
def create_anomaly_rule(org_id: str, name: str, metric_name: str,
                        condition: str, threshold: float,
                        window_minutes: int = 5, severity: str = "warning") -> dict:
    rule_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO anomaly_rules (id, org_id, name, metric_name, condition, threshold, window_minutes, severity)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (rule_id, org_id, name, metric_name, condition, threshold, window_minutes, severity)
    )
    return {"id": rule_id, "name": name, "metric_name": metric_name}


def check_anomalies(org_id: str) -> list:
    """Check all enabled anomaly rules for an org."""
    rules = pg_query(
        "SELECT * FROM anomaly_rules WHERE org_id = %s AND enabled = TRUE",
        (org_id,)
    )
    triggered = []
    for rule in rules:
        cutoff = datetime.utcnow() - timedelta(minutes=rule["window_minutes"])
        summary = get_metric_summary(org_id, rule["metric_name"],
                                     since_minutes=rule["window_minutes"])
        value = summary["avg"]
        threshold = rule["threshold"]
        condition = rule["condition"]

        hit = False
        if condition == "gt" and value > threshold: hit = True
        elif condition == "lt" and value < threshold: hit = True
        elif condition == "gte" and value >= threshold: hit = True
        elif condition == "lte" and value <= threshold: hit = True
        elif condition == "eq" and abs(value - threshold) < 0.001: hit = True

        if hit:
            event_id = str(uuid.uuid4())
            pg_execute(
                """INSERT INTO anomaly_events (id, rule_id, org_id, metric_value, threshold, severity, message)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (event_id, rule["id"], org_id, value, threshold, rule["severity"],
                 f"Anomaly: {rule['name']} — {rule['metric_name']}={value:.2f} {condition} {threshold}")
            )
            triggered.append({
                "rule": rule["name"],
                "metric": rule["metric_name"],
                "value": value,
                "threshold": threshold,
                "condition": condition,
                "severity": rule["severity"],
            })

    return triggered


def list_anomaly_events(org_id: str, resolved: bool = None, limit: int = 50) -> list:
    where = ["ae.org_id = ?"]
    params = [org_id]
    if resolved is not None:
        where.append("ae.resolved = ?")
        params.append(1 if resolved else 0)
    params.append(limit)
    return pg_query(
        f"""SELECT ae.*, ar.name as rule_name FROM anomaly_events ae
            LEFT JOIN anomaly_rules ar ON ae.rule_id = ar.id
            WHERE {' AND '.join(where)} ORDER BY ae.created_at DESC LIMIT %s""",
        params
    )


def resolve_anomaly(event_id: str) -> dict:
    pg_execute(
        "UPDATE anomaly_events SET resolved = 1, resolved_at = datetime('now') WHERE id = ?",
        (event_id,)
    )
    rows = pg_query("SELECT * FROM anomaly_events WHERE id = ?", (event_id,))
    return rows[0] if rows else None
