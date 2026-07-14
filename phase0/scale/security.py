"""Threat detection + multi-region config."""

import uuid
import json
from datetime import datetime, timedelta
from database import pg_query, pg_execute


# ============================================================
# Threat Detection
# ============================================================
def create_threat_rule(org_id: str, name: str, rule_type: str,
                       config: dict = None, severity: str = "warning",
                       description: str = None) -> dict:
    rule_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO threat_rules (id, org_id, name, description, rule_type, config, severity)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)""",
        (rule_id, org_id, name, description, rule_type, json.dumps(config or {}), severity)
    )
    return {"id": rule_id, "name": name, "rule_type": rule_type}


def get_threat_rules(org_id: str) -> list:
    return pg_query(
        "SELECT * FROM threat_rules WHERE org_id = ? AND enabled = 1",
        (org_id,)
    )


def record_threat_event(org_id: str, event_type: str, source_ip: str = None,
                        user_id: str = None, details: dict = None,
                        severity: str = "warning", rule_id: str = None,
                        action_taken: str = None) -> dict:
    event_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO threat_events (id, rule_id, org_id, event_type, source_ip, user_id,
           details, severity, action_taken)
           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)""",
        (event_id, rule_id, org_id, event_type, source_ip, user_id,
         json.dumps(details or {}), severity, action_taken)
    )
    return {"id": event_id, "event_type": event_type, "severity": severity}


def check_rate_limit_threat(org_id: str, source_ip: str,
                            window_minutes: int = 1, max_requests: int = 100) -> dict:
    """Check if an IP exceeds rate limits."""
    cutoff = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()
    count = pg_query(
        """SELECT COUNT(*) as c FROM observability_logs
           WHERE org_id = ? AND json_extract(metadata, '$.source_ip') = ? AND created_at > ?""",
        (org_id, source_ip, cutoff)
    )
    c = count[0]["c"] if count else 0
    if c > max_requests:
        event = record_threat_event(
            org_id, "rate_limit_exceeded", source_ip=source_ip,
            details={"request_count": c, "window_minutes": window_minutes},
            severity="warning", action_taken="blocked"
        )
        return {"blocked": True, "count": c, "event": event}
    return {"blocked": False, "count": c}


def get_threat_events(org_id: str, severity: str = None,
                      since_minutes: int = 60, limit: int = 50) -> list:
    cutoff = (datetime.utcnow() - timedelta(minutes=since_minutes)).isoformat()
    where = ["org_id = ?", "created_at > ?"]
    params = [org_id, cutoff]
    if severity:
        where.append("severity = %s")
        params.append(severity)
    params.append(limit)
    return pg_query(
        f"""SELECT * FROM threat_events WHERE {' AND '.join(where)}
            ORDER BY created_at DESC LIMIT %s""",
        params
    )


def get_threat_summary(org_id: str, since_minutes: int = 60) -> dict:
    cutoff = (datetime.utcnow() - timedelta(minutes=since_minutes)).isoformat()
    by_severity = pg_query(
        """SELECT severity, COUNT(*) as count FROM threat_events
           WHERE org_id = ? AND created_at > ? GROUP BY severity""",
        (org_id, cutoff)
    )
    by_type = pg_query(
        """SELECT event_type, COUNT(*) as count FROM threat_events
           WHERE org_id = ? AND created_at > ? GROUP BY event_type ORDER BY count DESC""",
        (org_id, cutoff)
    )
    return {
        "by_severity": {r["severity"]: r["count"] for r in by_severity},
        "by_type": by_type,
        "period_minutes": since_minutes,
    }


# ============================================================
# Multi-Region Config
# ============================================================
def create_region(region_name: str, endpoint: str, weight: int = 100,
                  features: dict = None) -> dict:
    region_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO region_configs (id, region_name, endpoint, weight, features)
           VALUES (%s, %s, %s, %s, %s::jsonb)""",
        (region_id, region_name, endpoint, weight, json.dumps(features or {}))
    )
    return {"id": region_id, "region_name": region_name, "endpoint": endpoint}


def get_region(region_name: str) -> dict:
    rows = pg_query("SELECT * FROM region_configs WHERE region_name = %s", (region_name,))
    return rows[0] if rows else None


def list_regions() -> list:
    return pg_query("SELECT * FROM region_configs ORDER BY weight DESC")


def update_region(region_name: str, **kwargs) -> dict:
    allowed = {"endpoint", "status", "weight", "features", "latency_ms_avg"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_region(region_name)
    set_parts = []
    values = []
    for k, v in updates.items():
        if k == "features":
            set_parts.append(f"{k} = %s::jsonb")
            values.append(json.dumps(v))
        else:
            set_parts.append(f"{k} = %s")
            values.append(v)
    pg_execute(f"UPDATE region_configs SET {', '.join(set_parts)}, updated_at = NOW() WHERE region_name = %s",
               values + [region_name])
    return get_region(region_name)


def assign_org_region(org_id: str, region_name: str, priority: int = 1) -> dict:
    pg_execute(
        """INSERT INTO region_routing (id, org_id, region_name, priority)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (org_id, region_name) DO UPDATE SET priority = EXCLUDED.priority""",
        (str(uuid.uuid4()), org_id, region_name, priority)
    )
    return {"org_id": org_id, "region_name": region_name, "priority": priority}


def get_org_regions(org_id: str) -> list:
    return pg_query(
        """SELECT rr.*, rc.endpoint, rc.status, rc.latency_ms_avg
           FROM region_routing rr LEFT JOIN region_configs rc ON rr.region_name = rc.region_name
           WHERE rr.org_id = %s ORDER BY rr.priority ASC""",
        (org_id,)
    )


def get_best_region(org_id: str) -> dict:
    """Get the best (lowest latency, active) region for an org."""
    regions = get_org_regions(org_id)
    active = [r for r in regions if r.get("status") == "active"]
    if not active:
        active = regions
    if not active:
        return None
    return min(active, key=lambda r: r.get("latency_ms_avg") or 999999)
