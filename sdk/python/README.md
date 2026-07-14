# AgentOS Python SDK

Build and integrate intelligent agents with AgentOS.

## Install

```bash
pip install agentos
# or from source:
pip install -e ./sdk/python
```

## Quickstart

```python
from agentos import AgentOS

client = AgentOS(base_url="http://localhost:8000")

# Register and get a token
client.register("dev@example.com", "password123")

# Chat with the agent
response = client.chat("What is 2 + 2?")
print(response.response)  # "2 + 2 = 4"

# Upload knowledge
doc = client.upload_document("./my-doc.txt")

# Search knowledge
results = client.search_knowledge("What is the policy?")

# Developer API
app = client.create_app("My App")
key = client.create_api_key("my-key")
usage = client.get_usage(days=7)

# Plugins
plugin = client.create_plugin("my-plugin", "My Plugin")
client.install_plugin(plugin.id)
```

## Authentication

```python
# JWT token (from register/login)
client = AgentOS(token="your-jwt-token")

# Or authenticate via API key
client = AgentOS(base_url="http://localhost:8000")
client.login("user@example.com", "password")
```

## Error Handling

```python
from agentos.client import AgentOSClientError

try:
    response = client.chat("Hello")
except AgentOSClientError as e:
    print(f"Error {e.status}: {e.message}")
```

## API Reference

### AgentOS(base_url, token)

| Method | Description |
|--------|-------------|
| `register(email, password, name)` | Register new user |
| `login(email, password)` | Login and get JWT |
| `chat(message, session_id)` | Send message to agent |
| `list_sessions()` | List all sessions |
| `list_memories()` | List memories |
| `create_memory(content)` | Create a memory |
| `upload_document(filepath)` | Upload knowledge document |
| `search_knowledge(query)` | Search knowledge base |
| `create_app(name)` | Create a developer app |
| `list_apps()` | List your apps |
| `create_api_key(name)` | Create API key |
| `list_api_keys()` | List API keys |
| `get_usage(days)` | Get usage analytics |
| `list_plugins()` | List published plugins |
| `create_plugin(name, display_name)` | Create a plugin |
| `install_plugin(plugin_id)` | Install a plugin |
| `status()` | Check API status |
| `changelog()` | Get changelog |

Full OpenAPI spec: `GET /api/developer/openapi.json`
