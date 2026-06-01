"""
LordsBot (Shareable Build) — Main Controller
=============================================
Single entry point. Orchestrates all modules in a priority-ordered loop.

This is a community / tester build focused on a single job: keeping a
turf shield active. It contains only the shield, popup, page-navigation,
and disconnect-recovery modules. There is no notification system, no
treasure/gift collection, and no dry-run mode.

Startup flow:
  0. Check if game is running — launch it if not
  1. Focus game window + auto-detect region
  2. Dismiss popups (two passes with 5s wait between)
  3. Navigate to home screen
  4. Open turf boost -> check shield timer -> activate if needed

Main loop:
  - Run a full cycle (game check, session, shield, popups)
  - Calculate exactly how long until shield has SHIELD_EARLY_REFRESH_MIN left
  - Sleep for that duration in 10-min chunks (process check + disconnect
    check on each wake — no OCR, no template scans during sleep)
  - Wake up and repeat

Usage:
    python main.py                          # normal run
    python main.py --shield-hours 8         # use 8hr shields instead of 4hr
    python main.py --log-level DEBUG        # verbose
"""

import argparse
import datetime
import logging
import os
import signal
import subprocess
import sys
import time

from config import BotConfig
from modules.screen_utils import ScreenUtils
from modules.timer_tracker import TimerTracker
from modules.page_navigator import PageNavigator
from modules.shield_manager import ShieldManager
from modules.popup_handler import PopupHandler
from modules.session_monitor import SessionMonitor


# ── Logging ──────────────────────────────────────────────────────────────────

