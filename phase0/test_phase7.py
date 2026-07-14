import os
import sys
import uuid
import json

os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://agentos:agentos_dev@localhost:5432/agentos")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from database import pg_query
from auth.jwt_auth import create_token, hash_password, create_org
from memory.store import create_user


def _uid():
    return uuid.uuid4().hex[:8]


def _setup_org():
    email = f"scale_{_uid()}@test.com"
    user = create_user(email, hash_password("pass"), "Scale Admin")
    org = create_org(f"Scale Org {_uid()}", user["id"])
    return user, org


def test_phase7_tables_exist():
    tables = pg_query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    names = [t["tablename"] for t in tables]
    required = ["kg_entities", "kg_relationships", "kg_snapshots",
                "scheduler_tasks", "scheduler_workers",
                "observability_traces", "observability_metrics", "observability_logs",
                "anomaly_rules", "anomaly_events",
                "threat_rules", "threat_events",
                "region_configs", "region_routing"]
    for t in required:
        assert t in names, f"Missing table: {t}"
    print(f"OK: All {len(required)} Phase 7 tables exist")


def test_knowledge_graph():
    from scale.knowledge_graph import (
        create_entity, get_entity, search_entities, update_entity, delete_entity,
        create_relationship, get_entity_neighbors, traverse_bfs, find_path,
        get_graph_stats, create_snapshot
    )
    user, org = _setup_org()

    # Create entities
    e1 = create_entity(org["id"], "concept", "Machine Learning",
                       description="AI subfield", properties={"domain": "AI"})
    e2 = create_entity(org["id"], "concept", "Deep Learning",
                       description="ML subset", properties={"domain": "AI"})
    e3 = create_entity(org["id"], "concept", "Neural Network",
                       description="Computing system")
    assert e1 is not None
    assert e1["entity_type"] == "concept"

    # Search
    results = search_entities(org["id"], query="Learning")
    assert len(results) >= 2

    # Update
    updated = update_entity(e1["id"], description="AI and ML subfield")
    assert updated["description"] == "AI and ML subfield"

    # Relationships
    r1 = create_relationship(e1["id"], e2["id"], "contains", weight=0.9)
    r2 = create_relationship(e2["id"], e3["id"], "uses", weight=0.8)
    assert r1 is not None

    # Neighbors
    neighbors = get_entity_neighbors(e1["id"], direction="outgoing")
    assert len(neighbors["outgoing"]) >= 1

    # BFS traversal
    graph = traverse_bfs(e1["id"], max_depth=2)
    assert len(graph["nodes"]) >= 2
    assert len(graph["edges"]) >= 1

    # Path finding
    path = find_path(e1["id"], e3["id"])
    assert len(path) >= 2

    # Stats
    stats = get_graph_stats(org["id"])
    assert stats["entity_count"] >= 3
    assert stats["relationship_count"] >= 2

    # Snapshot
    snap = create_snapshot(org["id"])
    assert snap["entity_count"] >= 3

    # Delete
    delete_entity(e3["id"])
    assert get_entity(e3["id"]) is None
    print("OK: Knowledge graph (entities, relationships, traversal, stats) works")


def test_scheduler():
    from scale.scheduler import (
        create_task, get_task, list_tasks, claim_task, complete_task,
        fail_task, cancel_task, register_worker, heartbeat,
        register_handler, process_next_task, get_queue_stats
    )
    user, org = _setup_org()

    # Create tasks
    t1 = create_task(org["id"], "email", payload={"to": "test@test.com"}, priority=8)
    t2 = create_task(org["id"], "report", payload={"type": "daily"}, priority=3)
    assert t1["status"] == "pending"
    assert t1["priority"] == 8

    # List
    tasks = list_tasks(org_id=org["id"])
    assert len(tasks) >= 2

    # Cancel
    cancel_task(t2["id"])
    assert get_task(t2["id"])["status"] == "cancelled"

    # Worker
    worker = register_worker("worker-1", org["id"])
    assert worker is not None
    heartbeat("worker-1")

    # Claim + complete
    claimed = claim_task("worker-1")
    assert claimed is not None
    assert claimed["status"] == "running"
    complete_task(claimed["id"])
    assert get_task(claimed["id"])["status"] == "completed"

    # Fail + retry
    t3 = create_task(org["id"], "failable", priority=5)
    claimed3 = claim_task("worker-1", task_type="failable")
    fail_task(claimed3["id"], "Test error")
    assert get_task(claimed3["id"])["status"] == "retry"

    # Handler registration
    register_handler("test_job", lambda payload: {"ok": True})
    t4 = create_task(org["id"], "test_job", payload={"x": 1})
    # Claim specifically the test_job task
    from scale.scheduler import claim_task as _claim
    claimed4 = _claim("worker-1", task_type="test_job")
    assert claimed4 is not None
    complete_task(claimed4["id"])
    assert get_task(claimed4["id"])["status"] == "completed"

    # Stats
    stats = get_queue_stats(org["id"])
    assert "completed" in stats
    print("OK: Scheduler (tasks, workers, claim, retry, handlers) works")


