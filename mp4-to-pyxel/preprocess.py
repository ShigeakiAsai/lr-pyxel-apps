#!/usr/bin/env python3
"""
mp4 -> Pyxel 動画パック変換ツール

入力の mp4 から、Pyxel で再生できる「フレームパック」を作る。
  - 全フレーム共通の16色パレットを作成 (pyxel.colors にそのまま流し込める形式)
  - 各フレームをそのパレットに量子化し、1ピクセル=1バイト(色インデックス0-15)で
    frames.bin にそのまま連結して書き出す
  - 必要なら音声も 16bit PCM wav として抽出する

使い方:
    python3 preprocess.py input.mp4 out_dir --width 256 --height 224 --fps 20 --audio

出力 (out_dir 内):
    manifest.json  - 幅/高さ/fps/フレーム数/パレット/音声情報
    frames.bin     - 生フレームデータ (1 byte/pixel, 必要なら zlib 圧縮)
    audio.wav      - 抽出した音声 (--audio 指定時のみ)

必要なもの: ffmpeg (PATH上), Pillow, numpy
"""
import argparse
import json
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import numpy as np
from PIL import Image


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def extract_frames(src, tmp_dir, width, height, fps):
    pattern = str(Path(tmp_dir) / "f_%06d.png")
    run([
        "ffmpeg", "-y", "-i", src,
        "-vf", f"scale={width}:{height}:flags=lanczos,fps={fps}",
        pattern,
    ])
    return sorted(Path(tmp_dir).glob("f_*.png"))


def extract_audio(src, out_wav, sample_rate):
    run([
        "ffmpeg", "-y", "-i", src,
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-acodec", "pcm_s16le",
        out_wav,
    ])


