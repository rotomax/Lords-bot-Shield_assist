# LordsMobile PC — Shield-Assist Test Build

A small Python automation for **Lords Mobile PC** that keeps a turf
shield active on your own account. This is a personal build of a larger personal project from Satyajeet-kuma4, stripped down to a single job so other players
can try it out and give feedback.

## What it does

* Detects whether the game is running and launches it if not
* Reads the shield countdown timer via OCR
* Re-applies a 4-hour (or 8-hour) shield when it's about to expire
* Detects the "logged in on another device" disconnect dialog and
recovers gracefully (so you can play on your phone without the program
fighting you for the session)
* Dismisses common popups; **never clicks the diamond purchase button**
* Logs everything to `bot.log` so you can see what it did

That's it. No notifications, no chest-collection, no auto-attack — just
shield maintenance.

## ⚠ Disclaimer

This is a **personal hobby project**. It is not affiliated with, endorsed
by, or supported by IGG or Lords Mobile. Automating gameplay may violate
the game's Terms of Service. By using this software you accept all risk
to your account. The authors and contributors accept no responsibility
for account bans, lost items, missed shields, or any other consequence
of using this software. Use at your own risk.

## Requirements (for running code directly / running the executable) 

* **Windows 10 or 11** (for both methods)
* **Lords Mobile PC** installed (the official client, for both methods)
* **Screen resolution: 1920×1080** (other resolutions will need calibration — tools included)
* **Python 3.10 or newer** (only for running the code, not required for executable)
* **Tesseract OCR** for Windows (separate installer) - required for both

## Installation

### 1. Install Python (not required if you download the Exe)

