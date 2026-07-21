# Pyxel 動画プレイヤー

mp4 を Pyxel (16色, 画像バンク最大256x256) で再生できる形式に変換し、
PC (`python3` 実行) と Lakka 上の lr-pyxel コアの両方で再生するためのツール一式。

```
preprocess.py    mp4 -> frames.bin / manifest.json / audio.wav (PCで実行)
video_common.py  共通処理 (FrameStore, 音声コントローラ, VideoAppアプリ本体)
player.py        PC実行・lr-pyxelコア実行 共通のプレイヤー
build_pyxapp.sh  mp4 -> .pyxapp をワンコマンドで作る自動化スクリプト
```

## 0. ワンコマンドで .pyxapp まで作る (lr-pyxel向け)

```bash
chmod +x build_pyxapp.sh   # 初回のみ
./build_pyxapp.sh input.mp4 out_name --width 128 --height 96 --fps 20 --audio
```

`preprocess.py` → `video_common.py`の同梱 → `pyxel package`によるパッケージング
までを一括で行い、`out_name.pyxapp`を生成する。追加の引数はそのまま
`preprocess.py`に渡されるので、`--compress`なども通常通り使える
(下記「1. 前処理」を参照)。生成された`.pyxapp`は`pyxel play out_name.pyxapp`
でPC上でも動作確認できるほか、LakkaのROMS_DIR(例: `/storage/roms/pyxel`)に
置けばlr-pyxelからそのまま起動できる。

個別に手を動かしたい場合は、以下の「1. 前処理」「2. 再生」の手順を
そのまま使うこともできる。

## 1. 前処理 (PC上、ffmpeg + Pillow + numpy が必要)

```bash
pip install pillow numpy --break-system-packages   # 未導入なら

python3 preprocess.py input.mp4 out_dir \
    --width 256 --height 224 --fps 20 --audio
```

- `--width/--height` は Pyxel の画像バンク上限 (256x256, `pyxel.IMAGE_SIZE`) 以下にすること。
- クリップ全体で共有する16色パレットを自動生成し、各フレームをそこへ量子化する
  (ディザリングあり)。`pyxel.colors.from_list()` にそのまま渡せる形式。
- `--audio` を付けると音声を 16bit PCM wav (`--sr` で指定、デフォルト22050Hz) として
  別途書き出す。PC実行モードでのみ使用する。
- `--compress` で `frames.bin` を zlib 圧縮 (再生側は起動時に全展開してRAMに保持する)。
  Lakka の SD カード容量が厳しい場合に有効。ただし短い/低解像度クリップ向き。

**容量の目安**: 無圧縮で 1フレーム = 幅×高さ バイト。例えば 256x224 @ 20fps を
1分再生すると frames.bin は約 65MB になる。Lakka の保存領域に合わせて解像度・fps・
収録時間を調整すること。

## 2. 再生 (PC / lr-pyxelコア共通)

**PC実行:**
```bash
python3 player.py out_dir
```

**lr-pyxel実行:** `preprocess.py`が`out_dir`内に自動生成する`main.py`を使う
(理由は下の「lr-pyxel向け: ジオメトリの静的パース対策」を参照)。
`video_common.py`を`out_dir`にコピーしてから、`main.py`と`video_common.py`が
同じディレクトリにある状態でpyxappパッケージングすること。

- PC実行時はこのように `out_dir` を引数で渡す。操作方法は下記「操作方法(終了まわり)」を参照。
- 音声は外部ライブラリ無しで Pyxel 自身の PCM 再生機能
  (`pyxel.sounds[].pcm()` + `pyxel.play()`) を使う。`pyxel.play_pos()` が返す
  再生位置(秒)をそのまま映像の再生クロックにしているので、音声とのズレが出にくい。
  lr-pyxelの`audio.rs`(`submit_audio_frame()`)がトラッカー音・PCM音を区別せず
  `Audio::render_samples()`経由でRetroArchに流す実装のため、実機
  (RPi5/Lakka)でも動作確認済み。
  もし音がおかしい(速度/ピッチが変)場合は、`player.py`冒頭の
  `AudioController = PcmAudioController` を
  `from video_common import NullAudioController as AudioController`
  に切り替えて映像のみで運用すること。
- 音声なし時の再生クロックは内部の frame_count ベースのカウンタ
  (コアのfpsと動画のfpsが同じ前提。異なる場合は `video_common.py` の
  `VideoApp.update()` にスケーリング処理を追加すること)。
- 依存は標準ライブラリ + pyxel のみ。numpy/Pillowは前処理(PC側)でしか使わないため、
  Lakka側のvendor site-packagesにwheelを置く必要は無い。

### 操作方法(終了まわり)

