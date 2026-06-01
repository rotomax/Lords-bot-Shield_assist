"""
LordsBot (Shareable Build) — Configuration
===========================================
All tuneable settings live here on a single BotConfig dataclass.
No magic numbers in module code.

If you're a tester, the values you most likely need to edit are:
  - GAME_EXE_PATH        (the path to Lords Mobile PC.exe on your machine)
  - SHIELD_DURATION_HOURS / SHIELD_HOUR_IMAGE (4hr or 8hr shield)
  - TESSERACT_CMD        (where Tesseract OCR is installed)

If clicks land in the wrong place, see calibrate.py and the README's
calibration section. This build is intended for 1920x1080 displays.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


_BASE = os.path.dirname(os.path.abspath(__file__))


@dataclass
class BotConfig:
    # ── General ──────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    POLL_INTERVAL_SEC: float = 60.0              # fallback poll between cycles
    GAME_ALIVE_CHECK_INTERVAL_SEC: float = 600.0  # check game/disconnect every 10 min during sleep
    BASE_DIR: str = _BASE

    # Global hotkey to stop the bot from anywhere (no need to switch focus).
    # Works even while the game is focused. Set to None to disable.
    # Examples: "f9", "ctrl+shift+q", "esc" (avoid keys the game uses).
    STOP_HOTKEY: Optional[str] = "ctrl+shift+q"

    # ── Game / Emulator ──────────────────────────────────────────────────
    # CHANGE THIS to the path of your Lords Mobile PC installation.
    GAME_EXE_PATH: str = (
        r"C:\Users\your_user_name\AppData\Roaming\IGG\Lords Mobile PC"
        r"\Lords Mobile Updater.exe"
    )
    GAME_PROCESS_NAME: str = "Lords Mobile PC.exe"
    GAME_WINDOW_TITLE: str = "Lords Mobile PC"
    GAME_STARTUP_WAIT_SEC: int = 40
    GAME_CLOSE_WAIT_SEC: int = 5            # wait after closing game before relaunch

    # ── Paths ────────────────────────────────────────────────────────────
    UTILS_DIR: str = os.path.join(_BASE, "utils")

    # ── Tesseract ────────────────────────────────────────────────────────
    # CHANGE THIS if you installed Tesseract somewhere else.
    # Standard Windows install location is shown.
    TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    OCR_SCALE_FACTOR: int = 2

    # ── Screen Regions (1920x1080 required) ──────────────────────────────
    # (left, top, width, height) — set to None for full screen.
    # At startup the bot auto-detects the real game-window position and
    # overrides this value, so it's mainly a sensible default.
    SCREENSHOT_REGION: Optional[Tuple[int, int, int, int]] = (152, 70, 1616, 939)

    # ── Confidence Thresholds ────────────────────────────────────────────
    DEFAULT_CONFIDENCE: float = 0.80

    # ── Shield ───────────────────────────────────────────────────────────
    SHIELD_DURATION_HOURS: int = 4           # 4 or 8 — pick your shield
    SHIELD_INTERVAL_SEC: int = 4 * 3600
    SHIELD_EARLY_REFRESH_MIN: int = 5        # re-shield when < N minutes left
    SHIELD_TURF_BOOST_IMAGES: List[str] = field(default_factory=lambda: [
        "turfBoost0.png",
    ])
    SHIELD_MENU_IMAGE: str = "shield1.png"
    SHIELD_HOUR_IMAGE: str = "shield4h.png"
    SHIELD_USE_IMAGE: str = "use.png"
    SHIELD_OK_IMAGE: str = "ok.png"

    # Position (absolute screen x, y) of the ">" arrow on the Shield row
    # that opens the duration-selection dialog. The boost panel always opens
    # in the same place, so a fixed position is reliable.
    SHIELD_ROW_ARROW_POS: Tuple[int, int] = (1460, 585)

    # Fallback coordinates for turfBoost icon if image detection fails.
    # Set this by hovering over the icon and running calibrate.py.
    # Format: (x, y) or None to disable fallback.
    TURF_BOOST_FALLBACK_POS = (1702, 457)

    # Fixed region for the shield timer text (x, y, width, height).
    # Only used if "Expires" text detection fails.
    # Set to None to skip; calibrate by hovering over the timer corners.
    SHIELD_TIMER_REGION: Optional[Tuple[int, int, int, int]] = (1027, 592, 225, 29)

    # Recovery threshold for stuck shield activation.
    # If activate_shield() fails this many cycles in a row, main.py forces
    # a game close+relaunch (same path as a disconnect). Protects against
    # UI-stuck states like a blocking Reports/mail window absorbing clicks.
    # Each failed cycle takes ~15s; relaunch takes ~70-90s. With shield
    # threshold = 5 min, keep this at 5 or lower to leave a safe margin.
    # Set to 0 to disable.
    SHIELD_FAIL_RECOVERY_THRESHOLD: int = 5

    # ── Session / "Another Device" / Disconnect ──────────────────────────
    SESSION_KICK_IMAGE: Optional[str] = None    # optional 2nd disconnect template
    # The "Disconnected..." dialog has a single "Close" button (and a red X).
    # Detection is OpenCV-only via this template. We detect it, click Close,
    # then close the game process so the relaunch flow starts fresh.
    DISCONNECT_CLOSE_IMAGE: str = "close_button.png"   # blue "Close" button
    RELOGIN_WAIT_SEC: int = 15

    # Disconnect recovery delay (minutes).
    # When a disconnect is detected (you logged in elsewhere, e.g. your
    # phone), the bot WAITS this long before closing/relaunching the game,
    # so you can play on your phone without the bot fighting you for the
    # session. EXCEPTION: if the shield drops below SHIELD_EARLY_REFRESH_MIN
    # during the wait, the bot recovers immediately to protect the shield.
    # Set to 0 to disable the delay (recover instantly).
    DISCONNECT_RECOVERY_DELAY_MIN: float = 30.0

    # ── Popup Dismissal ──────────────────────────────────────────────────
    # IMPORTANT: only true CLOSE buttons go here. NEVER put the diamond
    # (purchase) button here — clicking it could spend diamonds.
    POPUP_CLOSE_IMAGES: List[str] = field(default_factory=lambda: [
        "cross_button1.png",
    ])
    # Images that merely DETECT a popup is present (used to decide we should
    # close it). The diamond promo is detected here but closed via the X.
    POPUP_DETECT_IMAGES: List[str] = field(default_factory=lambda: [
        "diamond.png",
    ])
    POPUP_SCAN_INTERVAL_SEC: float = 3.0
    POPUP_CLOSE_KEYWORDS: List[str] = field(default_factory=lambda: [
        "special",
    ])

    # ── Quit-Game Dialog Safety ──────────────────────────────────────────
    # The "Quit Game?" Warning dialog that ESC opens on the home screen.
    # safe_esc() clicks Cancel if this appears. NEVER click Confirm.
    QUIT_DIALOG_CANCEL_IMAGE: str = "cancel_button.png"

    # ── Page Detection ───────────────────────────────────────────────────
    PAGE_IMAGES: dict = field(default_factory=lambda: {
        "home":        "map.png",
        "kingdom_map": "return_castle.png",
        "kvk_map":     "kvk_map.png",
    })
    EXIT_CONFIRM_IMAGE: str = "cancel_button.png"

    # ── Helper ───────────────────────────────────────────────────────────
    def img(self, filename: str) -> str:
        """Full path to a utils/ image."""
        return os.path.join(self.UTILS_DIR, filename)
