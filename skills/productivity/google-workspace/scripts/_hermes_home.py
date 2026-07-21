"""Resolve HERMES_HOME for standalone skill scripts.

Skill scripts may run outside the Hermes process (e.g. system Python,
nix env, CI) where ``agentic_os_constants`` is not importable.  This module
provides the same ``get_agentic_os_home()`` and ``display_agentic_os_home()``
contracts as ``agentic_os_constants`` without requiring it on ``sys.path``.

When ``agentic_os_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``agentic_os_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``HERMES_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from agentic_os_constants import display_agentic_os_home as display_agentic_os_home
    from agentic_os_constants import get_agentic_os_home as get_agentic_os_home
except (ModuleNotFoundError, ImportError):

    def get_agentic_os_home() -> Path:
        """Return the Hermes home directory (default: ~/.hermes).

        Mirrors ``agentic_os_constants.get_agentic_os_home()``."""
        val = os.environ.get("HERMES_HOME", "").strip()
        return Path(val) if val else Path.home() / ".hermes"

    def display_agentic_os_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``agentic_os_constants.display_agentic_os_home()``."""
        home = get_agentic_os_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
