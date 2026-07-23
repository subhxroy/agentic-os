# Repository Changelog & Evolution Record

This document summarizes the history of repository modifications, architectural evolution, feature additions, and documentation updates for **Agentic OS**.

---

## 1. Upstream Origin & Core Foundation

- **Base Project**: Open-source **[Hermes Agent](https://github.com/nousresearch/hermes-agent)** developed by **[Nous Research](https://nousresearch.com)** (MIT License).
- **Core Capabilities Preserved**: Self-improving AI agent loop, tool execution framework, multi-surface interfaces (CLI, TUI, Gateway), autonomous skill synthesis, and FTS5 session search.

---

## 2. Key Customizations & Enhancements (by Subhankar Roy)

### Architecture & Repository Restructuring
- Restructured workspace layout into modular components: `launch.py` (Python launcher), `server.js` (Node.js launcher), `obsidian-brain/` (Markdown memory vault), `agentic-os/` (Core engine), and `apps/desktop/` (Electron App).
- Conducted full package and namespace rebrand (`@/agentic-os`, `@agentic-os`, `AGENTIC_OS_*` environment variables).

### Unified Launchers
- **`launch.py`**: Added Python root entry point supporting `--voice`, `--tui`, `--gateway`, `--dashboard`, `--status`, and `--setup`.
- **`server.js`**: Added interactive Node.js surface selector menu with robust cross-platform process management (resolving `EINVAL` execution bugs under Windows). Added `--add-provider` CLI workflow for custom LLM configuration.

### Memory & Knowledge Graph Integration
- Introduced **Obsidian Brain** vault integration (`obsidian-brain/`) with sub-directories for `memories/`, `conversations/`, `journal/`, `projects/`, and `skills/`.
- Implemented bidirectional sync between AI agent state and Obsidian markdown files for long-term knowledge retention.

### Custom LLM Providers & Authentication
- Added support for custom LLM endpoints with customizable HTTP header authentication schemes (Bearer tokens, `x-api-key`, custom headers).
- Added local provider optimizations (model slug auto-completion, prefix stripping for Ollama, API key check exemptions for local endpoints).

### Voice & Desktop Application Upgrades
- Upgraded voice processing loop with stable non-continuous auto-restart mode for Electron desktop environments.
- Fixed voice dependencies (`faster-whisper`, `sounddevice`, `numpy`, `edge-tts`) and eliminated infinite print output loops in voice mode.
- Added hybrid browser-side wake-word fallback detection ("Jarvis").
- Integrated Electron desktop application surface with local SQLite state management and brand assets.

---

## 3. Documentation & Strategic Roadmap Overhaul

- **Strategic Next-Gen Roadmap (`ROADMAP.md`)**: Created [`ROADMAP.md`](ROADMAP.md) detailing 22 strategic feature domains: Proactive Intelligence, Agent Networks, Knowledge Graphs, Visual Computer Use, Workflow Engines, Cost Intelligence, Real-time Collab, Observability, Code Intelligence, Multi-modal Capabilities, Enterprise Security, and Plugin Ecosystem 2.0.
- **Provenance & Attribution**: Updated [`README.md`](README.md) to explicitly state upstream origin (Hermes Agent by Nous Research) and describe extensions added by Subhankar Roy.
- **Copyright & License Preservation**: Retained original MIT License in [`agentic-os/LICENSE`](agentic-os/LICENSE) (Copyright (c) 2025 Nous Research).
- **Architecture & Features**: Documented repository layout, launch options, Obsidian brain vault, and custom LLM provider engine.
- **Repository Metadata Recommendations**: Standardized GitHub About text, Topics, and badges.
