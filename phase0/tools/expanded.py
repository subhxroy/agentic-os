"""
Phase 9 expanded tools — desktop-native capabilities.
All tools require permission gating via the existing permission system.
"""

import os
import json
import time
from typing import Optional
from tools.registry import register_tool, confirm_tool


# ============================================================
# Screenshots (mss)
# ============================================================
@register_tool(
    name="take_screenshot",
    description="Capture screenshot of full screen or specific region",
    parameters={
        "region": {"type": "string", "enum": ["full", "primary", "region"], "default": "primary"},
        "region_coords": {"type": "object", "description": "x,y,w,h for region capture"},
    },
    permission="screenshot",
    timeout=10,
)
def take_screenshot(region: str = "primary", region_coords: Optional[dict] = None) -> dict:
    try:
        import mss
        from PIL import Image
        import io
        import base64
        import tempfile

        with mss.mss() as sct:
            if region == "full":
                monitor = sct.monitors[0]
            elif region == "region" and region_coords:
                monitor = region_coords
            else:
                monitor = sct.monitors[1]  # primary

            img = sct.grab(monitor)
            png = mss.tools.to_png(img.rgb, img.size)

            # Save to temp file
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(png)
            tmp.close()

            return {
                "status": "success",
                "path": tmp.name,
                "size": img.size,
            }
    except ImportError:
        return {"error": "mss not installed. Install: pip install mss"}


# ============================================================
# Clipboard (pyperclip)
# ============================================================
@register_tool(
    name="clipboard_read",
    description="Read current clipboard contents",
    parameters={},
    permission="clipboard",
    timeout=5,
)
def clipboard_read() -> dict:
    try:
        import pyperclip
        content = pyperclip.paste()
        return {"content": content}
    except ImportError:
        return {"error": "pyperclip not installed. Install: pip install pyperclip"}


@register_tool(
    name="clipboard_write",
    description="Write text to clipboard",
    parameters={"text": {"type": "string", "description": "Text to copy to clipboard"}},
    permission="clipboard",
    timeout=5,
)
def clipboard_write(text: str) -> dict:
    try:
        import pyperclip
        pyperclip.copy(text)
        return {"status": "success"}
    except ImportError:
        return {"error": "pyperclip not installed. Install: pip install pyperclip"}


# ============================================================
# Volume Control
# ============================================================
@register_tool(
    name="volume_set",
    description="Set system volume (0-100)",
    parameters={"level": {"type": "integer", "minimum": 0, "maximum": 100}},
    permission="volume",
    timeout=5,
)
def volume_set(level: int) -> dict:
    try:
        import subprocess
        import platform

        system = platform.system()
        if system == "Windows":
            # Use nircmd or PowerShell
            level_scalar = int(level * 65535 / 100)
            subprocess.run(
                ["powershell", "-Command",
                 f"(Get-WmiObject -Class Win32_SoundDevice).SetVolume({level_scalar})"],
                capture_output=True, timeout=5
            )
        elif system == "Darwin":
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"], timeout=5)
        elif system == "Linux":
            subprocess.run(["amixer", "set", "Master", f"{level}%"], timeout=5)

        return {"status": "success", "level": level}
    except Exception as e:
        return {"error": str(e)}


@register_tool(
    name="volume_get",
    description="Get current system volume level",
    parameters={},
    permission="volume",
    timeout=5,
)
def volume_get() -> dict:
    try:
        import subprocess
        import platform
        import re

        system = platform.system()
        if system == "Windows":
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-AudioDevice -PlaybackVolume)"],
                capture_output=True, text=True, timeout=5
            )
            level = int(re.search(r"(\d+)", result.stdout).group(1)) if result.stdout else 0
        elif system == "Darwin":
            result = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                                    capture_output=True, text=True, timeout=5)
            level = int(result.stdout.strip()) if result.stdout.strip() else 0
        elif system == "Linux":
            result = subprocess.run(["amixer", "get", "Master"], capture_output=True, text=True, timeout=5)
            match = re.search(r"\[(\d+)%\]", result.stdout)
            level = int(match.group(1)) if match else 0
        else:
            level = 0

        return {"level": level}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Notifications (plyer)
# ============================================================
@register_tool(
    name="send_notification",
    description="Send desktop notification",
    parameters={
        "title": {"type": "string"},
        "message": {"type": "string"},
        "timeout": {"type": "integer", "default": 5},
    },
    permission="notifications",
    timeout=10,
)
def send_notification(title: str, message: str, timeout: int = 5) -> dict:
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            timeout=timeout,
        )
        return {"status": "success"}
    except ImportError:
        return {"error": "plyer not installed. Install: pip install plyer"}


