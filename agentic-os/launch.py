"""
Agentic OS Launcher
====================
Unified entry point for the Agentic OS with:
  - Voice mode (STT → Agent → TTS)
  - Text mode (CLI/TUI)
  - Obsidian Brain memory sync
  - Platform gateway support

Usage:
  python launch.py              # Interactive CLI mode
  python launch.py --voice      # Voice mode (push-to-talk)
  python launch.py --tui        # Modern TUI mode
  python launch.py --gateway    # Start messaging gateway
  python launch.py --dashboard  # Start web dashboard
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if (ROOT / "pyproject.toml").exists() or (ROOT / "agentic_os_cli").exists():
    AGENTIC_ROOT = ROOT
elif (ROOT / "agentic-os").exists():
    AGENTIC_ROOT = ROOT / "agentic-os"
elif (ROOT / "agentic-os").exists():
    AGENTIC_ROOT = ROOT / "agentic-os"
else:
    AGENTIC_ROOT = ROOT
VAULT_PATH = ROOT / "obsidian-brain" if (ROOT / "obsidian-brain").exists() else ROOT.parent / "obsidian-brain"


def setup_environment():
    os.chdir(AGENTIC_ROOT)
    if str(AGENTIC_ROOT) not in sys.path:
        sys.path.insert(0, str(AGENTIC_ROOT))

    env_path = AGENTIC_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            _parse_env_file(env_path)

    vault_path = os.environ.get("OBSIDIAN_BRAIN_VAULT_PATH", str(VAULT_PATH))
    os.environ["OBSIDIAN_BRAIN_VAULT_PATH"] = vault_path

    os.environ.setdefault("TERMINAL_TIMEOUT", "120")


def _parse_env_file(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if val and key not in os.environ:
                os.environ[key] = val


def cmd_cli(args):
    setup_environment()
    from agentic_os_cli.main import main
    sys.argv = ["agentic-os"]
    main()


def cmd_tui(args):
    setup_environment()
    os.environ["AGENTIC_OS_TUI"] = "1"
    os.environ["AGENTIC_OS_TUI"] = "1"
    from agentic_os_cli.main import main
    sys.argv = ["agentic-os", "--tui"]
    main()


def cmd_voice(args):
    setup_environment()
    print("\n  Agentic OS — Voice Mode")
    print("  Speak when you see [LISTENING]")
    print("  Press Ctrl+C to exit\n")

    try:
        from run_agent import AIAgent
    except ImportError:
        sys.path.insert(0, str(AGENTIC_ROOT))
        from run_agent import AIAgent

    agent = AIAgent(
        platform="cli",
        quiet_mode=False,
    )

    import threading
    import tempfile
    import json

    def listen_once():
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            print("  Install audio deps: pip install sounddevice numpy")
            return None

        print("  [LISTENING] Speak now...", end="", flush=True)
        duration = 10
        sample_rate = 16000
        try:
            recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate,
                               channels=1, dtype="int16")
            sd.wait()
        except Exception as e:
            print(f"\n  Audio error: {e}")
            return None

        print(" [PROCESSING]", end="", flush=True)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            import wave
            with wave.open(f.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(recording.tobytes())
            wav_path = f.name

        transcript = transcribe_audio(wav_path)
        try:
            os.unlink(wav_path)
        except OSError:
            pass

        if transcript:
            print(f" {transcript}")
            return transcript
        print(" (no speech detected)")
        return None

    def transcribe_audio(wav_path: str) -> str:
        groq_key = os.environ.get("GROQ_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")

        if groq_key:
            try:
                import httpx
                with open(wav_path, "rb") as f:
                    resp = httpx.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {groq_key}"},
                        files={"file": (Path(wav_path).name, f, "audio/wav")},
                        data={"model": "whisper-large-v3-turbo"},
                        timeout=30,
                    )
                if resp.status_code == 200:
                    return resp.json().get("text", "")
            except Exception:
                pass

        if openai_key:
            try:
                import httpx
                with open(wav_path, "rb") as f:
                    resp = httpx.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {openai_key}"},
                        files={"file": (Path(wav_path).name, f, "audio/wav")},
                        data={"model": "whisper-1"},
                        timeout=30,
                    )
                if resp.status_code == 200:
                    return resp.json().get("text", "")
            except Exception:
                pass

        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(wav_path)
            return " ".join(s.text for s in segments)
        except ImportError:
            pass

        return ""

    def speak(text: str):
        tts_provider = os.environ.get("AGENTIC_OS_TTS_PROVIDER", os.environ.get("AGENTIC_OS_TTS_PROVIDER", "edge"))
        try:
            import edge_tts
            import asyncio

            async def _speak():
                voice = "en-US-AriaNeural"
                communicate = edge_tts.Communicate(text, voice)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    await communicate.save(f.name)
                    return f.name

            mp3_path = asyncio.run(_speak())
            try:
                import subprocess
                if sys.platform == "win32":
                    subprocess.run(["powershell", "-c",
                        f'(New-Object Media.SoundPlayer "{mp3_path}").PlaySync()'],
                        capture_output=True, timeout=30)
                else:
                    subprocess.run(["mpg123", mp3_path], capture_output=True, timeout=30)
            except Exception:
                try:
                    os.startfile(mp3_path)
                except Exception:
                    pass
            try:
                os.unlink(mp3_path)
            except OSError:
                pass
        except ImportError:
            pass

    try:
        while True:
            text = listen_once()
            if text and text.strip():
                if any(w in text.lower() for w in ["exit", "quit", "goodbye", "stop"]):
                    speak("Goodbye!")
                    break
                response = agent.chat(text)
                print(f"\n  [AGENT] {response}\n")
                speak(response)
    except KeyboardInterrupt:
        print("\n  Bye!")


def cmd_gateway(args):
    setup_environment()
    from agentic_os_cli.main import main
    sys.argv = ["agentic-os", "gateway"]
    main()


def cmd_dashboard(args):
    setup_environment()
    from agentic_os_cli.main import main
    sys.argv = ["agentic-os", "dashboard"]
    main()


def cmd_status(args):
    setup_environment()
    print("\n  Agentic OS — Status\n")

    env_path = AGENTIC_ROOT / ".env"
    if env_path.exists():
        env_text = env_path.read_text(encoding="utf-8")
        providers = {
            "OpenRouter": "OPENROUTER_API_KEY" in env_text and _has_value(env_text, "OPENROUTER_API_KEY"),
            "OpenAI": "OPENAI_API_KEY" in env_text and _has_value(env_text, "OPENAI_API_KEY"),
            "Anthropic": "ANTHROPIC_API_KEY" in env_text and _has_value(env_text, "ANTHROPIC_API_KEY"),
            "Groq (STT)": "GROQ_API_KEY" in env_text and _has_value(env_text, "GROQ_API_KEY"),
            "ElevenLabs (TTS)": "ELEVENLABS_API_KEY" in env_text and _has_value(env_text, "ELEVENLABS_API_KEY"),
        }
        print("  API Keys:")
        for name, configured in providers.items():
            status = "OK" if configured else "NOT SET"
            print(f"    {name}: {status}")
    else:
        print("  No .env file found!")

    vault_path = VAULT_PATH
    print(f"\n  Obsidian Vault: {vault_path}")
    if vault_path.exists():
        md_files = list(vault_path.rglob("*.md"))
        print(f"    Notes: {len(md_files)}")
        print(f"    Status: OK")
    else:
        print(f"    Status: NOT FOUND")

    print()


def _has_value(env_text: str, key: str) -> bool:
    for line in env_text.splitlines():
        if line.strip().startswith(f"{key}="):
            val = line.split("=", 1)[1].strip()
            return bool(val) and not val.startswith("#")
    return False


def cmd_setup(args):
    setup_environment()
    print("\n  Agentic OS — Setup\n")
    print("  1. Edit agentic-os/.env to add your API keys")
    print("  2. Open obsidian-brain/ in Obsidian to explore the vault")
    print("  3. Run: python launch.py          (CLI mode)")
    print("     Run: python launch.py --voice   (Voice mode)")
    print("     Run: python launch.py --tui     (Modern TUI)")
    print("     Run: python launch.py --gateway (Messaging platforms)")
    print("     Run: python launch.py --dashboard (Web dashboard)")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Agentic OS Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  (default)     Interactive CLI mode with Obsidian brain
  --voice       Voice mode: speak to agent, hear responses
  --tui         Modern terminal UI (Ink/React)
  --gateway     Start messaging platform gateway
  --dashboard   Start web dashboard
  --status      Show configuration status
  --setup       Setup instructions
        """
    )
    parser.add_argument("--voice", action="store_true", help="Voice mode")
    parser.add_argument("--tui", action="store_true", help="Modern TUI mode")
    parser.add_argument("--gateway", action="store_true", help="Start gateway")
    parser.add_argument("--dashboard", action="store_true", help="Start web dashboard")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--setup", action="store_true", help="Setup instructions")

    args = parser.parse_args()

    if args.voice:
        cmd_voice(args)
    elif args.tui:
        cmd_tui(args)
    elif args.gateway:
        cmd_gateway(args)
    elif args.dashboard:
        cmd_dashboard(args)
    elif args.status:
        cmd_status(args)
    elif args.setup:
        cmd_setup(args)
    else:
        cmd_cli(args)


if __name__ == "__main__":
    main()
