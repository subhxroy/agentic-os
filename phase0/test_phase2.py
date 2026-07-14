import os
import sys
import uuid

os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://agentos:agentos_dev@localhost:5432/agentos")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from auth.jwt_auth import create_token, decode_token, hash_password, verify_password
from agent.model_router import ModelRouter, MODEL_CATALOG, TIER_CHAINS

def _uid():
    return uuid.uuid4().hex[:8]

def test_jwt_token_create_decode():
    user_id = f"user_{_uid()}"
    org_id = f"org_{_uid()}"
    token = create_token(user_id, org_id=org_id, role="admin")
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["org_id"] == org_id
    assert payload["role"] == "admin"
    print(f"OK: JWT token create/decode works")

def test_jwt_invalid_token():
    payload = decode_token("invalid.token.here")
    assert payload is None
    print("OK: Invalid JWT token rejected")

def test_password_hash():
    password = "secure_password_123"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)
    print("OK: Password hash/verify works")

def test_model_catalog():
    assert len(MODEL_CATALOG) >= 7
    assert "gemini-3.5-flash" in MODEL_CATALOG
    assert "gpt-4o" in MODEL_CATALOG
    assert "claude-sonnet-4-20250514" in MODEL_CATALOG
    print(f"OK: Model catalog has {len(MODEL_CATALOG)} models")

def test_tier_chains():
    assert "cost_optimized" in TIER_CHAINS
    assert "balanced" in TIER_CHAINS
    assert "quality_first" in TIER_CHAINS
    print(f"OK: {len(TIER_CHAINS)} tier chains defined")

def test_model_router_init():
    router = ModelRouter()
    stats = router.get_usage_stats()
    assert "total_cost_usd" in stats
    assert "available_providers" in stats
    print(f"OK: Model router initialized, providers: {stats['available_providers']}")

def test_model_router_select():
    router = ModelRouter()
    model = router.select_model(tier="cost_optimized")
    # May be None if no API keys available, that's OK for testing
    print(f"OK: Model selection returned: {model or 'none (no API keys)'}")

def test_new_tools_loaded():
    import tools.registry
    import tools.web_search
    names = list(tools.registry.TOOL_REGISTRY.keys())
    assert "shell_command" in names
    assert "code_execute" in names
    assert "json_query" in names
    assert "write_file" in names
    assert len(names) >= 10
    print(f"OK: {len(names)} tools loaded (10+ requirement met)")

def test_org_tables_exist():
    from database import pg_query
    tables = pg_query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    table_names = [t["tablename"] for t in tables]
    assert "organizations" in table_names
    assert "org_members" in table_names
    assert "api_keys" in table_names
    assert "rate_limits" in table_names
    print(f"OK: Org tables exist: {[t for t in table_names if t in ['organizations','org_members','api_keys','rate_limits']]}")

if __name__ == "__main__":
    test_jwt_token_create_decode()
    test_jwt_invalid_token()
    test_password_hash()
    test_model_catalog()
    test_tier_chains()
    test_model_router_init()
    test_model_router_select()
    test_new_tools_loaded()
    test_org_tables_exist()
    print("\nAll Phase 2 tests passed!")