# ============================================================
# OCR (pytesseract + Pillow)
# ============================================================
@register_tool(
    name="ocr_extract",
    description="Extract text from image using OCR",
    parameters={
        "image_path": {"type": "string", "description": "Path to image file"},
        "language": {"type": "string", "default": "eng"},
    },
    permission="ocr",
    timeout=30,
)
def ocr_extract(image_path: str, language: str = "eng") -> dict:
    try:
        import pytesseract
        from PIL import Image

        if not os.path.exists(image_path):
            return {"error": f"Image not found: {image_path}"}

        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=language)
        return {"text": text.strip()}
    except ImportError:
        return {"error": "pytesseract not installed. Install: pip install pytesseract"}


# ============================================================
# Browser Automation (Playwright)
# ============================================================
@register_tool(
    name="browser_navigate",
    description="Navigate to URL in headless browser",
    parameters={"url": {"type": "string", "format": "uri"}},
    permission="browser",
    timeout=30,
)
def browser_navigate(url: str) -> dict:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=20000)
            title = page.title()
            content = page.content()
            browser.close()

            return {"title": title, "content": content[:5000]}
    except ImportError:
        return {"error": "playwright not installed. Install: pip install playwright && playwright install"}


@register_tool(
    name="browser_click",
    description="Click element on page by CSS selector",
    parameters={
        "url": {"type": "string", "format": "uri"},
        "selector": {"type": "string", "description": "CSS selector"},
    },
    permission="browser",
    timeout=15,
)
def browser_click(url: str, selector: str) -> dict:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=20000)
            page.click(selector, timeout=5000)
            result = {"status": "clicked", "url": page.url}
            browser.close()
            return result
    except ImportError:
        return {"error": "playwright not installed. Install: pip install playwright && playwright install"}


# ============================================================
# File Operations (Phase 7)
# ============================================================
@register_tool(
    name="file_read",
    description="Read file contents",
    parameters={"path": {"type": "string"}},
    permission="filesystem",
    timeout=10,
)
def file_read(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "size": len(content)}
    except Exception as e:
        return {"error": str(e)}


@register_tool(
    name="file_write",
    description="Write content to file",
    parameters={
        "path": {"type": "string"},
        "content": {"type": "string"},
    },
    permission="filesystem",
    timeout=10,
)
def file_write(path: str, content: str) -> dict:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "success", "path": path, "size": len(content)}
    except Exception as e:
        return {"error": str(e)}


@register_tool(
    name="file_list",
    description="List files in directory",
    parameters={
        "path": {"type": "string", "default": "."},
        "pattern": {"type": "string", "default": "*"},
    },
    permission="filesystem",
    timeout=5,
)
def file_list(path: str = ".", pattern: str = "*") -> dict:
    try:
        import glob
        files = glob.glob(os.path.join(path, pattern))
        entries = []
        for f in files[:100]:  # limit
            stat = os.stat(f)
            entries.append({
                "name": os.path.basename(f),
                "path": f,
                "is_dir": os.path.isdir(f),
                "size": stat.st_size,
            })
        return {"entries": entries, "count": len(entries)}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Scheduling (APScheduler)
# ============================================================
_scheduler = None

def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            _scheduler = BackgroundScheduler()
            _scheduler.start()
        except ImportError:
            pass
    return _scheduler


@register_tool(
    name="schedule_task",
    description="Schedule a task to run later",
    parameters={
        "task_id": {"type": "string", "description": "Unique task ID"},
        "delay_seconds": {"type": "integer", "description": "Delay in seconds"},
        "message": {"type": "string", "description": "Message to process when task runs"},
    },
    permission="scheduling",
    timeout=5,
)
def schedule_task(task_id: str, delay_seconds: int, message: str) -> dict:
    scheduler = _get_scheduler()
    if not scheduler:
        return {"error": "APScheduler not installed. Install: pip install apscheduler"}

    from datetime import datetime, timedelta

    def run_task():
        # Emit Socket.IO event when task runs
        from server import socketio
        socketio.emit("scheduled_task", {
            "task_id": task_id,
            "message": message,
            "ran_at": datetime.now().isoformat(),
        }, namespace="/")

    run_time = datetime.now() + timedelta(seconds=delay_seconds)
    scheduler.add_job(run_task, "date", run_date=run_time, id=task_id, replace_existing=True)
    return {"status": "scheduled", "task_id": task_id, "run_at": run_time.isoformat()}


@register_tool(
    name="cancel_task",
    description="Cancel a scheduled task",
    parameters={"task_id": {"type": "string"}},
    permission="scheduling",
    timeout=5,
)
def cancel_task(task_id: str) -> dict:
    scheduler = _get_scheduler()
    if not scheduler:
        return {"error": "APScheduler not installed"}

    try:
        scheduler.remove_job(task_id)
        return {"status": "cancelled", "task_id": task_id}
    except Exception:
        return {"error": f"Task not found: {task_id}"}
