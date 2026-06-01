"""
Session Monitor / Disconnect Handler
====================================
Detects the "Disconnected... This account is logged in on another device"
dialog and recovers from it.

The disconnect dialog has:
  - A title "Disconnected..."
  - Body text "This account is logged in on another device."
  - A single blue "Close" button (centre of screen)
  - A red X in the top-right corner

DETECTION (OpenCV only):
  Detection is done purely by OpenCV template matching against
  close_button.png — fast (milliseconds), reliable, and no Tesseract
  dependency. The Close button always appears in the centre of the screen,
  inside SCREENSHOT_REGION, so we use the normal region (no full-window
  screenshot needed). An optional second template (SESSION_KICK_IMAGE) can
  be supplied for redundancy.

RECOVERY STRATEGY:
  When this dialog appears, the game session is dead — clicking Close just
  dismisses the dialog and leaves a non-functional game. The only reliable
  recovery is to fully close the game process and relaunch it (which the
  main controller's relaunch flow handles).

  So this module:
    1. Detects the disconnect dialog (OpenCV template match, every cycle)
    2. Clicks Close (then X as fallback) to dismiss it
    3. Closes the game process so the main loop's relaunch logic takes over
"""

import logging
import time
from typing import Optional

from config import BotConfig
from modules.screen_utils import ScreenUtils


