"""
player_pc.py / player_core.py で共有する処理。

- FrameStore: frames.bin から任意フレームの生バイト列を取り出す
- NullAudioController / PcmAudioController: 音声クロックの抽象化
- VideoApp: 実際に pyxel.run() を回す共通アプリ本体

音声について (訂正版):
    Pyxel 本体は pyxel.sounds[n].pcm(filename) で WAV/OGG を読み込み、
    pyxel.play(ch, n) で通常のサウンドと同じように再生できる
    (トラッカー専用ではなく、生PCMもそのまま鳴らせる)。
    22050Hz mono 16bit PCM wav で動作確認済み。

    そのため PC実行モードでは外部ライブラリ無しで Pyxel 自身の音声エンジンを
    音声クロックとして使い、pyxel.play_pos() の秒数で映像フレームを同期させる。

    lr-pyxel コア(Lakka)側で同じ経路が使えるかどうかは、MixerBridge が
    Pyxel の音声出力(トラッカーもPCMも同じ内部ミキサーを通る)を
    RetroArch のオーディオコールバックへ橋渡しできているか次第。
    PcmAudioController はPC/コア共通のクラスにしてあるので、
    MixerBridgeが対応済みならコア側でもそのまま差し替えて試せる。
"""
import json
import mmap
import zlib
from pathlib import Path

import pyxel


def load_manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))


class FrameStore:
    """frames.bin から任意フレームの生インデックスバイト列 (1byte/pixel) を取り出す。"""

    def __init__(self, path: Path, width: int, height: int, frame_count: int, compressed: bool):
        self.frame_size = width * height
        self.compressed = compressed
        self._fh = open(path, "rb")

        if not compressed:
            self._mm = mmap.mmap(self._fh.fileno(), 0, access=mmap.ACCESS_READ)
            self.frames = None
        else:
            # 圧縮版は起動時に全展開して RAM に載せる (毎フレーム展開するコストを避ける)
            self._mm = None
            raw = self._fh.read()
            self.frames = []
            pos = 0
            for _ in range(frame_count):
                length = int.from_bytes(raw[pos:pos + 4], "little")
                pos += 4
                chunk = raw[pos:pos + length]
                pos += length
                self.frames.append(zlib.decompress(chunk))

    def get(self, index: int) -> bytes:
        if self.frames is not None:
            return self.frames[index]
        start = index * self.frame_size
        return self._mm[start:start + self.frame_size]


class NullAudioController:
    """音声を鳴らさない構成。frame_count 基準の内部クロックだけで映像を進める。"""

    available = False

    def start(self, manifest: dict, out_dir: Path):
        pass

    def current_sec(self):
        return None

    def toggle_pause(self):
        pass


class PcmAudioController:
    """pyxel.sounds[].pcm() + pyxel.play()/play_pos() を使った音声クロック。

    PC実行モードで動作確認済み。lr-pyxelコア上でMixerBridgeがPyxelの
    音声出力をRetroArchへ橋渡しできるようになったら、コア側でもこのクラスを
    そのまま使える見込み (未検証)。
    """

    CH = 0
    SND = 0

    def __init__(self):
        self.available = False
        self.paused = False
        self._paused_pos = None

    def start(self, manifest: dict, out_dir: Path):
        info = manifest.get("audio")
        if not info:
            return
        pyxel.sounds[self.SND].pcm(str(out_dir / info["file"]))
        pyxel.play(self.CH, self.SND)
        self.available = True

    def current_sec(self):
        if not self.available:
            return None
        pos = pyxel.play_pos(self.CH)
        return pos[1] if pos else None  # None = 再生終了

    def toggle_pause(self):
        if not self.available:
            return
        self.paused = not self.paused
        if self.paused:
            self._paused_pos = pyxel.play_pos(self.CH)
            pyxel.stop(self.CH)
        else:
            resume_sec = self._paused_pos[1] if self._paused_pos else 0.0
            pyxel.play(self.CH, self.SND, sec=resume_sec)