| 操作 | キー/ボタン | 動作 |
|---|---|---|
| 一時停止/再開 | `SPACE` | 映像・音声とも一時停止/再開する |
| キャンセル(再生中) | `Q` キー / コントローラー `X` ボタン | 何も表示せず即座に `pyxel.quit()` で終了する |
| 再生終了後 | 何かキー/ボタン | 右下に `play end` / `-push any key-` と表示され、いずれかのキー/ボタン入力で `pyxel.quit()` する |

- 動画が最後まで再生し終わると(音声終了、または音声なし時のフレーム終端到達)、
  自動では終了せず、最終フレームの上に上記メッセージを重ねて表示した状態で待機する。
  この状態で `ANY_KEY_CANDIDATES`(`video_common.py`)に列挙したキー/ボタンの
  いずれかが押されたタイミングで終了する。
- メッセージの文字色/背景色は固定ではなく、動画専用の16色パレット
  (`pyxel.colors.from_list()`で総入れ替えされている)の中から、実行時に
  輝度が最も高い色/低い色を自動選択している。動画によって見た目の配色は
  変わるが、コントラストは常に確保される。
- `pyxel.quit()`は、PC実行時はウィンドウを閉じる通常の終了動作、lr-pyxel実行時は
  `system_wrapper_lr.rs`の実装により`RETRO_ENVIRONMENT_SHUTDOWN`を発行して
  RetroArch自体を終了させる動作になる。「動画だけ終えてlr-pyxelのフロントエンド
  (ファイル一覧画面)に戻りたい」場合は、`pyxel.quit()`の代わりに
  `pyxel.load_content()`(引数無し)に差し替えること。

### lr-pyxel向け: ジオメトリの静的パース対策

lr-pyxelの`retro.rs`(`retro_load_game()`)は、Pythonスクリプトを実行する前に
ソースコードのテキストを静的パースして`pyxel.init()`の**リテラル**引数
(`pyxel.init(128, 96, ...)`のような直接値)を探し、それを最初のRetroArch
ジオメトリ申告に使う設計になっている(`parse_pyxel_init()`)。

`video_common.py`の`VideoApp`は`manifest.json`を実行時に読んだ変数
(`self.w`/`self.h`)を`pyxel.init()`に渡すため、この静的パーサは解決できず
デフォルト値(128x128)にフォールバックしてしまう。その後スクリプトが実際に
走って正しいサイズで`pyxel.init()`が呼ばれ、RetroArchへの`SET_GEOMETRY`は
再度正しく送られるものの、**最初の128x128前提でRetroArchが計算した表示領域が
尾を引いて、映像が本来より小さい枠の中に偏って表示される**症状が実機で確認された
(例: 128x96の映像が上側75%に収まり、下25%が空白になる)。

対策として、`preprocess.py`は変換のたびに`out_dir`内へ`main.py`を自動生成する。
この`main.py`は`pyxel.init(128, 96, ...)`のようにリテラル値を直接書いた状態で
最初に呼んでおき、`VideoApp`側は`skip_pyxel_init=True`で二重初期化を避ける
構成になっている。lr-pyxel向けにパッケージングする際は、`player.py`ではなく
この`main.py`を起動スクリプトとして使うこと。

## フレームデータの仕組み (実装メモ)

`pyxel.Image.data_ptr()` は画像バンクの生バッファ (1ピクセル=1バイト、パレット
インデックス0-15) への直接ポインタを返す。ただし lr-pyxel では `pyxel.images[]`
の各バンクは常に `pyxel.IMAGE_SIZE`(256)×256 固定で確保されており、かつ
`data_ptr()` が返すのは生のポインタ(整数アドレス)ではなく `ctypes` の配列
オブジェクト (`c_uint8 * (256*256)`)。そのため:

- ゲームの解像度(例: 128x96)が256より小さい場合、1行あたりの実際のストライドは
  常に256バイトになる。前処理側で作った `frame_bytes` は幅ぴったり(例:128バイト/行)
  で詰めたデータなので、単純に`ctypes.memmove()`で一括コピーすると行がズレて
  「縦が半分に潰れて画面上半分だけに表示される」症状になる(実機で確認済み)。
- 配列オブジェクトには整数を足すポインタ演算ができないため、アドレス演算による
  回避もできない。

`video_common.py`の`VideoApp.update()`では、これを避けるため1行ずつ正しい
オフセット(`row * pyxel.IMAGE_SIZE`)へスライス代入でコピーしている:

```python
for row in range(self.h):
    row_bytes = frame_bytes[row * self.w:(row + 1) * self.w]
    offset = row * self.stride  # self.stride = pyxel.IMAGE_SIZE
    self.img_ptr[offset:offset + self.w] = row_bytes
```

`Image.set()`の16進文字列パースよりは高速だが、Python側でのループが残るため、
ODROID-XU4のような非力な実機では解像度によっては負荷がかかる。
`--width/--height/--fps` を落として実測しながらチューニングすることを推奨する。