def setup_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("LordsBot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(module)-18s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler("bot.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


# ── Main Bot ─────────────────────────────────────────────────────────────────

class LordsBot:
    def __init__(self, config: BotConfig, logger: logging.Logger):
        self.cfg = config
        self.log = logger
        self.running = False

        # Shared services
        self.screen = ScreenUtils(config, logger)
        self.timer = TimerTracker(logger)
        self.page_nav = PageNavigator(config, logger, self.screen)

        # Task modules
        self.shield = ShieldManager(config, logger, self.screen, self.timer)
        self.popups = PopupHandler(config, logger, self.screen)
        self.session = SessionMonitor(config, logger, self.screen, self.shield)

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self):
        self.running = True
        self.log.info("=" * 60)
        self.log.info("  LordsBot (Shareable Build) — Starting Up")
        self.log.info("=" * 60)
        self.log.info(f"  Shield     : {self.cfg.SHIELD_DURATION_HOURS}hr "
                      f"(refresh at <{self.cfg.SHIELD_EARLY_REFRESH_MIN} min)")
        self.log.info(f"  Game check : every "
                      f"{self.cfg.GAME_ALIVE_CHECK_INTERVAL_SEC / 60:.0f} min during sleep")
        self.log.info("=" * 60)

        self._setup_hotkey()
        self._startup_sequence()
        self._main_loop()

    def stop(self, signum=None, frame=None):
        self.log.info("Shutdown signal received.")
        self.running = False

    def _setup_hotkey(self):
        hotkey = self.cfg.STOP_HOTKEY
        if not hotkey:
            return
        try:
            import keyboard
            keyboard.add_hotkey(hotkey, self._hotkey_stop)
            self.log.info(
                f"Press '{hotkey}' anytime to stop the bot (works in any window)."
            )
        except ImportError:
            self.log.info(
                "Global stop-hotkey unavailable — pip install keyboard to enable. "
                "Using Ctrl+C instead."
            )
        except Exception as e:
            self.log.warning(f"Could not register stop-hotkey: {e}")

    def _hotkey_stop(self):
        self.log.info(f"Stop-hotkey '{self.cfg.STOP_HOTKEY}' pressed — stopping bot.")
        self.running = False

    # ── Startup ──────────────────────────────────────────────────────────

    def _startup_sequence(self):
        """Full startup: launch game if needed, then init all modules."""
        self.log.info("── Startup Sequence ──")

        # Step 0a: If the game is already running but showing a disconnect
        # dialog, handle it first. The session handler closes the game so
        # the launch step below starts a clean, fresh session.
        if self._is_game_process_running():
            self.log.info("Step 0a: Checking for disconnect dialog …")
            self.screen.focus_game_window()
            time.sleep(1)
            if self.session.check(immediate=True):
                self.log.info(
                    "Disconnect handled at startup — game closed, will relaunch."
                )
            else:
                self.log.info("No disconnect dialog detected.")

        # Step 0b: Launch the game if it is not running (or was just closed)
        self.log.info("Step 0b: Checking if game is running …")
        self._ensure_game_running()
        self._post_launch_sequence()
        self.log.info("── Startup Complete ──")

    def _post_launch_sequence(self):
        """
        Runs after game is confirmed running — at startup and after any
        mid-session relaunch. Focuses window, clears popups, confirms
        home screen, and initialises the shield.
        """
        self.log.info("Focusing game window …")
        self.screen.focus_game_window()
        time.sleep(1)

        detected_region = self.screen.get_game_window_region()
        if detected_region:
            self.cfg.SCREENSHOT_REGION = detected_region
            self.log.info(f"SCREENSHOT_REGION auto-set to {detected_region}")
        else:
            self.log.warning("Could not detect game window region — using config value.")

        self.log.info("Dismissing popups (first pass) …")
        self.popups.dismiss_all()

        self.log.info("Waiting 5 seconds for delayed popups …")
        time.sleep(5)

        self.log.info("Dismissing popups (second pass) …")
        self.popups.dismiss_all()
        time.sleep(1)

        self.log.info("Navigating to home screen …")
        if self.page_nav.ensure_page("home"):
            self.log.info("On home screen.")
        else:
            self.log.warning("Could not confirm home screen — proceeding anyway.")
        time.sleep(1)

        self.log.info("Checking shield status …")
        self.shield.initialise()

    # ── Game Launch ──────────────────────────────────────────────────────

    def _ensure_game_running(self):
        """Launch the game if it is not running."""
        if self._is_game_process_running():
            self.log.info("Game is already running.")
            return

        self.log.warning("Game is NOT running — attempting to launch …")
        launched = False

        if self.screen.click_image("lords_icon.png", confidence=0.70):
            self.log.info("Clicked Lords Mobile desktop icon.")
            launched = True

        if not launched:
            exe_path = self.cfg.GAME_EXE_PATH
            if os.path.isfile(exe_path):
                self.log.info(f"Starting game via exe: {exe_path}")
                try:
                    os.startfile(exe_path)
                    launched = True
                except Exception as e:
                    self.log.error(f"os.startfile failed: {e}")

        if not launched:
            self.log.error("Could not launch game — please start it manually.")
            return

        self.log.info(f"Waiting {self.cfg.GAME_STARTUP_WAIT_SEC}s for game to load …")
        time.sleep(self.cfg.GAME_STARTUP_WAIT_SEC)

        self.log.info("Dismissing startup popups …")
        for attempt in range(10):
            if self.screen.click_image("cross_button1.png", confidence=0.70):
                self.log.info(f"Startup popup closed (attempt {attempt + 1}).")
                time.sleep(1.5)
            else:
                if self.screen.find_image("diamond.png", confidence=0.70):
                    self.log.warning("Diamond promo visible but no X found — waiting.")
                    time.sleep(1.5)
                    continue
                break
            time.sleep(1)

        self.log.info("Game launch complete.")

    def _is_game_process_running(self) -> bool:
        """Check if the game process is alive via psutil or tasklist."""
        process_name = self.cfg.GAME_PROCESS_NAME
        try:
            import psutil
            for proc in psutil.process_iter(attrs=["name"]):
                if proc.info["name"] and \
                        process_name.lower() in proc.info["name"].lower():
                    return True
            return False
        except ImportError:
            pass

        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
                capture_output=True, text=True, timeout=10,
            )
            return process_name.lower() in result.stdout.lower()
        except Exception as e:
            self.log.warning(f"Could not check running processes: {e}")

        return False

    def _check_game_alive(self) -> bool:
        """
        If the game has closed, relaunch it and re-run the full
        post-launch sequence. Returns True if a relaunch happened
        (caller should skip the rest of the cycle).
        """
        if self._is_game_process_running():
            return False

        self.log.warning("=" * 50)
        self.log.warning("  GAME CLOSED — relaunching …")
        self.log.warning("=" * 50)

        self.timer.cancel("shield")
        self._ensure_game_running()
        self._post_launch_sequence()
        self.log.info("Game relaunch complete — resuming.")
        return True

    # ── Main Loop ────────────────────────────────────────────────────────

    def _main_loop(self):
        """
        Smart sleep loop:
          1. Run a full work cycle
          2. Sleep until the shield has ~SHIELD_EARLY_REFRESH_MIN min left,
             waking every GAME_ALIVE_CHECK_INTERVAL_SEC to check the game
             is still running and not disconnected
          3. Repeat
        """
        cycle = 0
        while self.running:
            cycle += 1
            self.log.debug(f"── Cycle {cycle} ──")

            try:
                self._run_full_cycle()
                self._smart_sleep()
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception:
                self.log.exception("Unhandled error in main loop")

            if not self.running:
                break

        self.log.info("Bot stopped.")

    def _run_full_cycle(self):
        """All active checks in priority order."""
        # 0 — Game still running?
        if self._check_game_alive():
            return

        # 1 — Session kicked?
        if self.session.check():
            return

        # 2 — Shield timer
        self.shield.tick()

        # 2b — Shield-stuck recovery. If activate_shield() has failed
        # repeatedly, the game UI is in a bad state (e.g. a Reports/mail
        # window absorbing every click). Force the same close+relaunch
        # path as a disconnect — _check_game_alive() on the next cycle
        # will see the game is gone and start a fresh session.
        fail_threshold = self.cfg.SHIELD_FAIL_RECOVERY_THRESHOLD
        if fail_threshold > 0 and self.shield.consecutive_failures >= fail_threshold:
            self.log.warning("=" * 50)
            self.log.warning(
                f"  SHIELD STUCK — {self.shield.consecutive_failures} "
                "consecutive failures, forcing game relaunch."
            )
            self.log.warning("=" * 50)
            # Reset before recovery so we don't immediately retrigger.
            self.shield.consecutive_failures = 0
            # Close the game; next cycle's _check_game_alive() relaunches.
            self.session.force_relogin()
            time.sleep(self.cfg.GAME_CLOSE_WAIT_SEC)
            return

        # 3 — Popups
        self.popups.dismiss_all()

    def _smart_sleep(self):
        """
        Sleep efficiently until the shield needs refreshing.

        Calculates the exact seconds until (shield_remaining - threshold),
        then sleeps in GAME_ALIVE_CHECK_INTERVAL_SEC chunks. Each chunk
        checks the game process and disconnect dialog — no OCR, no template
        scans, near-zero CPU.
        """
        remaining_sec = self.timer.remaining_seconds("shield")
        threshold_sec = self.cfg.SHIELD_EARLY_REFRESH_MIN * 60
        sleep_for = max(0.0, remaining_sec - threshold_sec)

        if sleep_for < 60:
            # Shield due very soon — skip sleep, go straight to next cycle
            self.log.debug(
                f"Shield due in {remaining_sec:.0f}s — skipping sleep."
            )
            return

        wake_at = datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)
        self.log.info(
            f"Shield OK — sleeping {sleep_for / 3600:.2f}hrs  "
            f"(wake at {wake_at.strftime('%H:%M:%S')}, "
            f"game-alive check every "
            f"{self.cfg.GAME_ALIVE_CHECK_INTERVAL_SEC / 60:.0f} min)"
        )

        chunk = self.cfg.GAME_ALIVE_CHECK_INTERVAL_SEC
        slept = 0.0

        while slept < sleep_for and self.running:
            this_chunk = min(chunk, sleep_for - slept)
            time.sleep(this_chunk)
            slept += this_chunk

            if not self.running:
                break

            # Lightweight check — process existence only, no UI work
            if not self._is_game_process_running():
                self.log.warning(
                    "Game closed during sleep — breaking out to relaunch."
                )
                break

            # Disconnect check — the process stays ALIVE during a disconnect,
            # so the process check above won't catch it. We must also look
            # for the disconnect dialog so we don't sleep for hours while
            # logged out.
            if self.session.check():
                self.log.warning(
                    "Disconnect detected during sleep — breaking out to recover."
                )
                break

            remaining_now = self.timer.remaining_seconds("shield")
            self.log.debug(
                f"Sleep check — game alive, "
                f"{remaining_now / 60:.1f} min shield remaining."
            )

        if self.running:
            self.log.info("Waking up — running full cycle.")


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="LordsBot — Lords Mobile shield bot")
    p.add_argument("--shield-hours", type=int, default=None, choices=[4, 8],
                   help="Override shield duration (4 or 8). Default: config.py setting.")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def main():
    args = parse_args()

    config = BotConfig()
    config.LOG_LEVEL = args.log_level

    # Only override shield hours if explicitly passed on the command line.
    # Otherwise config.py values are used as-is.
    if args.shield_hours is not None:
        config.SHIELD_DURATION_HOURS = args.shield_hours
        config.SHIELD_INTERVAL_SEC = args.shield_hours * 3600
        config.SHIELD_HOUR_IMAGE = "shield4h.png" if args.shield_hours == 4 else "shield8h.png"

    logger = setup_logging(args.log_level)
    bot = LordsBot(config, logger)

    signal.signal(signal.SIGINT, bot.stop)
    signal.signal(signal.SIGTERM, bot.stop)

    bot.start()


if __name__ == "__main__":
    main()
