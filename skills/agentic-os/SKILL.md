---
name: agentic-os
description: Agentic OS voice mode and Obsidian brain integration.
platforms: [linux, macos, windows]
metadata:
  agentic-os:
    tags: [voice, obsidian, brain, agentic]
    category: productivity
---

# Agentic OS Skill

Voice-first interaction with Obsidian brain memory.

## When to Use

- User wants to interact via voice
- User asks about their memories or past conversations
- User wants to save something to their Obsidian brain
- User wants to see vault statistics

## Prerequisites

- Audio input device (microphone)
- `sounddevice`, `numpy`, `edge-tts`, `faster-whisper` Python packages
- Obsidian vault at `obsidian-brain/` directory

## Voice Mode

To enter voice mode, use the launcher:
```
python launch.py --voice
```

The voice pipeline:
1. Records audio from microphone (push-to-talk)
2. Transcribes via faster-whisper (local) or Groq/OpenAI (cloud)
3. Sends text to agent
4. Agent responds with edge-tts (free neural voices)

## Obsidian Brain Tools

The agent has these tools for Obsidian brain interaction:

- `obsidian_search` — Search vault notes by content
- `obsidian_add_memory` — Save a memory note with tags
- `obsidian_delete_memory` — Remove a note by ID
- `obsidian_stats` — Get vault statistics
- `obsidian_journal` — Write a daily journal entry

## Memory Conventions

When saving memories:
- Use descriptive tags (e.g., `preference`, `project`, `decision`)
- Frontmatter includes: id, created, updated, type, tags
- Link related notes with `[[wikilinks]]`
- Keep memories concise but complete

## Quick Reference

```bash
# Voice mode
python launch.py --voice

# Check vault status
python launch.py --status

# Open vault in Obsidian
# Open: obsidian-brain/ folder
```
