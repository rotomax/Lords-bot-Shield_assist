"""
Coordinate Finder — Calibration Utility
========================================
Hover your mouse over game UI elements and press Enter to record their
positions. Use the recorded coordinates to update config.py if the bot is
clicking in the wrong place on your machine.

Usage:  python calibrate.py
"""

import time
import pyautogui


def main():
    print("=" * 50)
    print("  LordsBot — Coordinate Finder")
    print("=" * 50)
    print("\nHover over each element and press Enter to record its position.")
    print("Press Ctrl+C to quit at any time.\n")
    print("Make sure the game is open on the home/turf screen, and the\n"
          "turfBoost icon is visible on the right edge of the window.\n")

    labels = [
        ("Turf Boost icon (right edge of screen)",
         "TURF_BOOST_FALLBACK_POS"),
        ("'>' arrow on the Shield row (after opening boost panel)",
         "SHIELD_ROW_ARROW_POS"),
        ("Shield timer text — top-left corner of the timer box",
         "SHIELD_TIMER_REGION (top-left)"),
        ("Shield timer text — bottom-right corner of the timer box",
         "SHIELD_TIMER_REGION (bottom-right)"),
    ]

    results = {}
    for label, key in labels:
        input(f"  -> Hover over [{label}] and press Enter...")
        pos = pyautogui.position()
        results[key] = (pos.x, pos.y)
        print(f"    Recorded: {key} = ({pos.x}, {pos.y})\n")

    print("\n" + "-" * 50)
    print("Results:\n")
    for key, val in results.items():
        print(f"    {key}: {val}")

    # Helpful: compute the SHIELD_TIMER_REGION (x, y, width, height) tuple
    # from the two corners the user recorded.
    if ("SHIELD_TIMER_REGION (top-left)" in results
            and "SHIELD_TIMER_REGION (bottom-right)" in results):
        tl = results["SHIELD_TIMER_REGION (top-left)"]
        br = results["SHIELD_TIMER_REGION (bottom-right)"]
        x, y = tl
        w, h = br[0] - tl[0], br[1] - tl[1]
        print(f"\n    SHIELD_TIMER_REGION (for config.py): ({x}, {y}, {w}, {h})")

    print("-" * 50)

    print("\nLive mouse tracker (Ctrl+C to stop):\n")
    try:
        while True:
            pos = pyautogui.position()
            print(f"  Mouse: ({pos.x}, {pos.y})    ", end="\r")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDone.")


if __name__ == "__main__":
    main()