def test_observability():
    from scale.observability import (
        create_trace, finish_trace, add_span, get_trace, get_slow_traces,
        record_metric, get_metrics, get_metric_summary,
        write_log, get_logs, get_error_rate
    )
    user, org = _setup_org()

    # Traces
    trace = create_trace(org["id"], "agent.chat", user_id=user["id"])
    assert trace["trace_id"] is not None
    finish_trace(trace["trace_id"], trace["span_id"], duration_ms=250, status="ok")
    add_span(trace["trace_id"], trace["span_id"], "tool.call", duration_ms=50)
    spans = get_trace(trace["trace_id"])
    assert len(spans) >= 2

    slow = get_slow_traces(org["id"], min_duration_ms=100)
    assert len(slow) >= 1

    # Metrics
    record_metric(org["id"], "latency_ms", 150.0, metric_type="histogram")
    record_metric(org["id"], "latency_ms", 200.0, metric_type="histogram")
    metrics = get_metrics(org["id"], metric_name="latency_ms")
    assert len(metrics) >= 2

    summary = get_metric_summary(org["id"], "latency_ms")
    assert summary["avg"] > 0
    assert summary["count"] >= 2

    # Logs
    write_log(org["id"], "Test log message", level="info")
    write_log(org["id"], "Test error", level="error")
    logs = get_logs(org["id"])
    assert len(logs) >= 2

    error_rate = get_error_rate(org["id"])
    assert error_rate["errors"] >= 1
    assert error_rate["rate"] > 0
    print("OK: Observability (traces, metrics, logs, error rate) works")


def test_anomaly_detection():
    from scale.observability import (
        create_anomaly_rule, check_anomalies, list_anomaly_events, record_metric
    )
    user, org = _setup_org()

    # Create rule: alert if latency_ms > 100
    rule = create_anomaly_rule(org["id"], "High Latency", "latency_ms",
                               "gt", 100, window_minutes=5, severity="warning")
    assert rule is not None

    # Record metrics that exceed threshold
    for i in range(5):
        record_metric(org["id"], "latency_ms", 150.0 + i * 10)

    # Check anomalies
    triggered = check_anomalies(org["id"])
    assert len(triggered) >= 1
    assert triggered[0]["severity"] == "warning"

    events = list_anomaly_events(org["id"])
    assert len(events) >= 1
    print("OK: Anomaly detection (rules, check, events) works")


def test_threat_detection():
    from scale.security import (
        create_threat_rule, get_threat_rules, record_threat_event,
        get_threat_events, get_threat_summary
    )
    user, org = _setup_org()

    rule = create_threat_rule(org["id"], "Brute Force", "rate_limit",
                              config={"max_attempts": 5}, severity="critical")
    assert rule is not None

    rules = get_threat_rules(org["id"])
    assert len(rules) >= 1

    event = record_threat_event(org["id"], "login_failed",
                                source_ip="10.0.0.1", severity="critical")
    assert event is not None

    events = get_threat_events(org["id"])
    assert len(events) >= 1

    summary = get_threat_summary(org["id"])
    assert "by_severity" in summary
    print("OK: Threat detection (rules, events, summary) works")


def test_multi_region():
    from scale.security import (
        create_region, get_region, list_regions, update_region,
        assign_org_region, get_org_regions, get_best_region
    )
    user, org = _setup_org()

    r1 = create_region(f"us-east-{_uid()}", "https://us-east.agentos.ai", weight=100)
    r2 = create_region(f"eu-west-{_uid()}", "https://eu-west.agentos.ai", weight=80)
    assert r1 is not None

    regions = list_regions()
    assert len(regions) >= 2

    updated = update_region(r1["region_name"], latency_ms_avg=50)
    assert updated["latency_ms_avg"] == 50

    assign_org_region(org["id"], r1["region_name"], priority=1)
    assign_org_region(org["id"], r2["region_name"], priority=2)

    org_regions = get_org_regions(org["id"])
    assert len(org_regions) >= 2

    best = get_best_region(org["id"])
    assert best is not None
    assert best["region_name"] == r1["region_name"]
    print("OK: Multi-region (regions, routing, best region) works")


if __name__ == "__main__":
    test_phase7_tables_exist()
    test_knowledge_graph()
    test_scheduler()
    test_observability()
    test_anomaly_detection()
    test_threat_detection()
    test_multi_region()
    print("\nAll Phase 7 tests passed!")
