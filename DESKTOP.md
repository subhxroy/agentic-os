# AgentOS Desktop

Native desktop application powered by Electron + Python backend.

## Quick Start

### Windows
Double-click `start-desktop.bat`

### Manual
```bash
# 1. Install Python dependencies
cd phase0
pip install -r ../electron/requirements.txt

# 2. Install Electron dependencies
cd ../electron
npm install

# 3. Launch
npm start
```

## Features

- **Voice Pipeline**: Always-on wake word detection → STT → TTS (local, offline)
- **Auto-Login**: Single-user mode, no auth wall on launch
- **Global Hotkey**: `Ctrl+Shift+Space` to show/focus window
- **System Tray**: Runs in background, double-click to show
- **Local Embeddings**: sentence-transformers (all-MiniLM-L6-v2)

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Toggle voice listening |
| `T` | Toggle TTS on/off |
| `L` | Toggle conversation log |
| `Esc` | Hide window |

## Requirements

- Python 3.10+
- Node.js 18+
- Windows 10+, macOS 11+, or Ubuntu 20.04+

## Voice Pipeline (Optional)

For full voice support:
```bash
pip install openwakeword faster-whisper piper-tts pyaudio
```

Without these, uses browser Web Speech API as fallback.

## Architecture

```
electron/
├── main.js          # Electron main process (Python supervision, tray, hotkey)
├── preload.js       # contextBridge for renderer IPC
├── package.json     # Electron config + build targets
├── requirements.txt # Python dependencies
└── renderer/
    └── index.html   # Desktop Jarvis UI

phase0/
├── server.py        # Flask+SocketIO backend (auto-started)
├── database.py      # SQLite + diskcache (no Docker required)
├── voice/
│   └── pipeline.py  # VoicePipeline (wake → STT → TTS)
├── embeddings/
│   └── local.py     # sentence-transformers integration
└── tools/
    └── expanded.py  # 15 desktop-native tools
```

## Data Location

User data stored in OS-appropriate location:
- Windows: `%APPDATA%/AgentOS/`
- macOS: `~/Library/Application Support/AgentOS/`
- Linux: `~/.config/AgentOS/`
