# AgentOS

AgentOS is an open-source, desktop-native AI assistant platform that integrates a local reasoning agent, memory store, offline voice pipeline, and desktop control tools. It is designed to run locally, utilizing SQLite for state persistence and a tray-based Electron interface for user interaction.

---

## Key Features

- **Local-First Architecture**: Powered by a Python backend (Flask + Socket.IO) and SQLite database. Zero cloud dependencies except for the LLM API.
- **Offline Voice Pipeline**: 
  - **Native Mode**: Always-on wake-word detection (`openWakeWord`), speech-to-text (`faster-whisper`), and offline text-to-speech (`piper-tts`) running on your local CPU.
  - **Browser Mode (Dynamic Fallback)**: Automatically falls back to Chromium's Web Speech API with browser-side wake-word detection if native dependencies are missing.
- **Desktop-Native Tools**: 15 built-in tools for desktop control (screenshots, OCR, clipboard read/write, system volume control, and automated browser navigation).
- **RAG & Memory Engine**: Integrated Knowledge Graph, vector database (via `sentence-transformers`), and long-term memory store.
- **Developer & Plugin SDKs**: Simple SDKs to extend the agent's capabilities or build marketplace packages.
- **Enterprise-Ready**: Multi-tenancy, RBAC, JWT authentication, and built-in audit logs across 49 SQLite database tables.

---

## Directory Structure

```
agentos/
├── phase0/          # Python backend (Flask + SocketIO + SQLite)
│   ├── agent/       # Local agent reasoning loop & model router
│   ├── auth/        # JWT & RBAC authentication
│   ├── voice/       # PyAudio + openWakeWord voice pipeline
│   ├── memory/      # Long-term semantic memory store
│   ├── tools/       # Desktop-native tool wrappers
│   └── database.py  # Thread-local SQLite adapter & schema migration
├── electron/        # Desktop shell (Electron + HTML UI)
│   ├── renderer/    # Front-end renderer (Jarvis orb interface)
│   └── main.js      # App startup, Tray, & Hotkey registry
├── sdk/             # Python + TypeScript client SDKs
└── start-desktop.bat # Single-click launcher for Windows
```

---

## Installation & Setup

### Prerequisites

- **Python**: 3.10 or 3.12 (highly recommended)
- **Node.js**: 18+ and `npm`

---

### Step-by-Step Guide

#### 1. Clone the Repository
```bash
git clone https://github.com/your-username/agentic-os.git
cd agentic-os
```

#### 2. Run on Windows (One-Click Launcher)
Double-click `start-desktop.bat` or run:
```powershell
.\start-desktop.bat
```
This launcher will:
- Check and install Python dependencies in `phase0/requirements.txt`.
- Check and install Electron dependencies in `electron/package.json`.
- Automatically initialize the SQLite database schema in `%APPDATA%/agentos/agentos.db`.
- Start the Flask backend on port `8088` and boot the desktop Electron shell.

#### 3. Run on macOS / Linux
Open a terminal and execute the following commands:
```bash
# 1. Install backend requirements
cd phase0
pip install -r ../electron/requirements.txt

# 2. Run migrations and start backend server
python server.py

# 3. In another terminal, start the Electron frontend
cd ../electron
npm install
npm start
```

---

## Configuration

AgentOS is configured using environment variables. Create a `.env` file in `phase0/` to configure keys:

| Variable | Default Value | Description |
|----------|---------------|-------------|
| `GEMINI_API_KEY` | *(Required)* | Google Gemini API Key for agent planning and reasoning. |
| `PORT` | `8088` | Backend server port (changed from 8000 to prevent collisions). |
| `AGENTOS_DATA_DIR` | `%APPDATA%/agentos/` | Directory where SQLite database and file cache are stored. |
| `AGENTOS_EMBED_MODEL` | `all-MiniLM-L6-v2` | Embedding model for semantic search & memory. |
| `AGENTOS_WHISPER_MODEL` | `base` | Model size for faster-whisper STT. |
| `AGENTOS_PIPER_MODEL` | `en_US-lessac-medium` | Offline voice package model for Piper TTS. |

---

## Voice Pipeline & Hybrid Fallback

AgentOS implements a hybrid voice interface that guarantees functionality across all systems:

```
                  +-----------------------------------+
                  |        VOICE Button Clicked       |
                  +-----------------------------------+
                                    |
                                    v
                     +-----------------------------+
                     |   Check Python Voice API    |
                     +-----------------------------+
                       /                         \
            (Available) /                           \ (Unavailable / 503)
                      /                             \
                     v                               v
       +---------------------------+   +---------------------------+
       |   Native Python Pipeline  |   |   Web Speech API Fallback |
       |                           |   |                           |
       |  1. pyaudio captures mic  |   |  1. Chromium captures mic |
       |  2. openWakeWord detects  |   |  2. JS checks transcription|
       |     "Hey Jarvis"          |   |     for "Hey Jarvis"      |
       |  3. whisper transcribes   |   |  3. Browser transcribes   |
       |  4. piper synthesizes TTS |   |  4. Browser speaks TTS    |
       +---------------------------+   +---------------------------+
```

### 1. Native Offline Mode
Requires optional system dependencies for audio capture:
```bash
# Install PyAudio dependencies (on Ubuntu)
sudo apt-get install portaudio19-dev python3-pyaudio

# Install voice packages
pip install openwakeword faster-whisper piper-tts pyaudio
```

### 2. Browser Fallback Mode (Default on Windows)
If the native libraries are not installed or PyAudio lacks physical microphone access, the backend API returns a `503 Service Unavailable`. The Electron frontend catches this and switches to the Chromium-powered **Web Speech API**:
- **Continuous Listening**: The mic is held active and processes audio in real time.
- **Wake Word Recognition**: The JavaScript engine processes the stream and triggers only when the phrase `"Hey Jarvis"` is spoken.
- **Visual Feedback**: The central purple orb scale and glow pulse in sync with the activation states.

---

## Desktop Tools & Shortcuts

| Keyboard Shortcut | Action |
|-------------------|--------|
| `Ctrl+Shift+Space` | Toggle show / focus window (Global Hotkey) |
| `Space` | Toggle voice listening (Active state) |
| `T` | Toggle text-to-speech feedback (TTS) |
| `L` | Toggle developer logs pane |
| `Esc` | Hide window to system tray |

---

## Developer SDK Usage

### Python SDK
```python
from agentos import AgentOS

# Initialize client
client = AgentOS("http://localhost:8088", api_key="your-jwt-token")

# Send chat prompt
response = client.chat("Hey Jarvis, list files in the current directory.")
print(response)
```

### TypeScript SDK
```typescript
import { AgentOS } from 'agentos-sdk';

const client = new AgentOS('http://localhost:8088', 'your-jwt-token');
const response = await client.chat('Hey Jarvis, take a screenshot.');
```

---

## License

This project is licensed under the MIT License.
