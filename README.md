<p align="center">
  <img src="agentic-os/assets/agentic-os-banner.png" alt="Agentic OS" width="100%">
</p>

# Agentic OS ☤

<p align="center">
  <a href="https://github.com/subhxroy/agentic-os">Agentic OS Core</a> | <a href="https://github.com/subhxroy/agentic-os/tree/master/obsidian-brain">Obsidian Brain</a>
</p>

<p align="center">
  <a href="https://github.com/subhxroy/agentic-os/blob/master/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://nousresearch.com"><img src="https://img.shields.io/badge/Built%20by-Nous%20Research-blueviolet?style=for-the-badge" alt="Built by Nous Research"></a>
  <a href="https://github.com/subhxroy/agentic-os/issues"><img src="https://img.shields.io/badge/Issues-Open-orange?style=for-the-badge" alt="Issues"></a>
</p>

**Agentic OS** is a self-improving AI agent system integrated with an Obsidian memory vault, voice pipeline, interactive terminal UI, and messaging gateways. It features a closed learning loop — creating skills from experience, persisting structured notes, and recalling context across sessions.

---

## Workspace Layout

```text
agentic-os/
├── README.md               # Main project overview & quickstart
├── launch.py               # Unified launcher (CLI, TUI, Voice, Gateway, Dashboard)
├── obsidian-brain/         # Persistent Obsidian markdown memory vault & knowledge graph
│   ├── README.md
│   ├── memories/           # Facts, user preferences, auto-synced memories
│   ├── journal/            # Activity logs and session summaries
│   └── projects/           # Project notes and context
└── agentic-os/             # Core AI agent engine & CLI framework
    ├── agentic_os_cli/     # Command line interface & web server
    ├── agent/              # Agent reasoning loop & LLM handlers
    ├── tools/              # 40+ built-in agent execution tools
    ├── pyproject.toml      # Package & dependency specifications
    └── run_agent.py        # Core agent execution entry point
```

---

## Quickstart & Launch Modes

Run the unified launcher from the workspace root:

```bash
# 1. Interactive CLI Mode (default)
python launch.py

# 2. Modern Terminal UI (Ink/React TUI)
python launch.py --tui

# 3. Voice Mode (Push-to-talk speech-to-text & text-to-speech)
python launch.py --voice

# 4. Multi-Platform Gateway (Telegram, Discord, Slack, WhatsApp, Signal)
python launch.py --gateway

# 5. Web Dashboard (Localhost SPA & API server)
python launch.py --dashboard

# 6. Check System Status & API Configuration
python launch.py --status

# 7. Setup Guide
python launch.py --setup
```

---

## Features

- 🧠 **Obsidian Brain**: Bidirectional markdown vault sync for long-term memory, reflections, and knowledge graphs.
- 🎙️ **Voice Integration**: Hands-free speech-to-text transcription (Groq / Whisper) and natural text-to-speech output (Edge TTS / ElevenLabs).
- 💻 **Real Terminal & TUI**: Full TUI with multiline editing, slash commands, conversation history, and streaming tool execution.
- ⚡ **Multi-Platform Gateway**: Single gateway process connecting Telegram, Discord, Slack, WhatsApp, Signal, and Email.
- 🛠️ **Autonomous Learning**: Autonomous skill creation from complex tasks and self-improving skill definitions.

---

## License

MIT — see [agentic-os/LICENSE](agentic-os/LICENSE).
