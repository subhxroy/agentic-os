# AgentOS

Open-source AI assistant platform — from prototype to production desktop app.

## Architecture

```
agentos/
├── phase0/          # Python backend (Flask + SocketIO + SQLite)
├── electron/        # Desktop shell (Electron)
├── sdk/             # Python + TypeScript SDKs
├── handbook/        # 19-volume design documentation
└── migrations/      # SQL migrations (legacy, SQLite built-in)
```

## Quick Start

### Desktop App (Recommended)

```bash
# Windows
start-desktop.bat

# macOS / Linux
cd phase0 && pip install -r ../electron/requirements.txt
cd ../electron && npm install && npm start
```

### Docker (Legacy)

```bash
docker-compose up --build
```

Open http://localhost:8000

## Features

| Feature | Status |
|---------|--------|
| Voice Pipeline (wake word → STT → TTS) | ✅ Local, offline |
| SQLite + DiskCache (no Docker required) | ✅ |
| Electron Desktop App (tray, global hotkey) | ✅ |
| Local Embeddings (sentence-transformers) | ✅ |
| Model Router (Gemini / OpenAI / Anthropic) | ✅ |
| JWT Auth + Multi-tenancy + RBAC | ✅ |
| Knowledge Graph + Long-term Memory | ✅ |
| Agent Scheduler + Observability | ✅ |
| Marketplace + Plugin SDK | ✅ |
| 15 Desktop-Native Tools | ✅ |
| 49 Database Tables | ✅ |
| 66 Tests (7 suites) | ✅ |
| Python + TypeScript SDKs | ✅ |

## Desktop Tools

| Tool | Description |
|------|-------------|
| `take_screenshot` | Full screen or region capture |
| `clipboard_read/write` | System clipboard access |
| `volume_set/get` | System volume control |
| `send_notification` | Desktop notifications |
| `ocr_extract` | Image text extraction |
| `browser_navigate` | Headless browser automation |
| `browser_click` | Click elements by CSS selector |
| `file_read/write/list` | File system operations |
| `schedule_task/cancel_task` | Task scheduling |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+Shift+Space` | Show/focus window (global) |
| `Space` | Toggle voice listening |
| `T` | Toggle TTS |
| `L` | Toggle conversation log |
| `Esc` | Hide window |

## Requirements

- Python 3.10+
- Node.js 18+ (for Electron)
- Windows 10+ / macOS 11+ / Ubuntu 20.04+

### Optional (full voice support)

```bash
pip install openwakeword faster-whisper piper-tts pyaudio
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google Gemini API key (only paid dependency) |
| `AGENTOS_EMBED_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `AGENTOS_WHISPER_MODEL` | `base` | Faster-whisper model |
| `AGENTOS_PIPER_MODEL` | `en_US-lessac-medium` | Piper TTS voice |
| `PORT` | `8000` | Backend port |

## Data

User data stored in OS-appropriate location:

| OS | Path |
|----|------|
| Windows | `%APPDATA%/AgentOS/` |
| macOS | `~/Library/Application Support/AgentOS/` |
| Linux | `~/.config/AgentOS/` |

## SDK

### Python

```python
from agentos import AgentOS

client = AgentOS("http://localhost:8000", api_key="your-key")
response = client.chat("Hello, what can you do?")
```

### TypeScript

```typescript
import { AgentOS } from 'agentos';

const client = new AgentOS('http://localhost:8000', 'your-key');
const response = await client.chat('Hello, what can you do?');
```

## Project Structure

```
phase0/
├── server.py              # Flask + SocketIO app
├── database.py            # SQLite + diskcache
├── config.py              # Environment config
├── migrate.py             # SQLite migrations
├── agent/
│   ├── loop.py            # Agent reasoning loop
│   ├── model_router.py    # Multi-provider LLM router
│   ├── planner.py         # Task planning engine
│   └── prompt_builder.py  # System prompt construction
├── auth/
│   └── jwt_auth.py        # JWT authentication
├── memory/
│   └── store.py           # Working + long-term memory
├── knowledge/
│   └── ingest.py          # Document ingestion + RAG
├── tools/
│   ├── registry.py        # Tool registration + permissions
│   ├── expanded.py        # 15 desktop-native tools
│   └── web_search.py      # Web search tool
├── embeddings/
│   └── local.py           # sentence-transformers
├── voice/
│   └── pipeline.py        # Voice pipeline (wake → STT → TTS)
├── brain/
│   └── notes.py           # Notes + backlinks
├── scale/
│   ├── scheduler.py       # Task scheduler
│   ├── observability.py   # Traces, metrics, logs
│   ├── security.py        # Threat detection
│   └── knowledge_graph.py # Entity graph + traversal
├── marketplace/
│   └── packages.py        # Package registry
├── developer/
│   ├── apps.py            # Developer apps
│   └── plugins.py         # Plugin SDK
├── enterprise/
│   └── compliance.py      # GDPR + compliance
└── collaboration/
    └── team.py            # Team features

electron/
├── main.js                # Electron main process
├── preload.js             # Context bridge
├── package.json           # Build config
├── requirements.txt       # Python dependencies
└── renderer/
    └── index.html         # Desktop UI
```

## License

MIT
