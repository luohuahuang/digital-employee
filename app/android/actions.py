"""
android/actions.py — ADB device control primitives

Wraps adb shell commands to drive a connected Android device or emulator.
No Appium server or app instrumentation required.

Caller is responsible for ensuring:
  - adb is on PATH
  - target device is connected (real device via USB/wifi, or emulator running)
  - device_serial matches `adb devices` output (or None for the sole connected device)
"""
from __future__ import annotations

import base64
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ActionResult:
    success: bool
    error: str = ""


class AndroidSession:
    """
    Thin wrapper around ADB commands for one test run.

    Usage:
        session = AndroidSession(device_serial="emulator-5554")
        session.launch_app("com.shopee.sg")
        session.tap(540, 960)
        b64 = session.screenshot_b64()
    """

    def __init__(self, device_serial: str | None = None):
        """
        device_serial: value from `adb devices` (e.g. "emulator-5554" or "R3CN80XXXXX").
                       Pass None to use the only connected device.
        """
        self._s = ["-s", device_serial] if device_serial else []
        self._screen_size: tuple[int, int] | None = None

    # ── Internal helper ────────────────────────────────────────────────────────

    def _adb(self, *args: str, timeout: int = 30) -> str:
        """Run an adb command and return stdout as a string."""
        result = subprocess.run(
            ["adb", *self._s, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout

    def _adb_raw(self, *args: str, timeout: int = 15) -> bytes:
        """Run an adb command and return raw stdout bytes."""
        result = subprocess.run(
            ["adb", *self._s, *args],
            capture_output=True,
            timeout=timeout,
        )
        return result.stdout

    # ── Device info ────────────────────────────────────────────────────────────

    def get_screen_size(self) -> tuple[int, int]:
        """
        Return (width, height) in pixels.
        Result is cached — the screen size doesn't change during a run.
        """
        if not self._screen_size:
            out = self._adb("shell", "wm", "size")
            # Output: "Physical size: 1080x2340\n" (or "Override size: ...")
            for line in out.splitlines():
                if "size:" in line.lower():
                    dims = line.strip().split()[-1]  # "1080x2340"
                    w, h = dims.split("x")
                    self._screen_size = (int(w), int(h))
                    break
            if not self._screen_size:
                # Safe fallback
                self._screen_size = (1080, 1920)
        return self._screen_size

    # ── Screenshot ─────────────────────────────────────────────────────────────

    def screenshot_b64(self) -> str:
        """Take a screenshot and return as base64-encoded PNG string."""
        raw = self._adb_raw("exec-out", "screencap", "-p")
        return base64.b64encode(raw).decode("utf-8")

    def screenshot_save(self, path: str) -> str:
        """Take a screenshot and save to disk. Returns the path."""
        raw = self._adb_raw("exec-out", "screencap", "-p")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(raw)
        return path

    # ── Touch actions ──────────────────────────────────────────────────────────

    def tap(self, x: int, y: int) -> ActionResult:
        """Single tap at (x, y)."""
        try:
            self._adb("shell", "input", "tap", str(x), str(y))
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> ActionResult:
        """Long press at (x, y) for duration_ms milliseconds."""
        try:
            # Swipe in place = long press
            self._adb(
                "shell", "input", "swipe",
                str(x), str(y), str(x), str(y), str(duration_ms),
            )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def swipe(
        self,
        x1: int, y1: int,
        x2: int, y2: int,
        duration_ms: int = 300,
    ) -> ActionResult:
        """
        Swipe from (x1, y1) to (x2, y2) over duration_ms milliseconds.
        To scroll DOWN: swipe upward, i.e. y1 > y2.
        To scroll UP:   swipe downward, i.e. y1 < y2.
        """
        try:
            self._adb(
                "shell", "input", "swipe",
                str(x1), str(y1), str(x2), str(y2), str(duration_ms),
            )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    # ── Keyboard / text ────────────────────────────────────────────────────────

    def type_text(self, text: str) -> ActionResult:
        """
        Type ASCII text into the focused field.
        Spaces are percent-encoded (%s) as required by adb input text.
        Non-ASCII characters are silently replaced — use ADBKeyboard APK for
        full Unicode support if needed in the future.
        """
        try:
            # Replace space with %s (adb input text escaping)
            # Escape special shell characters
            safe = text.replace("\\", "\\\\").replace("'", "\\'")
            safe = safe.replace(" ", "%s").replace("&", "\\&")
            self._adb("shell", "input", "text", safe)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def press_key(self, keycode: str) -> ActionResult:
        """
        Press an Android keycode by name, e.g.:
          KEYCODE_BACK, KEYCODE_HOME, KEYCODE_ENTER, KEYCODE_DEL,
          KEYCODE_TAB, KEYCODE_SEARCH, KEYCODE_DPAD_DOWN, etc.
        """
        try:
            self._adb("shell", "input", "keyevent", keycode)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    # ── App lifecycle ──────────────────────────────────────────────────────────

    def launch_app(self, package: str, activity: str | None = None) -> ActionResult:
        """
        Launch an app by package name.
        If activity is provided, starts that specific component.
        Otherwise uses the monkey launcher (fires the LAUNCHER intent).
        """
        try:
            if activity:
                self._adb("shell", "am", "start", "-n", f"{package}/{activity}")
            else:
                self._adb(
                    "shell", "monkey",
                    "-p", package,
                    "-c", "android.intent.category.LAUNCHER",
                    "1",
                )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    # ── Timing ─────────────────────────────────────────────────────────────────

    def wait(self, ms: int = 1000) -> ActionResult:
        """Wait for ms milliseconds."""
        try:
            time.sleep(ms / 1000)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    # ── Dispatch ───────────────────────────────────────────────────────────────

    def execute_action(self, action: dict) -> ActionResult:
        """
        Dispatch a structured action dict as returned by android/vision.decide_actions().

        Supported action types:
          {"type": "tap",        "x": 540, "y": 960}
          {"type": "long_press", "x": 540, "y": 960, "duration_ms": 1000}
          {"type": "type",       "text": "hello world"}
          {"type": "key",        "keycode": "KEYCODE_BACK"}
          {"type": "swipe",      "x1": 540, "y1": 1400, "x2": 540, "y2": 600, "duration_ms": 300}
          {"type": "launch",     "package": "com.shopee.sg", "activity": ".MainActivity"}
          {"type": "wait",       "ms": 1500}
        """
        t = action.get("type", "")
        if t == "tap":
            return self.tap(int(action["x"]), int(action["y"]))
        elif t == "long_press":
            return self.long_press(
                int(action["x"]), int(action["y"]),
                int(action.get("duration_ms", 1000)),
            )
        elif t == "type":
            return self.type_text(action["text"])
        elif t == "key":
            return self.press_key(action["keycode"])
        elif t == "swipe":
            return self.swipe(
                int(action["x1"]), int(action["y1"]),
                int(action["x2"]), int(action["y2"]),
                int(action.get("duration_ms", 300)),
            )
        elif t == "launch":
            return self.launch_app(action["package"], action.get("activity"))
        elif t == "wait":
            return self.wait(int(action.get("ms", 1000)))
        else:
            return ActionResult(success=False, error=f"Unknown action type: {t!r}")
