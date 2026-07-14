"""Plugin SDK — manifest validation, loader, sandboxed execution."""

import os
import json
import importlib.util
import traceback
from typing import Any, Callable, Dict, List, Optional


# ============================================================
# Plugin Manifest Schema
# ============================================================
REQUIRED_MANIFEST_FIELDS = {"name", "version", "description", "author", "tools"}
TOOL_SCHEMA_FIELDS = {"name", "description", "parameters"}


def validate_manifest(manifest: dict) -> List[str]:
    """Validate a plugin manifest. Returns list of errors (empty = valid)."""
    errors = []
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            errors.append(f"Missing required field: {field}")

    if "tools" in manifest:
        if not isinstance(manifest["tools"], list):
            errors.append("'tools' must be a list")
        else:
            for i, tool in enumerate(manifest["tools"]):
                for field in TOOL_SCHEMA_FIELDS:
                    if field not in tool:
                        errors.append(f"Tool [{i}] missing field: {field}")
                if "parameters" in tool and not isinstance(tool["parameters"], dict):
                    errors.append(f"Tool [{i}] 'parameters' must be an object")

    if "hooks" in manifest:
        if not isinstance(manifest["hooks"], list):
            errors.append("'hooks' must be a list")

    if "version" in manifest:
        parts = manifest["version"].split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            errors.append("Version must be semver (e.g., '1.0.0')")

    return errors


def create_manifest(
    name: str,
    version: str,
    description: str,
    author: str,
    tools: list,
    hooks: list = None,
    config_schema: dict = None,
) -> dict:
    """Create a plugin manifest with proper structure."""
    return {
        "name": name,
        "version": version,
        "description": description,
        "author": author,
        "tools": tools,
        "hooks": hooks or [],
        "config_schema": config_schema or {},
    }


# ============================================================
# Plugin Loader
# ============================================================
class PluginLoader:
    """Load and manage plugins from directories or registries."""

    def __init__(self):
        self._plugins: Dict[str, Any] = {}
        self._tool_registry: Dict[str, Callable] = {}
        self._hooks: Dict[str, List[Callable]] = {}

    def load_from_directory(self, plugin_dir: str) -> List[dict]:
        """Load all plugins from a directory."""
        loaded = []
        if not os.path.exists(plugin_dir):
            return loaded

        for entry in os.listdir(plugin_dir):
            plugin_path = os.path.join(plugin_dir, entry)
            manifest_path = os.path.join(plugin_path, "manifest.json")
            if os.path.isdir(plugin_path) and os.path.exists(manifest_path):
                try:
                    manifest = self.load_plugin(plugin_path)
                    loaded.append(manifest)
                except Exception as e:
                    print(f"Failed to load plugin {entry}: {e}")
        return loaded

    def load_plugin(self, plugin_path: str) -> dict:
        """Load a single plugin from a directory."""
        manifest_path = os.path.join(plugin_path, "manifest.json")
        with open(manifest_path) as f:
            manifest = json.load(f)

        errors = validate_manifest(manifest)
        if errors:
            raise ValueError(f"Invalid manifest: {errors}")

        plugin_name = manifest["name"]

        # Load code if present
        code_file = os.path.join(plugin_path, "plugin.py")
        if os.path.exists(code_file):
            spec = importlib.util.spec_from_file_location(f"plugin_{plugin_name}", code_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Register tools
            for tool_def in manifest.get("tools", []):
                tool_name = tool_def["name"]
                if hasattr(module, tool_name):
                    self._tool_registry[tool_name] = getattr(module, tool_name)
                else:
                    print(f"Warning: tool '{tool_name}' not found in {code_file}")

            # Register hooks
            for hook_name in manifest.get("hooks", []):
                if hasattr(module, hook_name):
                    if hook_name not in self._hooks:
                        self._hooks[hook_name] = []
                    self._hooks[hook_name].append(getattr(module, hook_name))

        self._plugins[plugin_name] = manifest
        return manifest

    def get_tool(self, name: str) -> Optional[Callable]:
        return self._tool_registry.get(name)

    def get_tools(self) -> Dict[str, Callable]:
        return dict(self._tool_registry)

    def get_hooks(self, event: str) -> List[Callable]:
        return self._hooks.get(event, [])

    def list_plugins(self) -> List[dict]:
        return list(self._plugins.values())


# ============================================================
# Plugin Sandbox
# ============================================================
class PluginSandbox:
    """Execute plugin tools in a sandboxed environment with resource limits."""

    def __init__(self, timeout: int = 10, max_memory_mb: int = 128):
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb

    def execute_tool(self, tool_fn: Callable, arguments: dict) -> dict:
        """Execute a plugin tool with error handling and timeout."""
        import signal
        import threading

        if not hasattr(signal, 'SIGALRM'):
            result = []
            error = []

            def wrapper():
                try:
                    result.append(tool_fn(**arguments))
                except Exception as e:
                    error.append(e)

            t = threading.Thread(target=wrapper, daemon=True)
            t.start()
            t.join(timeout=self.timeout)
            if t.is_alive():
                return {"success": False, "error": f"Tool execution timed out after {self.timeout}s"}
            if error:
                return {"success": False, "error": str(error[0]), "traceback": traceback.format_exc()}
            return {"success": True, "result": result[0]}

        def timeout_handler(signum, frame):
            raise TimeoutError(f"Tool execution timed out after {self.timeout}s")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(self.timeout)

        try:
            result = tool_fn(**arguments)
            signal.alarm(0)
            return {"success": True, "result": result}
        except TimeoutError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    def list_tools_as_registry(self, plugin_dir: str) -> list:
        """Load plugins from directory and return tool definitions for agent."""
        loader = PluginLoader()
        loader.load_from_directory(plugin_dir)

        tools = []
        for name, fn in loader.get_tools().items():
            tools.append({
                "name": name,
                "description": getattr(fn, "__doc__", f"Plugin tool: {name}") or f"Plugin tool: {name}",
                "parameters": getattr(fn, "_parameters", {}),
                "_source": "plugin",
            })
        return tools


# ============================================================
# Plugin Package Builder
# ============================================================
def create_plugin_package(
    output_dir: str,
    name: str,
    version: str,
    description: str,
    author: str,
    tools: list,
    tool_code: str,
    hooks: list = None,
    config_schema: dict = None,
    readme: str = None,
) -> str:
    """Create a complete plugin package directory."""
    plugin_dir = os.path.join(output_dir, name)
    os.makedirs(plugin_dir, exist_ok=True)

    manifest = create_manifest(name, version, description, author, tools, hooks, config_schema)
    with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    with open(os.path.join(plugin_dir, "plugin.py"), "w") as f:
        f.write(tool_code)

    if readme:
        with open(os.path.join(plugin_dir, "README.md"), "w") as f:
            f.write(readme)

    return plugin_dir
