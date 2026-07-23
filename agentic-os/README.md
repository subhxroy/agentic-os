<p align="center">
  <img src="assets/agentic-os-banner.png" alt="Agentic OS" width="100%">
</p>

# Agentic OS Engine ☤

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/nousresearch/hermes-agent"><img src="https://img.shields.io/badge/Based%20on-Hermes%20Agent-purple?style=for-the-badge" alt="Based on Hermes Agent"></a>
  <a href="https://nousresearch.com"><img src="https://img.shields.io/badge/Upstream-Nous%20Research-blueviolet?style=for-the-badge" alt="Upstream Nous Research"></a>
  <a href="https://github.com/subhxroy"><img src="https://img.shields.io/badge/Customized%20by-Subhankar%20Roy-blue?style=for-the-badge" alt="Customized by Subhankar Roy"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
</p>

## Overview

**Agentic OS Core Engine** is the underlying reasoning, tool execution, and agent runtime framework powering Agentic OS. It features a closed-loop learning architecture, autonomous skill creation, FTS5 session memory retrieval, multi-platform gateway connectors, and dynamic tool invocation.

---

## Origin & Provenance

This codebase is based on the open-source **[Hermes Agent](https://github.com/nousresearch/hermes-agent)** project created by **[Nous Research](https://nousresearch.com)** (MIT License). 

It has been customized, extended, and rebranded by **Subhankar Roy** with workspace restructuring, unified launchers, Obsidian memory integration, custom provider authentication, voice pipeline stabilization, and desktop application surfaces.

---

## What's New in Agentic OS

- **Custom Provider Authentication**: Configurable HTTP headers (Bearer, `x-api-key`, custom names) and local endpoint optimizations (Ollama slug normalization, API key bypass).
- **Obsidian Brain Sync**: Automated memory vault synchronization connecting agent state with Obsidian markdown notes.
- **Voice Pipeline Upgrades**: Non-continuous auto-restarting speech-to-text loop for desktop apps, resolving audio dependencies and eliminating infinite print loops.
- **Electron Desktop Integration**: Native desktop application surface (`apps/desktop`) with SQLite state management.
- **System Prompt Optimizations**: Casual greeting tool-call optimizations and robust Windows process spawning execution.

---

## Strategic Roadmap

For the master 22-pillar architectural roadmap, see **[../ROADMAP.md](../ROADMAP.md)**.

---

## Quickstart

Run via the workspace root launchers:

```bash
# Node.js Launcher
node ../server.js

# Python Launcher
python ../launch.py
```

Or execute directly within this directory:

```bash
# Run agent CLI
python run_agent.py

# Run CLI framework
python -m agentic_os_cli.main
```

---

## Attribution

Derived from **[Hermes Agent](https://github.com/nousresearch/hermes-agent)** by **[Nous Research](https://nousresearch.com)**, with substantial extensions developed by **[Subhankar Roy](https://github.com/subhxroy)**.

---

## License

This project is licensed under the MIT License — see the [`LICENSE`](LICENSE) file in this directory.
