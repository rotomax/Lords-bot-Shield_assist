"""
Shield Manager
==============
Activates the shield and tracks its countdown timer.

Startup flow:
  1. Click turfBoost icon (image detection -> fallback coordinates)
  2. Find "Expires In" text -> OCR the timer region to the right of it
  3. If timer found -> sync internal timer, close panel
  4. If no timer -> activate new shield (4hr or 8hr per config)
  5. Verify shield timer on same page, update internal timer

Main-loop flow:
  - Each tick checks internal timer
  - When < SHIELD_EARLY_REFRESH_MIN minutes remain -> re-activate
"""

import logging
import re
import time
from typing import Optional, Tuple

from config import BotConfig
from modules.screen_utils import ScreenUtils
from modules.timer_tracker import TimerTracker

TIMER_NAME = "shield"


class ShieldManager:
    def __init__(
        self,
        config: BotConfig,
        logger: logging.Logger,
        screen: ScreenUtils,
        timer: TimerTracker,
    ):
        self.cfg = config
        self.log = logger
        self.screen = screen
        self.timer = timer
        # Counter of consecutive activate_shield() failures.
        # main.py monitors this and triggers a game relaunch when it
        # reaches SHIELD_FAIL_RECOVERY_THRESHOLD, recovering from UI-stuck
        # states (e.g. a Reports window blocking clicks).
        self.consecutive_failures: int = 0

    # ══════════════════════════════════════════════════════════════════════
    #  PUBLIC API
    # ══════════════════════════════════════════════════════════════════════

    def initialise(self):
        """
        Called once at startup after popups are cleared and we're on home screen.
        Opens the boost panel, reads the shield timer, decides what to do.
        """
        self.log.info("Shield Manager: initialising …")

        # Step 1: Open the turf boost panel
        if not self._open_turf_boost_panel():
            self.log.error("Could not open turf boost panel — cannot check shield.")
            return

        time.sleep(1.5)  # wait for panel to fully render

        # Save debug screenshot so we can see what the bot sees
        self.screen.save_debug_screenshot("debug_boost_panel.png")

        # Step 2: Read the shield timer
        remaining_sec = self._read_shield_timer()

        if remaining_sec and remaining_sec > self.cfg.SHIELD_EARLY_REFRESH_MIN * 60:
            self.log.info(
                f"Shield already active — {remaining_sec / 60:.1f} min remaining."
            )
            self.timer.sync_from_ocr(TIMER_NAME, remaining_sec)
            self.screen.safe_esc()
            time.sleep(0.5)
            return

        if remaining_sec:
            self.log.info(
                f"Shield has only {remaining_sec / 60:.1f} min left — refreshing."
            )
        else:
            self.log.info("No active shield detected.")

        # Close panel before activating (clean state)
        self.screen.safe_esc()
        time.sleep(0.5)

        # Step 3: Activate a new shield
        self.activate_shield()

    def tick(self):
        """Called every main-loop cycle. Refreshes shield if timer is low."""
        remaining = self.timer.remaining_minutes(TIMER_NAME)

        if remaining <= self.cfg.SHIELD_EARLY_REFRESH_MIN:
            self.log.info(
                f"Shield has {remaining:.1f} min left "
                f"(threshold {self.cfg.SHIELD_EARLY_REFRESH_MIN} min) — refreshing."
            )
            self.activate_shield()
        else:
            self.log.debug(f"Shield OK — {remaining:.1f} min remaining.")

    def activate_shield(self) -> bool:
        """
        Public entry point. Wraps the activation flow with consecutive-
        failure bookkeeping so main.py can trigger a game relaunch when
        the UI gets stuck (e.g. a Reports/mail window blocking clicks).
        Every successful activation resets the counter to zero.
        """
        success = self._activate_shield_impl()
        if success:
            if self.consecutive_failures > 0:
                self.log.info(
                    f"Shield activation recovered after "
                    f"{self.consecutive_failures} consecutive failure(s) — "
                    "resetting counter."
                )
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            self.log.warning(
                f"Shield activation failed (consecutive failures: "
                f"{self.consecutive_failures})."
            )
        return success

    def _activate_shield_impl(self) -> bool:
        """
        Full shield activation flow:
          1. Open turf boost panel
          2. Find & click shield menu item (scrolls to find it)
          3. Click "Use" aligned with the correct hour row
          4. Click OK to confirm
          5. Read the new shield timer to verify
          6. Close panel and start internal countdown
        """
        hours = self.cfg.SHIELD_DURATION_HOURS
        self.log.info(f"Activating {hours}hr shield …")

        # Step 1: Open turf boost panel
        if not self._open_turf_boost_panel():
            self.log.error("Cannot find turfBoost icon — shield activation failed.")
            return False
        time.sleep(1.5)

        # Step 1b: GUARD — re-read the timer now that the panel is open.
        # If a healthy shield is already active, skip application entirely.
        # This prevents double-applying when a previous attempt succeeded
        # but its OK-confirmation check timed out.
        existing = self._read_shield_timer()
        if existing and existing > self.cfg.SHIELD_EARLY_REFRESH_MIN * 60:
            self.log.info(
                f"Shield already active ({existing / 60:.1f} min) — "
                "skipping application to avoid double-shielding."
            )
            self.timer.sync_from_ocr(TIMER_NAME, existing)
            self.screen.safe_esc()
            time.sleep(0.5)
            return True

        # Step 2: Find shield menu item (may need to scroll)
        if not self._find_and_click_shield_menu():
            self.log.error("Cannot find shield menu item — closing panel.")
            self.screen.safe_esc()
            return False
        time.sleep(1.0)

        # Step 3: Click "Use" for the correct duration
        if not self._click_use_for_duration():
            self.log.error("Cannot click Use button — closing panel.")
            self.screen.safe_esc()
            return False
        time.sleep(1.5)  # wait for the OK confirmation dialog to appear

        # Step 4: Confirm with OK (generous retry window — OK can be slow)
        ok_clicked = self.screen.click_image(
            self.cfg.SHIELD_OK_IMAGE, retries=6, retry_delay=0.6
        )
        if not ok_clicked:
            # OK wasn't found — but the shield may STILL have been applied.
            # Verify by reading the timer before deciding it failed.
            self.log.warning("OK button not found — verifying shield state via timer …")
            time.sleep(1.5)
            verify = self._read_shield_timer()
            if verify and verify > self.cfg.SHIELD_EARLY_REFRESH_MIN * 60:
                # Shield IS active — treat as success, set timer, don't re-apply
                self.timer.sync_from_ocr(TIMER_NAME, verify)
                self.log.info(
                    f"Shield confirmed active via timer ({verify / 60:.1f} min) — "
                    "no OK click needed."
                )
                self.screen.safe_esc()
                time.sleep(0.5)
                return True
            self.log.error("Could not confirm shield — closing panel.")
            self.screen.safe_esc()
            return False
        time.sleep(1.5)

        # Step 5: Read the new shield timer to confirm it worked
        new_remaining = self._read_shield_timer()
        if new_remaining:
            self.timer.sync_from_ocr(TIMER_NAME, new_remaining)
            self.log.info(
                f"Shield activated — timer confirmed: {new_remaining / 60:.1f} min."
            )
        else:
            # Timer wasn't readable, but shield likely activated — use config duration
            duration_sec = hours * 3600
            self.timer.set_timer(
                TIMER_NAME, duration_sec,
                notes=f"{hours}hr shield (timer not verified via OCR)"
            )
            self.log.warning(
                "Shield likely activated but could not read timer — "
                f"using {hours}hr estimate."
            )

        # Step 6: Close panel
        self.screen.safe_esc()
        time.sleep(0.5)
        return True

    def needs_refresh(self) -> bool:
        return self.timer.remaining_minutes(TIMER_NAME) <= self.cfg.SHIELD_EARLY_REFRESH_MIN

    # ══════════════════════════════════════════════════════════════════════
    #  PRIVATE: Opening the Turf Boost Panel
    # ══════════════════════════════════════════════════════════════════════

    def _open_turf_boost_panel(self) -> bool:
        """
        Click the turfBoost icon to open the boost panel.
        Tries image detection first, then falls back to fixed coordinates.
        """
        self.screen.focus_game_window()
        time.sleep(0.3)

        # Strategy 1: Image detection (tries all turfBoost variants)
        result = self.screen.find_any_image(
            self.cfg.SHIELD_TURF_BOOST_IMAGES,
            confidence=0.70,
        )
        if result:
            name, x, y = result
            self.log.info(f"TurfBoost icon found via '{name}' at ({x}, {y})")
            self.screen.click(x, y)
            return True

        # Strategy 2: Fallback to fixed coordinates
        fallback = self.cfg.TURF_BOOST_FALLBACK_POS
        if fallback:
            self.log.warning(
                f"TurfBoost not found via image — using fallback coords {fallback}"
            )
            self.screen.click(*fallback)
            time.sleep(1.0)
            return True

        # Strategy 3: OCR search for "Boost" text
        pos = self.screen.find_text_on_screen("Boost")
        if pos:
            self.log.info(f"TurfBoost found via OCR at {pos}")
            self.screen.click(*pos)
            return True

        self.log.error("TurfBoost icon not found by any method.")
        return False

    # ══════════════════════════════════════════════════════════════════════
    #  PRIVATE: Shield Menu Navigation
    # ══════════════════════════════════════════════════════════════════════

    def _find_and_click_shield_menu(self) -> bool:
        """
        Open the shield duration dialog by clicking the ">" arrow on the
        Shield row. The boost panel opens in a fixed position, so we click
        the known arrow coordinates directly (most reliable). Falls back to
        template/OCR if the fixed position is somehow wrong.
        """
        # Primary: click the fixed arrow position
        arrow_pos = self.cfg.SHIELD_ROW_ARROW_POS
        if arrow_pos:
            self.log.info(f"Clicking Shield row arrow at {arrow_pos}")
            self.screen.click(*arrow_pos)
            time.sleep(1.0)
            # Verify the duration dialog opened by checking for the "Use" button
            if self.screen.find_image(self.cfg.SHIELD_USE_IMAGE):
                self.log.info("Shield duration dialog opened.")
                return True
            self.log.debug("Use button not visible after arrow click — trying fallbacks.")

        # Fallback 1: template match
        if self.screen.click_image(self.cfg.SHIELD_MENU_IMAGE):
            self.log.info("Shield menu item found via template.")
            time.sleep(1.0)
            return True

        # Fallback 2: OCR — find "Shield" text, click arrow at that Y
        shield_pos = self.screen.find_text_on_screen("Shield")
        if shield_pos and arrow_pos:
            sx, sy = shield_pos
            self.log.info(f"Found 'Shield' text at ({sx}, {sy}) — clicking arrow at x={arrow_pos[0]}")
            self.screen.click(arrow_pos[0], sy)
            time.sleep(1.0)
            if self.screen.find_image(self.cfg.SHIELD_USE_IMAGE):
                return True

        # Failed — save debug screenshot
        self.screen.save_debug_screenshot("debug_shield_menu_fail.png")
        self.log.warning("Shield menu item not found — saved debug_shield_menu_fail.png")
        return False

    def _click_use_for_duration(self) -> bool:
        """
        Find the hour-duration label and the "Use" button, then click
        "Use" at the Y-coordinate of the correct hour row.
        """
        hour_img = self.cfg.SHIELD_HOUR_IMAGE
        use_img = self.cfg.SHIELD_USE_IMAGE

        hour_pos = self.screen.find_image(hour_img)
        use_pos = self.screen.find_image(use_img)

        if hour_pos and use_pos:
            self.screen.click(use_pos[0], hour_pos[1])
            self.log.info(f"Clicked Use at ({use_pos[0]}, {hour_pos[1]})")
            return True

        if use_pos:
            self.log.warning("Hour image not found — clicking Use directly.")
            self.screen.click(*use_pos)
            return True

        self.log.warning("Neither hour label nor Use button found.")
        return False

    # ══════════════════════════════════════════════════════════════════════
    #  PRIVATE: Reading Shield Timer via OCR
    # ══════════════════════════════════════════════════════════════════════

    def _read_shield_timer(self) -> Optional[int]:
        """
        Smart timer reading:
          1. Find "Expires" text on screen -> gives us the Y position
          2. OCR a small region to the RIGHT of "Expires" where the
             timer (e.g. "08:33:34") sits in its dark box
          3. Parse the HH:MM:SS from that small, clean OCR region
          4. Fallback: try SHIELD_TIMER_REGION from config
          5. Last resort: OCR the full game window (noisy)

        Returns remaining seconds, or None if not found.
        """
        # ── Method 1: Find "Expires" -> targeted OCR to the right ─────
        expires_pos = self.screen.find_text_on_screen("Expires")
        if not expires_pos:
            # Also try "Expire" in case OCR misreads slightly
            expires_pos = self.screen.find_text_on_screen("Expire")

        if expires_pos:
            ex, ey = expires_pos
            self.log.info(f"Found 'Expires' text at ({ex}, {ey})")

            # The timer is to the RIGHT of "Expires In", same Y level.
            # OCR a box: start a bit right of "Expires", same height,
            # wide enough to capture "HH:MM:SS"
            timer_region = (
                ex + 100,       # start 100px right of "Expires" center
                ey - 25,        # 25px above to capture full text height
                350,            # 350px wide — enough for "08:33:34"
                50,             # 50px tall
            )
            self.log.debug(f"Timer OCR region: {timer_region}")
            self.screen.save_debug_screenshot("debug_timer_region.png", region=timer_region)
            timer_text = self.screen.ocr_timer_region(timer_region)
            self.log.info(f"Timer region OCR result: '{timer_text}'")

            secs = self.screen.extract_timer_seconds(timer_text)
            if secs:
                self.log.info(
                    f"Shield timer: {secs // 3600}h "
                    f"{(secs % 3600) // 60}m {secs % 60}s"
                )
                return secs

        # ── Method 2: Use fixed region from config ────────────────────
        fixed_region = self.cfg.SHIELD_TIMER_REGION
        if fixed_region:
            self.log.debug(f"Trying fixed timer region: {fixed_region}")
            self.screen.save_debug_screenshot("debug_fixed_timer_region.png", region=fixed_region)
            timer_text = self.screen.ocr_timer_region(fixed_region)
            self.log.info(f"Fixed region OCR result: '{timer_text}'")

            secs = self.screen.extract_timer_seconds(timer_text)
            if secs:
                self.log.info(
                    f"Shield timer (fixed region): {secs // 3600}h "
                    f"{(secs % 3600) // 60}m {secs % 60}s"
                )
                return secs

        # ── Method 3: Full game window OCR (last resort, noisy) ───────
        self.log.debug("Trying full-screen OCR as last resort …")
        text = self.screen.ocr_screen()

        # Look for "shield" or "expires" near a timer pattern
        lines = text.split("\n")
        for i, line in enumerate(lines):
            lower = line.lower()
            if any(kw in lower for kw in ["shield", "expires", "barrier"]):
                for j in range(i, min(i + 3, len(lines))):
                    secs = self.screen.extract_timer_seconds(lines[j])
                    if secs and secs > 60:  # ignore tiny values (noise)
                        self.log.info(
                            f"Shield timer (full OCR): {secs // 3600}h "
                            f"{(secs % 3600) // 60}m {secs % 60}s"
                        )
                        return secs

        self.log.warning("No shield timer found by any method.")
        return None