def build_palette(frame_paths, sample_count=24):
    """クリップ全体で共有する16色パレットを作る。

    数枚のフレームをサンプリングして1枚の帯画像に貼り合わせ、
    Pillow のメディアンカット量子化で代表16色を選ばせる。
    """
    step = max(1, len(frame_paths) // sample_count)
    samples = frame_paths[::step][:sample_count]
    imgs = [Image.open(p).convert("RGB") for p in samples]
    w, h = imgs[0].size
    strip = Image.new("RGB", (w, h * len(imgs)))
    for i, im in enumerate(imgs):
        strip.paste(im, (0, h * i))
    pal_img = strip.quantize(colors=16, method=Image.MEDIANCUT)
    raw_palette = pal_img.getpalette()[: 16 * 3]
    rgb = [tuple(raw_palette[i:i + 3]) for i in range(0, 48, 3)]
    return pal_img, rgb


def to_hex_colors(rgb_list):
    return [(r << 16) | (g << 8) | b for r, g, b in rgb_list]


LAUNCHER_TEMPLATE = '''#!/usr/bin/env python3
# main.py — preprocess.py が自動生成した起動スクリプト。
#
# lr-pyxel は Python スクリプトを実行する前に、ソースコードのテキストを
# 静的パースして pyxel.init() のリテラル引数を探し、それを最初の
# RetroArch ジオメトリ申告(retro_get_system_av_info / 最初のSET_GEOMETRY)に
# 使う (retro.rs の parse_pyxel_init())。manifest.json から実行時に読んだ
# 変数を pyxel.init() に渡すと静的パーサが解決できずデフォルト値
# (128x128)にフォールバックしてしまい、後から正しい値で再申告しても
# 表示が化ける (実測: {width}x{height}の映像が128x128前提の枠の上側
# {height}/128 の位置に収まり、残りが空白になる)。
#
# そのため、ここで pyxel.init() をリテラル引数で明示的に呼んでおき、
# VideoApp 側では skip_pyxel_init=True で呼び直しをスキップする。
import pyxel
pyxel.init({width}, {height}, title="Pyxel Video", fps={fps})

from pathlib import Path
from video_common import PcmAudioController, VideoApp

VideoApp(
    str(Path(__file__).resolve().parent),
    audio_controller=PcmAudioController(),
    window_title="Pyxel Video",
    skip_pyxel_init=True,
)
'''


def write_launcher(out_dir: Path, width: int, height: int, fps: int):
    """lr-pyxel向けの起動スクリプト (main.py) を生成する。

    video_common.py もこの main.py と同じディレクトリに置くこと
    (preprocess.py 自体はコピーしないので、python_video/ 一式から
    video_common.py を out_dir にコピーしてから使う)。
    """
    code = LAUNCHER_TEMPLATE.format(width=width, height=height, fps=fps)
    (out_dir / "main.py").write_text(code, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="入力 mp4 ファイル")
    ap.add_argument("out_dir", help="出力先ディレクトリ")
    ap.add_argument("--width", type=int, default=256, help="出力幅 (<=256, Pyxel の IMAGE_SIZE 上限)")
    ap.add_argument("--height", type=int, default=224, help="出力高さ (<=256)")
    ap.add_argument("--fps", type=int, default=20, help="再生フレームレート")
    ap.add_argument("--audio", action="store_true",
                     help="音声も抽出する (pyxel.sounds[].pcm()でそのまま読み込める16bit wav)")
    ap.add_argument("--sr", type=int, default=22050, help="音声サンプルレート (Hz)")
    ap.add_argument("--compress", action="store_true",
                     help="frames.bin を zlib 圧縮する (再生側が起動時に全展開してRAM保持する前提)")
    args = ap.parse_args()

    if args.width > 256 or args.height > 256:
        sys.exit("Pyxel の画像バンクは 256x256 が上限です (pyxel.IMAGE_SIZE)。--width/--height を小さくしてください。")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        print("ffmpeg でフレームを抽出中...")
        frame_paths = extract_frames(args.input, tmp, args.width, args.height, args.fps)
        if not frame_paths:
            sys.exit("フレームが抽出できませんでした。入力ファイルや ffmpeg の出力を確認してください。")

        print(f"{len(frame_paths)} フレームから共有パレットを作成中...")
        pal_img, rgb_palette = build_palette(frame_paths)
        palette_hex = to_hex_colors(rgb_palette)

        print("フレームを量子化してパック中...")
        frames_path = out_dir / "frames.bin"
        with open(frames_path, "wb") as fout:
            for p in frame_paths:
                im = Image.open(p).convert("RGB")
                q = im.quantize(palette=pal_img, dither=Image.FLOYDSTEINBERG)
                idx = np.array(q, dtype=np.uint8)  # 0-15, shape (h, w)
                data = idx.tobytes()
                if args.compress:
                    data = zlib.compress(data, level=6)
                    fout.write(len(data).to_bytes(4, "little"))
                fout.write(data)

    audio_info = None
    if args.audio:
        print("音声トラックを抽出中...")
        wav_path = out_dir / "audio.wav"
        try:
            extract_audio(args.input, str(wav_path), args.sr)
            audio_info = {"file": "audio.wav", "sample_rate": args.sr, "channels": 1}
        except subprocess.CalledProcessError:
            print("音声トラックが見つからないか抽出に失敗しました。音声なしで続行します。")

    manifest = {
        "width": args.width,
        "height": args.height,
        "fps": args.fps,
        "frame_count": len(frame_paths),
        "compressed": args.compress,
        "palette": palette_hex,
        "audio": audio_info,
    }
    with open(out_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    write_launcher(out_dir, args.width, args.height, args.fps)

    size_mb = (out_dir / "frames.bin").stat().st_size / (1024 * 1024)
    print(f"完了 -> {out_dir} ({len(frame_paths)} フレーム, frames.bin {size_mb:.1f} MB)")
    print(f"lr-pyxel用に {out_dir / 'main.py'} を生成しました "
          f"(video_common.py をこのディレクトリにコピーしてから使ってください)")


if __name__ == "__main__":
    main()
