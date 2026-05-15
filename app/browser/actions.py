"""
browser/actions.py — Playwright primitives

Manages a single browser instance for the duration of one test case.
All methods are synchronous (using Playwright's sync API).
"""
from __future__ import annotations
import base64
import time
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ActionResult:
    success: bool
    error: str = ""


class BrowserSession:
    """
    Wraps a single Playwright browser page.
    Caller is responsible for calling open() and close().
    """

    def __init__(self, headless: bool = True, slow_mo: int = 100):
        self.headless = headless
        self.slow_mo = slow_mo
        self._playwright = None
        self._browser = None
        self._page = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def open(self) -> None:
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )
        self._page = self._browser.new_page(
            viewport={"width": 1280, "height": 800},
        )

    def close(self) -> None:
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._browser = None
        self._playwright = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Actions ────────────────────────────────────────────────────────────────

    def navigate(self, url: str, timeout: int = 15000) -> ActionResult:
        try:
            self._page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def click(self, x: int, y: int) -> ActionResult:
        try:
            self._page.mouse.click(x, y)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def type_text(self, text: str, delay: int = 50) -> ActionResult:
        """Type text at the currently focused element."""
        try:
            self._page.keyboard.type(text, delay=delay)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def press_key(self, key: str) -> ActionResult:
        """Press a keyboard key, e.g. 'Enter', 'Tab', 'Escape'."""
        try:
            self._page.keyboard.press(key)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def scroll(self, direction: Literal["up", "down", "left", "right"],
               amount: int = 300) -> ActionResult:
        try:
            dx = {"left": -amount, "right": amount}.get(direction, 0)
            dy = {"up": -amount, "down": amount}.get(direction, 0)
            self._page.mouse.wheel(dx, dy)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def wait(self, ms: int = 1000) -> ActionResult:
        """Wait for a fixed number of milliseconds."""
        try:
            time.sleep(ms / 1000)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def wait_for_network_idle(self, timeout: int = 8000) -> ActionResult:
        try:
            self._page.wait_for_load_state("networkidle", timeout=timeout)
            return ActionResult(success=True)
        except Exception:
            # Non-fatal — page may never fully reach networkidle (e.g. polling)
            return ActionResult(success=True)

    # ── Screenshot ─────────────────────────────────────────────────────────────

    def screenshot_b64(self) -> str:
        """Take a full-page screenshot and return as base64-encoded PNG string."""
        png_bytes = self._page.screenshot(full_page=False)
        return base64.b64encode(png_bytes).decode("utf-8")

    def screenshot_save(self, path: str) -> str:
        """Take a screenshot and save to disk. Returns the path."""
        self._page.screenshot(path=path, full_page=False)
        return path

    def current_url(self) -> str:
        return self._page.url if self._page else ""

    # ── Dispatch helper ────────────────────────────────────────────────────────

    def execute_action(self, action: dict) -> ActionResult:
        """
        Dispatch a structured action dict returned by vision.decide_actions().

        Supported action types:
          {"type": "navigate", "url": "..."}
          {"type": "click",    "x": 100, "y": 200}
          {"type": "type",     "text": "..."}
          {"type": "press",    "key": "Enter"}
          {"type": "scroll",   "direction": "down", "amount": 300}
          {"type": "wait",     "ms": 1000}
        """
        t = action.get("type", "")
        if t == "navigate":
            return self.navigate(action["url"])
        elif t == "click":
            return self.click(int(action["x"]), int(action["y"]))
        elif t == "type":
            return self.type_text(action["text"])
        elif t == "press":
            return self.press_key(action["key"])
        elif t == "scroll":
            return self.scroll(action.get("direction", "down"), int(action.get("amount", 300)))
        elif t == "wait":
            return self.wait(int(action.get("ms", 1000)))
        else:
            return ActionResult(success=False, error=f"Unknown action type: {t!r}")