class VideoApp:
    """フレームパックを再生する共通アプリ本体。

    音声ありの場合は audio_controller.current_sec() を再生クロックにする。
    音声なしの場合は pyxel.frame_count ベースの内部クロックにフォールバックする
    (pyxel.init(fps=...) 自体がフレームレートを管理しているので、ここでの
    フレーム数カウントだけで十分同期が取れる)。
    """

    def __init__(self, out_dir: str, audio_controller=None, window_title="Pyxel Video",
                 skip_pyxel_init=False):
        """
        skip_pyxel_init: True の場合、呼び出し側が既に
        pyxel.init(literal_w, literal_h, ...) と pyxel.colors.from_list(...)
        を済ませている前提で、ここでは呼び直さない。

        lr-pyxel は Python スクリプトを実行する前に、ソースコードのテキストを
        静的パースして pyxel.init() のリテラル引数を探し、それを最初の
        RetroArch ジオメトリ申告に使う (retro.rs の parse_pyxel_init())。
        manifest.json から実行時に読んだ変数を pyxel.init() に渡すと
        静的パーサが解決できずデフォルト値にフォールバックしてしまうため、
        preprocess.py が生成する起動スクリプト側でリテラル値の
        pyxel.init(128, 96, ...) を先に呼んでおき、ここではスキップする。
        """
        out_dir = Path(out_dir)
        manifest = load_manifest(out_dir)

        self.w = manifest["width"]
        self.h = manifest["height"]
        self.fps = manifest["fps"]
        self.frame_count_total = manifest["frame_count"]
        self.palette = manifest["palette"]

        self.store = FrameStore(
            out_dir / "frames.bin", self.w, self.h, self.frame_count_total, manifest["compressed"]
        )

        self.audio = audio_controller or NullAudioController()

        if not skip_pyxel_init:
            pyxel.init(self.w, self.h, title=window_title, fps=self.fps)
        pyxel.colors.from_list(self.palette)

        self.img_ptr = pyxel.images[0].data_ptr()
        # pyxel.images[] の各バンクは、ゲーム自身のwidth/height(ここでは
        # self.w/self.h)とは無関係に、常に pyxel.IMAGE_SIZE x IMAGE_SIZE
        # (256x256) で確保される — crates/pyxel-core/src/pyxel.rs の
        # Image::new(IMAGE_SIZE, IMAGE_SIZE) 参照。
        #
        # frame_bytes は self.w バイト/行でぴったり詰めたデータなので、
        # 1回の flat memmove では実際の行幅(self.stride)とズレて、
        # 動画の奇数行が偶数行と同じバッファ行の後半に紛れ込み、
        # 結果として「縦が半分に潰れて画面上半分だけに表示される」
        # 症状になる(実機で確認済み)。行ごとに正しいオフセットへ
        # コピーすることで解消する。
        self.stride = pyxel.IMAGE_SIZE

        self.paused = False
        self.last_shown = -1
        self._manual_frames = 0
        self._ended = False

        self.audio.start(manifest, out_dir)

        pyxel.run(self.update, self.draw)

    def update(self):
        if pyxel.btnp(pyxel.KEY_SPACE):
            self.paused = not self.paused
            self.audio.toggle_pause()

        if self.paused or self._ended:
            return

        if self.audio.available:
            sec = self.audio.current_sec()
            if sec is None:
                self._ended = True  # 音声再生終了 = 動画終了
                return
            target = int(sec * self.fps)
        else:
            target = self._manual_frames
            self._manual_frames += 1

        if target >= self.frame_count_total:
            target = self.frame_count_total - 1
            self._ended = True

        if target != self.last_shown:
            frame_bytes = self.store.get(target)
            # self.img_ptr は生のポインタ(整数アドレス)ではなく、
            # ctypesの配列オブジェクト(c_uint8 * (width*height))
            # (image_wrapper_lr.rs の data_ptr() 実装参照)。
            # 配列オブジェクトに整数を足すポインタ演算はできないので、
            # ctypes.memmove + アドレス演算ではなく、配列への
            # スライス代入で行ごとに書き込む。
            for row in range(self.h):
                row_bytes = frame_bytes[row * self.w:(row + 1) * self.w]
                offset = row * self.stride
                self.img_ptr[offset:offset + self.w] = row_bytes
            self.last_shown = target

    def draw(self):
        pyxel.cls(0)
        pyxel.blt(0, 0, 0, 0, 0, self.w, self.h)
