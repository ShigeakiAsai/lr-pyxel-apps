# title: lr-pyxel Downloader
# desc: Download Pyxel games from the internet
# license: MIT

import pyxel
import json
import os
import sys
import threading

INDEX_URL = "https://raw.githubusercontent.com/ShigeakiAsai/lr-pyxel-apps/main/index.json"
ROMS_DIR  = "/storage/roms/pyxel"

W, H = 128, 128

STATE_LOADING  = 0
STATE_LIST     = 1
STATE_DOWNLOAD = 2
STATE_DONE     = 3
STATE_ERROR    = 4

state     = STATE_LOADING
games     = []
cursor    = 0
message   = "Loading..."
error_msg = ""

# Auto-repeat for UP/DOWN cursor movement: wait REPEAT_HOLD frames after
# the initial press, then repeat every REPEAT_RATE frames at a constant
# interval (no acceleration). Same values as frontend.py for consistency.
REPEAT_HOLD = 20
REPEAT_RATE = 4

# Networking is done entirely on the Rust side (pyxel.http_get /
# pyxel.download_file, which shell out to the system `curl` binary),
# since Lakka's embedded Python has no _socket.so / _ssl.so.


def fetch_index():
    global state, games, error_msg
    try:
        data = pyxel.http_get(INDEX_URL)
        games = json.loads(data)
        if not games:
            raise ValueError("index is empty")
        state = STATE_LIST
    except Exception as e:
        print(f"[downloader] fetch_index error: {e}", file=sys.stderr)
        error_msg = str(e)
        state = STATE_ERROR


def download_game(game):
    global state, message, error_msg
    state = STATE_DOWNLOAD
    message = "Downloading..."
    try:
        dest = os.path.join(ROMS_DIR, game["file"])
        ok = pyxel.download_file(game["url"], dest)
        if ok:
            message = game["file"]
            state = STATE_DONE
        else:
            error_msg = "download failed (curl)"
            state = STATE_ERROR
    except Exception as e:
        print(f"[downloader] download_game error: {e}", file=sys.stderr)
        error_msg = str(e)[:28]
        state = STATE_ERROR


# Fetch index directly (network assumed available)
threading.Thread(target=fetch_index, daemon=True).start()

pyxel.init(W, H, title="lr-pyxel Downloader", fps=30)


def update():
    global cursor, state

    # Ignore input for first 10 frames to avoid button carry-over from launcher
    if pyxel.frame_count < 10:
        return

    if state == STATE_LIST:
        if pyxel.btnp(pyxel.KEY_UP, REPEAT_HOLD, REPEAT_RATE) or \
           pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_UP, REPEAT_HOLD, REPEAT_RATE):
            cursor = max(0, cursor - 1)
        if pyxel.btnp(pyxel.KEY_DOWN, REPEAT_HOLD, REPEAT_RATE) or \
           pyxel.btnp(pyxel.GAMEPAD1_BUTTON_DPAD_DOWN, REPEAT_HOLD, REPEAT_RATE):
            cursor = min(len(games) - 1, cursor + 1)
        if pyxel.btnp(pyxel.KEY_RETURN) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A):
            threading.Thread(target=download_game, args=(games[cursor],), daemon=True).start()

    if state in (STATE_DONE, STATE_ERROR):
        if pyxel.btnp(pyxel.KEY_RETURN) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A):
            pyxel.load_content(None)

    # Note: SELECT (GAMEPAD1_BUTTON_BACK) is intentionally not checked here.
    # retro_run() intercepts SELECT globally for core shutdown before this
    # script's update() ever runs, so a Python-side check for it would
    # never fire anyway.
    if pyxel.btnp(pyxel.KEY_ESCAPE) or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_B):
        pyxel.load_content(None)


def draw():
    pyxel.cls(0)
    pyxel.text(2, 2, "lr-pyxel", 5)
    pyxel.text(54, 2, "DOWNLOAD", 13)
    pyxel.line(0, 10, W - 1, 10, 5)

    if state == STATE_LOADING:
        dots = "." * ((pyxel.frame_count // 10) % 4)
        pyxel.text(24, 56, "Loading" + dots, 13)

    elif state == STATE_LIST:
        for i, game in enumerate(games):
            y = 16 + i * 18
            if i == cursor:
                pyxel.rect(0, y - 1, W, 17, 1)
                pyxel.text(4, y, game["name"][:20], 7)
            else:
                pyxel.text(4, y, game["name"][:20], 6)
            pyxel.text(4, y + 8, "by " + game.get("author", "")[:18], 5)
        pyxel.line(0, H - 12, W - 1, H - 12, 5)
        pyxel.text(2, H - 9, "A:download  B:back", 5)

    elif state == STATE_DOWNLOAD:
        pyxel.text(20, 48, "Downloading...", 13)
        # pyxel.download_file() is a single blocking call (no chunked
        # progress callback like the old socket-based downloader), so we
        # show an indeterminate bouncing-block animation instead of a
        # real percentage.
        pyxel.rectb(13, 61, 102, 10, 5)
        pos = (pyxel.frame_count * 3) % 94
        pyxel.rect(14 + pos, 62, 8, 8, 11)

    elif state == STATE_DONE:
        pyxel.text(20, 48, "Complete!", 11)
        pyxel.text(4, 62, message[:24], 7)
        pyxel.text(20, 80, "A:back", 5)

    elif state == STATE_ERROR:
        pyxel.text(20, 44, "Error!", 8)
        pyxel.text(2, 56, error_msg[:24], 13)
        pyxel.text(2, 64, error_msg[24:48], 13)
        pyxel.text(2, 72, error_msg[48:72], 13)
        pyxel.text(20, 84, "A:back", 5)


pyxel.run(update, draw)
