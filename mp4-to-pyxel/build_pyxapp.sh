#!/usr/bin/env bash
# build_pyxapp.sh — mp4 から lr-pyxel 用 .pyxapp をワンコマンドで作る。
#
# 内部でやっていること:
#   1. preprocess.py で mp4 -> frames.bin / manifest.json / audio.wav
#   2. video_common.py / player.py を出力ディレクトリに同梱
#   3. `pyxel package` で .pyxapp にまとめる (起動スクリプトは player.py)
#      (出力ディレクトリの「親」から実行する必要がある — 中から実行すると
#      出来上がった .pyxapp が出力ディレクトリ自身の中に紛れ込むため)
#
# 使い方:
#   ./build_pyxapp.sh input.mp4 out_name [preprocess.py へのオプション...]
#
# 例:
#   ./build_pyxapp.sh input.mp4 my_video --width 128 --height 96 --fps 20 --audio
#   ./build_pyxapp.sh input.mp4 my_video --width 160 --height 120 --fps 15 --audio --compress
#
# 出力:
#   ./out_name/          preprocess.py の出力一式 + video_common.py + player.py
#   ./out_name.pyxapp    lr-pyxel / pyxel play で実行できるパッケージ

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

usage() {
    echo "使い方: $0 input.mp4 out_name [preprocess.py へのオプション...]" >&2
    echo "例:     $0 input.mp4 my_video --width 128 --height 96 --fps 20 --audio" >&2
    exit 1
}

if [ $# -lt 2 ]; then
    usage
fi

INPUT_MP4="$1"
OUT_NAME="$2"
shift 2
PREPROCESS_ARGS=("$@")

# --- 事前チェック ---------------------------------------------------------

if [ ! -f "$INPUT_MP4" ]; then
    echo "エラー: 入力ファイルが見つかりません: $INPUT_MP4" >&2
    exit 1
fi

for cmd in ffmpeg pyxel python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "エラー: '$cmd' コマンドが見つかりません。インストールしてから再実行してください。" >&2
        exit 1
    fi
done

if [ ! -f "$SCRIPT_DIR/preprocess.py" ] || [ ! -f "$SCRIPT_DIR/video_common.py" ] || [ ! -f "$SCRIPT_DIR/player.py" ]; then
    echo "エラー: preprocess.py / video_common.py / player.py がこのスクリプトと同じディレクトリに見つかりません: $SCRIPT_DIR" >&2
    exit 1
fi

if [ -e "$OUT_NAME" ]; then
    echo "エラー: 出力先が既に存在します: $OUT_NAME (削除するか別名を指定してください)" >&2
    exit 1
fi

# --- 1. mp4 -> frames.bin / manifest.json / audio.wav ----------------------

echo "== [1/3] 前処理 (mp4 -> フレームパック) =="
python3 "$SCRIPT_DIR/preprocess.py" "$INPUT_MP4" "$OUT_NAME" "${PREPROCESS_ARGS[@]}"

# --- 2. video_common.py / player.py を同梱 ---------------------------------

echo "== [2/3] video_common.py / player.py を同梱 =="
cp "$SCRIPT_DIR/video_common.py" "$OUT_NAME/video_common.py"
cp "$SCRIPT_DIR/player.py" "$OUT_NAME/player.py"

# --- 3. .pyxapp にパッケージング -------------------------------------------

echo "== [3/3] .pyxapp としてパッケージング =="
# 出力ディレクトリの「親」から実行する: pyxel package はカレントディレクトリに
# {出力ディレクトリ名}.pyxapp を書き出すため、出力ディレクトリの中から実行すると
# 生成物が出力ディレクトリ自身の中に紛れ込んでしまう。
pyxel package "$OUT_NAME" "$OUT_NAME/player.py"

PYXAPP_FILE="${OUT_NAME}.pyxapp"
if [ -f "$PYXAPP_FILE" ]; then
    SIZE=$(du -h "$PYXAPP_FILE" | cut -f1)
    echo
    echo "完了 -> $PYXAPP_FILE ($SIZE)"
    echo "  Lakka/lr-pyxel の ROMS_DIR (例: /storage/roms/pyxel) に置くか、"
    echo "  'pyxel play $PYXAPP_FILE' でPC上でも動作確認できます。"
else
    echo "警告: $PYXAPP_FILE が見つかりません。pyxel package の出力を確認してください。" >&2
    exit 1
fi
