"""
Popup Handler
=============
Detects and dismisses sales, promotions, event popups, and stray dialogs.

SAFETY DESIGN:
  - Popups are closed ONLY by clicking a real close button (the X).
  - The diamond/purchase button is NEVER clicked — it's used only to
    DETECT that a purchase promo is on screen.
  - We never press ESC to dismiss popups, because ESC on the home screen
    opens the "Quit Game?" dialog. (The shield flow uses screen.safe_esc()
    which guards against that, but popup dismissal sticks to the X.)
"""

import logging
import time

from config import BotConfig
from modules.screen_utils import ScreenUtils


class PopupHandler:
    def __init__(self, config: BotConfig, logger: logging.Logger, screen: ScreenUtils):
        self.cfg = config
        self.log = logger
        self.screen = screen
        self._last_scan: float = 0.0

    def dismiss_all(self) -> int:
        """
        Scan for popups and close them via the X button only.
        Returns the number of popups dismissed. Rate-limited.
        """
        now = time.time()
        if now - self._last_scan < self.cfg.POPUP_SCAN_INTERVAL_SEC:
            return 0
        self._last_scan = now

        dismissed = 0

        # Strategy 1: click any known close-button (the X) — the safe action
        for img_name in self.cfg.POPUP_CLOSE_IMAGES:
            if self.screen.click_image(img_name):
                self.log.info(f"Popup closed via '{img_name}'")
                time.sleep(0.5)
                dismissed += 1

        # Strategy 2: a purchase promo (diamond) is detected but no X was
        # clicked above — try to find the X again; NEVER click the diamond.
        if dismissed == 0 and self._purchase_promo_visible():
            self.log.info("Purchase promo detected — looking for its close button.")
            for img_name in self.cfg.POPUP_CLOSE_IMAGES:
                if self.screen.click_image(img_name):
                    self.log.info(f"Purchase promo closed via '{img_name}'")
                    time.sleep(0.5)
                    dismissed += 1
                    break
            else:
                self.log.warning(
                    "Purchase promo visible but no close button found — "
                    "leaving it (will NOT click the diamond)."
                )

        # Strategy 3: OCR keyword scan (only if nothing closed yet)
        if dismissed == 0:
            for keyword in self.cfg.POPUP_CLOSE_KEYWORDS:
                pos = self.screen.find_text_on_screen(keyword)
                if pos:
                    self.log.info(f"Popup keyword '{keyword}' at {pos} — clicking.")
                    self.screen.click(*pos)
                    time.sleep(0.5)
                    dismissed += 1
                    break  # one per cycle to avoid mis-clicks

        if dismissed:
            self.log.info(f"Dismissed {dismissed} popup(s) this cycle.")
        return dismissed

    def is_popup_visible(self) -> bool:
        """Quick check: is a close button OR a detect-image on screen?"""
        for img_name in self.cfg.POPUP_CLOSE_IMAGES:
            if self.screen.find_image(img_name):
                return True
        return self._purchase_promo_visible()

    def _purchase_promo_visible(self) -> bool:
        """True if a purchase/diamond promo is detected (detection only)."""
        for img_name in self.cfg.POPUP_DETECT_IMAGES:
            if self.screen.find_image(img_name):
                return True
        return False