class SessionMonitor:
    def __init__(
        self,
        config: BotConfig,
        logger: logging.Logger,
        screen: ScreenUtils,
        shield_mgr,
    ):
        self.cfg = config
        self.log = logger
        self.screen = screen
        self.shield_mgr = shield_mgr
        # Timestamp (time.time()) when the current disconnect was first seen.
        # None means "no disconnect currently being tracked".
        self._disconnect_first_seen: Optional[float] = None

    # ── Public API ───────────────────────────────────────────────────────

    def check(self, immediate: bool = False) -> bool:
        """
        Returns True if a disconnect was detected AND handled (game closed).
        When True, the caller should `continue` its loop — the game has
        been closed and will be relaunched on the next cycle.

        Returns False if there is no disconnect, OR if a disconnect is
        present but we are still inside the grace-delay window (giving the
        user time to play on their phone). In the latter case the game is
        left untouched.

        If *immediate* is True, the grace delay is bypassed and recovery
        happens right away (used at startup, where the user is clearly at
        the computer and wants the disconnect handled now).
        """
        if not self._is_disconnected():
            # No disconnect on screen — clear any tracking and carry on.
            if self._disconnect_first_seen is not None:
                self.log.info(
                    "Disconnect dialog gone — resetting recovery delay timer."
                )
                self._disconnect_first_seen = None
            return False

        # A disconnect dialog IS present.
        now = time.time()
        delay_sec = self.cfg.DISCONNECT_RECOVERY_DELAY_MIN * 60

        # First time we've seen this disconnect -> start the grace timer.
        if self._disconnect_first_seen is None:
            self._disconnect_first_seen = now
            self.log.warning("=" * 50)
            self.log.warning("  DISCONNECTED — account logged in on another device.")
            self.log.warning("=" * 50)
            if delay_sec > 0 and not immediate:
                self.log.info(
                    f"Holding off recovery for up to "
                    f"{self.cfg.DISCONNECT_RECOVERY_DELAY_MIN:.0f} min "
                    f"(so you can play elsewhere). Will recover sooner if the "
                    f"shield drops below {self.cfg.SHIELD_EARLY_REFRESH_MIN} min."
                )

        elapsed = now - self._disconnect_first_seen
        shield_remaining_min = self.shield_mgr.timer.remaining_minutes("shield")

        # Decide whether to recover now.
        delay_elapsed = elapsed >= delay_sec
        shield_critical = shield_remaining_min <= self.cfg.SHIELD_EARLY_REFRESH_MIN

        if not immediate and not (delay_elapsed or shield_critical):
            # Still in the grace window and shield is safe — leave the game be.
            remaining_wait = (delay_sec - elapsed) / 60.0
            self.log.info(
                f"Disconnect active — waiting {remaining_wait:.1f} more min before "
                f"recovery (shield has {shield_remaining_min:.1f} min left)."
            )
            return False

        # Time to recover.
        if immediate:
            self.log.info("Recovering from disconnect immediately (startup).")
        elif shield_critical and not delay_elapsed:
            self.log.warning(
                f"Shield critical ({shield_remaining_min:.1f} min) — "
                "recovering now despite grace delay."
            )
        else:
            self.log.info(
                f"Grace delay elapsed ({elapsed / 60:.1f} min) — recovering now."
            )

        # Reset tracking before we act.
        self._disconnect_first_seen = None

        # Step 1: Dismiss the dialog (click Close, then X as fallback)
        self._dismiss_disconnect_dialog()

        # Step 2: The session is dead — closing the dialog alone won't
        # reconnect. Close the game process so the main loop relaunches it.
        self._close_game_process()

        # Give Windows time to fully tear down the process before the
        # relaunch flow tries to start it again.
        self.log.info(
            f"Waiting {self.cfg.GAME_CLOSE_WAIT_SEC}s for game to fully close …"
        )
        time.sleep(self.cfg.GAME_CLOSE_WAIT_SEC)

        # The shield timer is now stale — cancel it so the relaunch flow
        # re-reads the true shield state from a fresh game session.
        self.shield_mgr.timer.cancel("shield")

        self.log.info("Disconnect handled — game closed, will relaunch next cycle.")
        return True

    # ── Detection (OpenCV only) ──────────────────────────────────────────

    def _is_disconnected(self) -> bool:
        """
        Pure OpenCV template detection — no OCR.
        Matches close_button.png (always centre-screen, inside the normal
        SCREENSHOT_REGION). Optionally also matches SESSION_KICK_IMAGE for
        redundancy if the user supplied a second template.
        """
        # Primary: the blue "Close" button on the disconnect dialog
        if self.screen.find_image(
            self.cfg.DISCONNECT_CLOSE_IMAGE, confidence=0.75
        ):
            self.log.debug("Disconnect detected via Close-button template.")
            return True

        # Optional redundancy: a second template (e.g. dialog title or X)
        if self.cfg.SESSION_KICK_IMAGE:
            if self.screen.find_image(
                self.cfg.SESSION_KICK_IMAGE, confidence=0.70
            ):
                self.log.debug("Disconnect detected via kick-dialog template.")
                return True

        return False

    # ── Dialog Dismissal ─────────────────────────────────────────────────

    def _dismiss_disconnect_dialog(self):
        """Click the Close button, falling back to the red X."""
        # Try the blue "Close" button first
        if self.screen.click_image(self.cfg.DISCONNECT_CLOSE_IMAGE, confidence=0.75):
            self.log.info("Clicked 'Close' on disconnect dialog.")
            time.sleep(1.0)
            return

        # Fallback: the red X (top-right of the dialog)
        if self.screen.click_image("cross_button1.png", confidence=0.70):
            self.log.info("Clicked X on disconnect dialog.")
            time.sleep(1.0)
            return

        self.log.warning(
            "Could not find Close/X on disconnect dialog — "
            "closing game process anyway."
        )

    # ── Game Process Control ─────────────────────────────────────────────

    def _close_game_process(self):
        """
        Forcefully close the game process so the main loop's relaunch
        logic starts a fresh session. Uses psutil if available, else
        falls back to the Windows taskkill command.
        """
        process_name = self.cfg.GAME_PROCESS_NAME
        self.log.info(f"Closing game process '{process_name}' …")

        # Method 1: psutil
        try:
            import psutil
            killed = False
            for proc in psutil.process_iter(attrs=["name", "pid"]):
                name = proc.info.get("name") or ""
                if process_name.lower() in name.lower():
                    try:
                        proc.terminate()
                        killed = True
                        self.log.info(f"Terminated PID {proc.info['pid']} ({name}).")
                    except Exception as e:
                        self.log.warning(f"Could not terminate {name}: {e}")
            if killed:
                # Give processes a moment, then force-kill any survivors
                time.sleep(3)
                for proc in psutil.process_iter(attrs=["name"]):
                    name = proc.info.get("name") or ""
                    if process_name.lower() in name.lower():
                        try:
                            proc.kill()
                        except Exception:
                            pass
                return
        except ImportError:
            pass
        except Exception as e:
            self.log.warning(f"psutil terminate failed: {e}")

        # Method 2: taskkill
        try:
            import subprocess
            subprocess.run(
                ["taskkill", "/F", "/IM", process_name],
                capture_output=True, text=True, timeout=15,
            )
            self.log.info(f"taskkill issued for '{process_name}'.")
            time.sleep(2)
        except Exception as e:
            self.log.warning(f"taskkill failed: {e}")

    # ── Legacy compatibility ─────────────────────────────────────────────

    def force_relogin(self):
        """Kept for compatibility — closes the game so it relaunches."""
        self._close_game_process()
        self.shield_mgr.timer.cancel("shield")
