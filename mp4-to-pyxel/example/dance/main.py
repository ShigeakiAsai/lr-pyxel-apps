#!/usr/bin/env python3
# main.py — preprocess.py が自動生成した起動スクリプト。
#
# lr-pyxel は Python スクリプトを実行する前に、ソースコードのテキストを
# 静的パースして pyxel.init() のリテラル引数を探し、それを最初の
# RetroArch ジオメトリ申告(retro_get_system_av_info / 最初のSET_GEOMETRY)に
# 使う (retro.rs の parse_pyxel_init())。manifest.json から実行時に読んだ
# 変数を pyxel.init() に渡すと静的パーサが解決できずデフォルト値
# (128x128)にフォールバックしてしまい、後から正しい値で再申告しても
# 表示が化ける (実測: 256x256の映像が128x128前提の枠の上側
# 256/128 の位置に収まり、残りが空白になる)。
#
# そのため、ここで pyxel.init() をリテラル引数で明示的に呼んでおき、
# VideoApp 側では skip_pyxel_init=True で呼び直しをスキップする。
import pyxel
pyxel.init(256, 256, title="Pyxel Video", fps=20)

from pathlib import Path
from video_common import PcmAudioController, VideoApp

VideoApp(
    str(Path(__file__).resolve().parent),
    audio_controller=PcmAudioController(),
    window_title="Pyxel Video",
    skip_pyxel_init=True,
)
