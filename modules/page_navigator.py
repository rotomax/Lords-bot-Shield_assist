"""
Page Navigator
==============
Detects which game screen is active and can escape back to a known page.
"""

import logging
import time
from typing import Optional

from config import BotConfig
from modules.screen_utils import ScreenUtils


class PageNavigator:
    def __init__(self, config: BotConfig, logger: logging.Logger, screen: ScreenUtils):
        self.cfg = config
        self.log = logger
        self.screen = screen

    def get_current_page(self) -> Optional[str]:
        """Returns 'home', 'kingdom_map', 'kvk_map', or None."""
        for page_name, image_file in self.cfg.PAGE_IMAGES.items():
            pos = self.screen.find_image(image_file)
            if pos:
                self.log.debug(f"Current page: {page_name}")
                return page_name
        self.log.debug("Current page: unknown")
        return None

    def escape_to_known_page(self, max_attempts: int = 20) -> Optional[str]:
        """Press ESC until exit-confirm dialog appears, click Cancel, re-detect."""
        self.log.info("Escaping to known page state…")
        for _ in range(max_attempts):
            self.screen.press("esc")
            time.sleep(0.5)

            if self.screen.click_image(self.cfg.EXIT_CONFIRM_IMAGE):
                self.log.info("Clicked cancel → should be on known page now.")
                time.sleep(1)
                return self.get_current_page()

        self.log.warning("Could not escape to a known page.")
        return None

    def ensure_page(self, target: str = "home") -> bool:
        """
        Make sure we're on *target* page. Returns True if we got there.
        """
        page = self.get_current_page()
        if page == target:
            return True

        if page is None:
            page = self.escape_to_known_page()

        if page == target:
            return True

        # Navigate home → kingdom_map or vice versa
        if target == "kingdom_map" and page == "home":
            if self.screen.click_image(self.cfg.PAGE_IMAGES["home"]):
                time.sleep(1.5)
                return self.get_current_page() == "kingdom_map"

        if target == "home" and page == "kingdom_map":
            if self.screen.click_image(self.cfg.PAGE_IMAGES["kingdom_map"]):
                time.sleep(1.5)
                return self.get_current_page() == "home"

        self.log.warning(f"Could not navigate to '{target}' (currently on '{page}').")
        return False