If you don't already have it, download **Python 3.11** from
[python.org/downloads/windows](https://www.python.org/downloads/windows/).
During installation, **tick "Add python.exe to PATH"** on the first screen.

Confirm it works by opening Command Prompt and running:
```
python --version
```
### 2. Install Tesseract OCR

The program reads the shield countdown using OCR, which requires Tesseract to
be installed separately from Python.

1. Download the Windows installer from the UB-Mannheim build:
[https://github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)
2. Run the installer. The default install location is
`C:\Program Files\Tesseract-OCR\` — keep it there if you can; the program
looks for it at that path by default.
3. If you install it somewhere else, edit `TESSERACT_CMD` in `config.py`.

### 3. Download Lords Shield assist (code or Exe) 

 download the ZIP from GitHub and extract it.

### 4. Install Python dependencies (not required for Exe) 

```
pip install -r requirements.txt
```

## Configuration (code / Exe ) 

Open `config.py` (or settings.ini) ****in any text editor (Notepad works). The two values you
most likely need to change are at the top of the **Game**section:

```
GAME_EXE_PATH = r"C:\UsersYourUserName\AppDataRoaming\IGG\Lords Mobile PC\Lords Mobile Updater.exe"
```

Replace `YourUserName` with your Windows username. If your install is in
a different location, point this to wherever `Lords Mobile Updater.exe`
lives.

```
SHIELD_DURATION_HOURS = 4
SHIELD_HOUR_IMAGE     = "shield4h.png"
```
If you'd rather use 8-hour shields, change both:
```
SHIELD_DURATION_HOURS = 8
SHIELD_HOUR_IMAGE     = "shield8h.png"
```
Save and close.

## Screen resolution

This build is calibrated for **1920×1080 fullscreen**. Set your Windows
display to 1920×1080 before running the ShieldAssist. Lords Mobile PC should be in
**windowed mode** at its default size — when you launch it the window will
sit roughly in the centre of your screen, and the program auto-detects its
exact position at startup.

If you're on a different resolution and willing to calibrate, see the
"Different resolution" section under Troubleshooting below.

Set power settings on PC to never sleep. 

## Running the ShieldAssist

1. **Open Lords Mobile PC** and log in to your account. Get to the home
screen (the view of your turf with your castle in the middle).
2. **Make sure your turf shield row is the first item** when you open the
Turf Boost panel — i.e. when you click the boost icon on the right
edge of the screen, "Shield" should be the top row.
3. Run ShieldAssist.exe (and skip step 4 & 5 below)
4. If you are running the code, **Open Command Prompt** in the folder (Shift + right-click in the
folder, "Open in Terminal" or "Open command window here").
5. Run:
   python main.py

The program will check the game is open, navigate to the home screen, read
your current shield timer, and apply a shield if needed. Then it will
sleep until the shield is close to expiring, and refresh it.

**To stop the program:** press `Ctrl+Shift+Q` from any window, or `Ctrl+C` in
the command prompt window.

### First run — what to watch

*  `bot.log` (open it in Notepad). You should see lines about:

  * Game window region detected
  * Popups dismissed
  * Shield Manager initialising
  * Shield timer reading (e.g. "Shield timer: 3h 59m 58s")
* If a `debug_*.png` file is created in the  folder, open it — it
shows what the program saw at the moment something went wrong.

### Useful command-line options

```
python main.py                      # normal run
python main.py --shield-hours 8     # use 8hr shields for this run
python main.py --log-level DEBUG    # verbose logging
```

## How the smart-sleep loop works

The program does NOT poll the screen every second — that would be wasteful and
risk fighting you for control of the game. Instead it:

1. Reads the shield timer once
2. Calculates how long until the shield has 5 minutes left
3. Sleeps for that long, waking only every 10 minutes to check that the
game is still running and not showing a disconnect dialog
4. Wakes up at the right time, refreshes the shield, sleeps again

CPU usage is essentially zero between checks.

## Disconnect handling

If you log in to your account on another device (e.g. your phone), Lords
Mobile shows a "Disconnected — this account is logged in on another
device" dialog on the PC and the session goes dead. When the program sees
this dialog it:

1. **Waits 30 minutes** before doing anything, so you can play on your
phone without the program trying to kick you out
2. **Watches your shield timer during the wait** — if the shield gets
close to expiring, the program recovers immediately to protect it
3. **After the wait**, dismisses the dialog, closes the game process,
and relaunches it to start a fresh session

You can change the 30-minute wait via `DISCONNECT_RECOVERY_DELAY_MIN` in
`config.py`. Set to 0 to recover instantly.

## Safety guarantees built into the code

* **Never clicks the diamond/purchase button.** The diamond image is
used only to *detect* a purchase promo, so the program knows to look for
the X close button instead.
* **Never clicks Confirm on the "Quit Game?" dialog.** Every ESC press
goes through `safe_esc()`, which clicks Cancel if the quit dialog
appears.
* **Double-shield guard.** Before applying a shield, the program re-reads
the timer. If a healthy shield is already active, it skips applying
another one — protecting you from wasting a shield item.

## Troubleshooting

### The shieldassist can't find the Turf Boost icon

Check `debug_boost_panel.png` and `debug_shield_menu_fail.png` in the 
folder — these show what the program saw. Most common causes:

* The game is in fullscreen instead of windowed mode
* The screen resolution doesn't match 1920×1080
* Something is covering the boost icon (a popup, an event banner)

If the issue is resolution or coordinate-related, run `calibrate.py`
(see below).

### Tesseract not found / OCR returns garbage

Check the path in `config.py`:

```
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Make sure that file actually exists. If you installed Tesseract to a
different drive or folder, update this path.

### Shield activation fails repeatedly

The program is designed to handle this: after 5 consecutive failed shield
activations it will force-close the game and relaunch it (the same
recovery path as a disconnect). If you see "SHIELD STUCK" warnings in
`bot.log`, that's the recovery kicking in. If it happens repeatedly,
something on screen is consistently blocking the boost panel (an event,
a chat popup, etc.) — let me know what you see.

### Different resolution

If you can't use 1920×1080, you can calibrate:

1. Run `python calibrate.py`
2. Hover over the elements it asks about and press Enter
3. Copy the coordinates it prints into the matching fields in `config.py`
(`TURF_BOOST_FALLBACK_POS`, `SHIELD_ROW_ARROW_POS`,
`SHIELD_TIMER_REGION`)
4. You may also need to recapture some of the PNG templates in `utils/`
so they match how the game renders at your resolution — but try
running first, the template matching may still work.

### The program clicked something I didn't expect

Stop the program (`Ctrl+Shift+Q`), open `bot.log` and look at the last few
lines for what the program was trying to do. Open any `debug_*.png` files
to see what it saw. Then please report the issue (see below) with both
the log lines and the screenshots — that's the fastest way to fix it.

## File overview

```
main.py            Entry point and main loop
config.py          All settings on a single BotConfig dataclass
calibrate.py       Coordinate finder utility

modules/
  screen_utils.py    Screenshots, OCR, template matching, clicking
  timer_tracker.py   Named countdown timers (the shield)
  shield_manager.py  Reads the shield timer; applies/refreshes shield
  popup_handler.py   Closes popups via the X (never the diamond)
  page_navigator.py  Detects which game screen is active
  session_monitor.py Disconnect detection and recovery

utils/             Template PNGs the program matches on screen
  shield1.png, shield4h.png, shield8h.png    Shield menu rows
  turfBoost0.png                              Boost icon
  use.png, ok.png                             Confirmation buttons
  cross_button1.png                           X close button on popups
  close_button.png                            Close button on disconnect dialog
  cancel_button.png                           Cancel on Quit Game dialog
  diamond.png                                 Diamond promo (DETECTION ONLY)
  map.png, return_castle.png, kvk_map.png    Page-detection markers
  lords_icon.png                              Desktop icon (for launching)

requirements.txt   Python dependencies
bot.log            Runtime log (created on first run)
debug_*.png        Diagnostic screenshots (created on failures)
```

## License

MIT — see [LICENSE](LICENSE).

