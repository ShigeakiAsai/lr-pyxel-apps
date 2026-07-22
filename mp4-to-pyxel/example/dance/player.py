#!/usr/bin/env python3
"""
Pyxel 動画プレイヤー (PC実行 / lr-pyxelコア実行 共通)

preprocess.py で作った frame パック (manifest.json + frames.bin (+ audio.wav)) を
Pyxel 上で再生する。音声は外部ライブラリ無しで Pyxel 自身の PCM 再生機能
(pyxel.sounds[].pcm() + pyxel.play()) を使い、pyxel.play_pos() の秒数を
そのまま映像の再生クロックにする。

out_dir の決め方 (PC/コア両対応):
    - コマンドライン引数があればそれを使う
      例: python3 player.py out_dir   (PC実行時)
    - 引数が無ければ、このスクリプト自身と同じディレクトリを out_dir とみなす
      lr-pyxel は pyxel.load_content() 経由でこのスクリプトをそのまま実行する
      ため sys.argv に out_dir は入ってこない。pyxappパッケージングツールは
      変換済み frames.bin 一式と player.py を同じディレクトリにまとめて
      .pyxapp にする、という構成を想定している。

音声について:
    lr-pyxel の audio.rs (submit_audio_frame()) は、pyxel_core::channels() を
    毎フレーム Audio::render_samples() に渡して RetroArch の audio_batch_cb に
    そのまま流している。トラッカー音かPCM音かを区別しない実装なので、
    pyxel.sounds[].pcm() + play() で鳴らした音もこの経路にそのまま乗る
    (実機 RPi5/Lakka で動作確認済み)。
    もし音がおかしい(速度/ピッチが変)場合は、下の import を
    NullAudioController に切り替えて映像のみで運用すること。

操作:
    SPACE : 一時停止 / 再開
    ESC   : 終了 (PC実行時。lr-pyxel上ではフロントエンド側の操作に従う)
"""
import sys
from pathlib import Path

from video_common import PcmAudioController, VideoApp

# 音がおかしい場合はこちらに切り替えて映像のみで運用:
# from video_common import NullAudioController as AudioController
AudioController = PcmAudioController


def resolve_out_dir() -> str:
    script_dir = Path(__file__).resolve().parent

    # パッケージング済み(.pyxapp)実行時はこちらを優先する。
    # `pyxel play x.pyxapp` や lr-pyxel の pyxel.load_content() 経由だと、
    # このスクリプト用にきれいな sys.argv が用意されるとは限らず、
    # ホスト側のコマンドライン引数をそのまま引き継いでしまうことがある
    # (例: `pyxel play x.pyxapp` 経由だと sys.argv[1] が "play" になり、
    # out_dir と誤認してしまう — 実機で確認済み)。
    # そのため sys.argv より先に、スクリプト自身の場所に manifest.json が
    # あるかどうかで判定する。
    if (script_dir / "manifest.json").exists():
        return str(script_dir)

    if len(sys.argv) >= 2:
        # 手動でのPC実行時 (python3 player.py out_dir) はこちら。
        return sys.argv[1]

    return str(script_dir)


def main():
    out_dir = resolve_out_dir()
    VideoApp(out_dir, audio_controller=AudioController(), window_title="Pyxel Video")


# if __name__ == "__main__": のガードは使わない。
# lr-pyxel が pyxel.load_content() 経由でこのスクリプトを実行する際、
# 実行環境によっては __name__ が "__main__" にならない可能性があり、
# その場合ガード付きだと main() が一切呼ばれず何も起動しなくなる
# (frontend.py もガード無しのトップレベル実行スタイルになっている)。
# `python3 player.py out_dir` として直接実行する場合は __name__ は
# 必ず "__main__" になるため、ガードを外しても動作は変わらない。
main()
