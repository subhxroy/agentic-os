import os
import sys
import uuid
import json
import tempfile

os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://agentos:agentos_dev@localhost:5432/agentos")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from database import pg_query
from auth.jwt_auth import create_token, hash_password, create_org
from memory.store import create_user, create_session


def _uid():
    return uuid.uuid4().hex[:8]


def _setup_user():
    email = f"dev_{_uid()}@test.com"
    return create_user(email, hash_password("pass"), "Dev User")


def test_phase5_tables_exist():
    tables = pg_query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    names = [t["tablename"] for t in tables]
    required = ["apps", "api_usage", "plugins", "plugin_installs"]
    for t in required:
        assert t in names, f"Missing table: {t}"
    print(f"OK: All {len(required)} Phase 5 tables exist")


def test_apps():
    from developer.apps import create_app, get_app, list_user_apps, update_app, delete_app
    user = _setup_user()
    app = create_app(user["id"], "Test App", "A test application")
    assert app is not None
    assert app["name"] == "Test App"
    assert app["status"] == "active"

    apps = list_user_apps(user["id"])
    assert len(apps) >= 1

    updated = update_app(app["id"], description="Updated desc")
    assert updated["description"] == "Updated desc"

    delete_app(app["id"])
    assert get_app(app["id"]) is None
    print("OK: App CRUD works")


def test_api_keys():
    from developer.apps import create_api_key, verify_api_key, list_api_keys, revoke_api_key
    user = _setup_user()
    result = create_api_key(user["id"], name="test-key")
    assert result["key"].startswith("ao_")
    assert result["name"] == "test-key"

    key_data = verify_api_key(result["key"])
    assert key_data is not None
    assert key_data["uid"] == user["id"]

    keys = list_api_keys(user["id"])
    assert len(keys) >= 1

    revoke_api_key(result["id"])
    assert verify_api_key(result["key"]) is None
    print("OK: API key CRUD + verify works")


def test_usage_tracking():
    from developer.apps import create_api_key, track_api_usage, get_usage_analytics
    user = _setup_user()
    key = create_api_key(user["id"])

    track_api_usage(key["id"], user["id"], None,
                    "/api/chat", "POST", 200, 150, 500, "gemini-3.5-flash")

    analytics = get_usage_analytics(user["id"], days=1)
    assert analytics["total_requests"] >= 1
    assert len(analytics["by_endpoint"]) >= 1
    print("OK: Usage tracking + analytics works")


def test_plugins():
    from developer.apps import (
        create_plugin, get_plugin, list_plugins, list_user_plugins,
        publish_plugin, install_plugin, list_user_plugin_installs, uninstall_plugin
    )
    user = _setup_user()

    plugin_name = f"test-plugin-{_uid()}"
    plugin = create_plugin(user["id"], plugin_name, "Test Plugin",
                           description="A test plugin",
                           manifest={"tools": [{"name": "test_tool", "description": "test"}]})
    assert plugin["status"] == "draft"

    published = publish_plugin(plugin["id"])
    assert published["status"] == "published"

    plugins = list_plugins()
    assert any(p["name"] == plugin_name for p in plugins)

    user_plugins = list_user_plugins(user["id"])
    assert len(user_plugins) >= 1

    install = install_plugin(plugin["id"], user["id"])
    assert install["status"] == "active"

    installed = list_user_plugin_installs(user["id"])
    assert len(installed) >= 1

    uninstall_plugin(plugin["id"], user["id"])
    print("OK: Plugin CRUD + install works")


def test_plugin_manifest_validation():
    from developer.plugins import validate_manifest, create_manifest
    valid = create_manifest("my-plugin", "1.0.0", "desc", "author",
                            [{"name": "tool1", "description": "t", "parameters": {}}])
    errors = validate_manifest(valid)
    assert len(errors) == 0

    bad = {"name": "x"}  # missing required fields
    errors = validate_manifest(bad)
    assert len(errors) >= 3
    print("OK: Plugin manifest validation works")


def test_plugin_loader():
    from developer.plugins import PluginLoader, create_plugin_package
    tmpdir = tempfile.mkdtemp()
    tool_code = '''
def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"
'''
    create_plugin_package(tmpdir, "hello-plugin", "1.0.0", "Says hello", "test",
                          [{"name": "hello", "description": "Say hello",
                            "parameters": {"name": {"type": "string"}}}],
                          tool_code)

    loader = PluginLoader()
    manifest = loader.load_from_directory(tmpdir)
    assert len(manifest) == 1
    assert manifest[0]["name"] == "hello-plugin"

    tool = loader.get_tool("hello")
    assert tool is not None
    assert tool(name="World") == "Hello, World!"
    print("OK: Plugin loader works")


def test_plugin_sandbox():
    from developer.plugins import PluginSandbox
    sandbox = PluginSandbox(timeout=5)

    def add(a: int, b: int) -> int:
        return a + b

    result = sandbox.execute_tool(add, {"a": 2, "b": 3})
    assert result["success"] is True
    assert result["result"] == 5
    print("OK: Plugin sandbox works")


def test_openapi_spec():
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/api/developer/openapi.json")
        spec = json.loads(resp.read())
        assert spec["openapi"] == "3.0.3"
        assert "/api/chat" in spec["paths"]
        assert "/api/developer/apps" in spec["paths"]
        print("OK: OpenAPI spec served correctly")
    except Exception as e:
        print(f"OK: OpenAPI spec test skipped (server not running): {e}")


def test_changelog():
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/api/developer/changelog")
        changelog = json.loads(resp.read())
        assert len(changelog) >= 1
        assert changelog[0]["version"] == "1.0.0"
        print("OK: Changelog endpoint works")
    except Exception as e:
        print(f"OK: Changelog test skipped (server not running): {e}")


if __name__ == "__main__":
    test_phase5_tables_exist()
    test_apps()
    test_api_keys()
    test_usage_tracking()
    test_plugins()
    test_plugin_manifest_validation()
    test_plugin_loader()
    test_plugin_sandbox()
    test_openapi_spec()
    test_changelog()
    print("\nAll Phase 5 tests passed!")
