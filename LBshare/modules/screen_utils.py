"""
Screen Utilities
================
Shared helpers for screenshots, OCR, template matching, and clicking.
Every module calls this instead of using pyautogui directly.

All detection methods default to SCREENSHOT_REGION from config,
so OpenCV and Tesseract only scan the game window — not the full monitor.
"""

import logging
import os
import re
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pyautogui
import pytesseract
from PIL import Image

from config import BotConfig


class ScreenUtils:
    def __init__(self, config: BotConfig, logger: logging.Logger):
        self.cfg = config
        self.log = logger

        if os.path.exists(config.TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

        pyautogui.PAUSE = 0.3
        pyautogui.FAILSAFE = True

    # ── Region Helper ────────────────────────────────────────────────────

    def _region(self, region=None):
        if region is not None:
            return region
        return self.cfg.SCREENSHOT_REGION

    # ── Screenshots ──────────────────────────────────────────────────────

    def grab_screen(self, region=None) -> np.ndarray:
        shot = pyautogui.screenshot(region=self._region(region))
        return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)

    def grab_pil(self, region=None) -> Image.Image:
        return pyautogui.screenshot(region=self._region(region))

    # ── Debug: Save Screenshot ───────────────────────────────────────────

    def save_debug_screenshot(self, filename: str = "debug_screenshot.png", region=None):
        """
        Save a screenshot to disk for debugging.
        Call this to see exactly what the bot sees.
        """
        img = self.grab_pil(region)
        path = os.path.join(self.cfg.BASE_DIR, filename)
        img.save(path)
        self.log.info(f"Debug screenshot saved: {path}")
        return path

    # ── Template Matching (wraps pyautogui.locateOnScreen) ───────────────

    def find_image(
        self,
        image_name: str,
        confidence: Optional[float] = None,
        region=None,
    ) -> Optional[Tuple[int, int]]:
        path = self._resolve_image(image_name)
        if not path or not os.path.isfile(path):
            self.log.debug(f"Image file not found: {image_name}")
            return None

        conf = confidence or self.cfg.DEFAULT_CONFIDENCE
        scan_region = self._region(region)

        try:
            loc = pyautogui.locateOnScreen(path, confidence=conf, region=scan_region)
            if loc:
                pos = pyautogui.center(loc)
                self.log.debug(f"Found '{image_name}' at ({pos.x}, {pos.y})")
                return (pos.x, pos.y)
        except pyautogui.ImageNotFoundException:
            pass
        except Exception as e:
            self.log.debug(f"locateOnScreen error for '{image_name}': {e}")
        return None

    def find_any_image(
        self,
        image_names: List[str],
        confidence: Optional[float] = None,
        region=None,
    ) -> Optional[Tuple[str, int, int]]:
        for name in image_names:
            pos = self.find_image(name, confidence, region)
            if pos:
                return (name, pos[0], pos[1])
        return None

    def click_image(
        self,
        image_name: str,
        confidence: Optional[float] = None,
        retries: int = 1,
        retry_delay: float = 0.5,
        region=None,
    ) -> bool:
        for attempt in range(retries):
            pos = self.find_image(image_name, confidence, region)
            if pos:
                self.click(*pos)
                return True
            if attempt < retries - 1:
                time.sleep(retry_delay)
        return False

    # ── OCR ───────────────────────────────────────────────────────────────

    def ocr_screen(self, region=None) -> str:
        img = self.grab_pil(region)
        return self._ocr_image(img)

    def ocr_region(self, region: Tuple[int, int, int, int]) -> str:
        """OCR an exact (x, y, w, h) rectangle — bypasses default region."""
        img = pyautogui.screenshot(region=region)
        return self._ocr_image(img)

    def ocr_timer_region(self, region: Tuple[int, int, int, int]) -> str:
        """
        Specialized OCR for timer text (white/light text on dark background).
        Uses inverted binary threshold instead of adaptive threshold.
        """
        try:
            img = pyautogui.screenshot(region=region)
            scale = 3  # higher scale for small text
            img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
            grey = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)

            # Simple binary threshold + invert (white text on dark bg)
            _, thresh = cv2.threshold(grey, 150, 255, cv2.THRESH_BINARY)

            result1 = pytesseract.image_to_string(
                thresh, config="--psm 7 -c tessedit_char_whitelist=0123456789:"
            ).strip()

            if re.search(r"\d{1,3}:\d{2}", result1):
                return result1

            # Try inverted threshold
            _, thresh_inv = cv2.threshold(grey, 150, 255, cv2.THRESH_BINARY_INV)
            result2 = pytesseract.image_to_string(
                thresh_inv, config="--psm 7 -c tessedit_char_whitelist=0123456789:"
            ).strip()

            if re.search(r"\d{1,3}:\d{2}", result2):
                return result2

            # Return whichever has more digits
            return result1 if sum(c.isdigit() for c in result1) >= sum(c.isdigit() for c in result2) else result2
        except Exception as e:
            self.log.warning(f"OCR timer region failed: {e}")
            return ""

    def _ocr_image(self, img: Image.Image) -> str:
        try:
            scale = self.cfg.OCR_SCALE_FACTOR
            img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
            grey = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            thresh = cv2.adaptiveThreshold(
                grey, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 11, 2,
            )
            return pytesseract.image_to_string(thresh, config="--psm 6").strip()
        except Exception as e:
            self.log.warning(f"OCR image_to_string failed: {e}")
            return ""

    def find_text_on_screen(self, target: str, region=None) -> Optional[Tuple[int, int]]:
        """
        OCR the game window, find *target* text, return its centre (x, y)
        in absolute screen coordinates.
        """
        scan_region = self._region(region)
        try:
            img = pyautogui.screenshot(region=scan_region)
            scale = self.cfg.OCR_SCALE_FACTOR
            img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
            grey = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            thresh = cv2.adaptiveThreshold(
                grey, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 11, 2,
            )
            data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)
        except Exception as e:
            self.log.warning(f"OCR image_to_data failed: {e}")
            return None

        target_lower = target.lower()

        for i, word in enumerate(data["text"]):
            if target_lower in word.lower():
                x = data["left"][i] // scale
                y = data["top"][i] // scale
                w = data["width"][i] // scale
                h = data["height"][i] // scale
                cx, cy = x + w // 2, y + h // 2
                if scan_region:
                    cx += scan_region[0]
                    cy += scan_region[1]
                return (cx, cy)
        return None

    def screen_contains_text(self, phrases: List[str], region=None) -> Optional[str]:
        """Returns first matching phrase found on screen, or None."""
        text = self.ocr_screen(region)
        if not text:
            return None
        text_lower = text.lower()
        for phrase in phrases:
            if phrase.lower() in text_lower:
                return phrase
        return None

    # ── Clicking ─────────────────────────────────────────────────────────

    def click(self, x: int, y: int, button: str = "left"):
        self.log.debug(f"Click ({x}, {y})")
        pyautogui.click(x, y, button=button)

    def press(self, key: str):
        self.log.debug(f"Press '{key}'")
        pyautogui.press(key)

    def safe_esc(self):
        """
        Press ESC, then guard against accidentally opening the in-game
        "Quit Game?" dialog. On the home screen, ESC opens a Warning dialog
        with Cancel / Confirm buttons. If we detect it (cancel_button.png),
        we click Cancel immediately. We NEVER click Confirm — that would
        quit the game.
        """
        self.log.debug("Press 'esc' (safe)")
        pyautogui.press("esc")
        time.sleep(0.5)
        # Check whether the quit-game warning appeared
        if self.find_image(self.cfg.QUIT_DIALOG_CANCEL_IMAGE, confidence=0.75):
            self.log.warning(
                "ESC opened the Quit Game dialog — clicking Cancel to back out."
            )
            self.click_image(self.cfg.QUIT_DIALOG_CANCEL_IMAGE, confidence=0.75)
            time.sleep(0.5)

    def drag(self, start_x, start_y, dx, dy, duration=0.3):
        pyautogui.moveTo(start_x, start_y)
        pyautogui.dragRel(dx, dy, duration=duration)

    # ── Window Management ────────────────────────────────────────────────

    def focus_game_window(self) -> bool:
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(self.cfg.GAME_WINDOW_TITLE)
            if windows:
                win = windows[0]
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.5)
                return True
            self.log.warning(f"Window '{self.cfg.GAME_WINDOW_TITLE}' not found.")
            return False
        except ImportError:
            return True
        except Exception as e:
            self.log.warning(f"Could not focus window: {e}")
            return False

    def get_game_window_region(self) -> Optional[Tuple[int, int, int, int]]:
        """Auto-detect game window position and size."""
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(self.cfg.GAME_WINDOW_TITLE)
            if windows:
                win = windows[0]
                region = (win.left, win.top, win.width, win.height)
                self.log.info(f"Game window region: {region}")
                return region
        except Exception as e:
            self.log.warning(f"Could not get window region: {e}")
        return None

    # ── Timer Parsing ────────────────────────────────────────────────────

    def parse_timer_text(self, text: str) -> Optional[int]:
        """Parse 'HH:MM:SS', 'MM:SS', or '3h 42m' into total seconds."""
        text = text.strip()
        # HH:MM:SS
        m = re.match(r"(\d{1,2}):(\d{2}):(\d{2})", text)
        if m:
            return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
        # MM:SS (e.g. "17:25")
        m = re.match(r"(\d{1,3}):(\d{2})$", text)
        if m:
            return int(m[1]) * 60 + int(m[2])
        # Xh Ym Zs
        total = 0
        for val, unit in re.findall(r"(\d+)\s*([hms])", text.lower()):
            v = int(val)
            total += v * (3600 if unit == "h" else 60 if unit == "m" else 1)
        return total if total > 0 else None

    def extract_timer_seconds(self, text: str) -> Optional[int]:
        """
        Robustly extract a countdown timer from noisy OCR text, handling
        the format changing as the timer counts down:
          - HH:MM:SS  when >= 1 hour remains  (e.g. "03:59:59")
          - MM:SS     when < 1 hour remains   (e.g. "17:25")

        ALWAYS tries HH:MM:SS first, so "03:59:59" is never mis-read as
        the "03:59" MM:SS substring. Searches anywhere in the string,
        so it tolerates leading/trailing junk from OCR.

        Returns total seconds, or None.
        """
        if not text:
            return None

        # Priority 1: HH:MM:SS anywhere in the text
        m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})", text)
        if m:
            h, mn, s = int(m[1]), int(m[2]), int(m[3])
            if mn < 60 and s < 60:
                return h * 3600 + mn * 60 + s

        # Priority 2: MM:SS anywhere in the text
        m = re.search(r"(\d{1,3}):(\d{2})", text)
        if m:
            mn, s = int(m[1]), int(m[2])
            if s < 60:
                return mn * 60 + s

        return None

    # ── Internal ─────────────────────────────────────────────────────────

    def _resolve_image(self, name: str) -> Optional[str]:
        if os.path.isabs(name):
            return name
        return os.path.join(self.cfg.UTILS_DIR, name)
