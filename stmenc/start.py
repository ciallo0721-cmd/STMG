#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STMG 加密打包器（对应设计稿里的 STMENC/start.py）。

用法：

    python stmenc/start.py demo
    python stmenc/start.py demo --out dist/我的游戏 --key 我的口令
    python stmenc/start.py demo --no-assets      不打包素材，只加密剧本
    python stmenc/start.py demo --exe            顺手跑一次 pyinstaller（要先装）

产出（默认 dist/<游戏目录名>/）：

    start.py / start.bat   ← 生成的启动器，口令写在里面
    script.stmdec          ← 加密的主剧本
    options.stmdec         ← 加密的配置
    assets.stmdec          ← gui/ 和 music/ 打成一个加密资源包
    stmg/                  ← 引擎本体（Python 源码，没加密）
    打包成exe.bat          ← 可选：把整个目录封成单个 exe
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import crypto, options as optmod, pack                # noqa: E402

LAUNCHER = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STMG 发布版启动器（由 stmenc/start.py 自动生成，别手改）。"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from stmg import crypto, options as optmod, pack, parser
from stmg.gui import App

KEY = {key!r}


def main():
    script_path = os.path.join(HERE, "script.stmdec")
    if not os.path.isfile(script_path):
        print("缺少 script.stmdec，游戏文件不完整。")
        return 2
    try:
        text = crypto.load_text(script_path, KEY)
    except crypto.DecryptError as e:
        print("解密失败：%s" % e)
        return 3

    assets = os.path.join(HERE, "assets.stmdec")
    if os.path.isfile(assets):
        pack.set_current(pack.AssetPack(assets, KEY))

    script = parser.parse_text(text, script_path)
    opt = optmod.load_options(optmod.find_options(script_path), KEY)
    if not opt.get("enc"):
        opt["enc"] = KEY

    if "--check" in sys.argv:
        # 发布前验一眼：解密 + 解析 + 资源包都正常
        print("标题: %s" % script.title)
        print("语法错误: %d" % script.error_count())
        print("资源包文件数: %d" % (len(pack.active()) if pack.active() else 0))
        return 1 if script.error_count() else 0

    App(script, opt, dev_mode=False).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

BAT = '''@echo off
cd /d "%~dp0"
python start.py
if errorlevel 1 pause
'''

EXE_BAT = '''@echo off
cd /d "%~dp0"
echo 正在打包成单文件 exe（需要先 pip install pyinstaller）...
python -m PyInstaller --noconfirm --onefile --windowed ^
  --name "{name}" ^
  --add-data "stmg;stmg" ^
  --add-data "script.stmdec;." ^
  --add-data "options.stmdec;." ^
  --add-data "assets.stmdec;." ^
  --hidden-import pygame ^
  start.py
echo.
echo 完成后 exe 在 dist\\{name}.exe
pause
'''


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2

    src = os.path.abspath(args[0])
    out = None
    key = None
    do_assets = True
    do_exe = False

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--out":
            i += 1
            out = args[i]
        elif a == "--key":
            i += 1
            key = args[i]
        elif a == "--no-assets":
            do_assets = False
        elif a == "--exe":
            do_exe = True
        i += 1

    if not os.path.isdir(src):
        print("找不到游戏目录：%s" % src)
        return 2

    name = os.path.basename(src.rstrip("\\/")) or "game"
    out = os.path.abspath(out or os.path.join(ROOT, "dist", name))
    script = os.path.join(src, "script.stm")
    if not os.path.isfile(script):
        print("这个目录里没有 script.stm：%s" % src)
        return 2

    opt = optmod.load_options(os.path.join(src, "options.stm"))
    key = key or opt.get("enc") or ""
    if not key:
        print("没给口令。用 --key 指定，或者在 options.stm 里写 Enc = \"...\"")
        return 2

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    # 1. 剧本 + 配置
    crypto.encrypt_file(script, os.path.join(out, "script.stmdec"), key)
    opt_src = os.path.join(src, "options.stm")
    if os.path.isfile(opt_src):
        crypto.encrypt_file(opt_src, os.path.join(out, "options.stmdec"), key)

    # 2. 引擎本体
    shutil.copytree(os.path.join(ROOT, "stmg"), os.path.join(out, "stmg"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # 3. 素材
    if do_assets:
        patterns = opt.get("dec") or ["*.png", "*.jpg", "*.mp3", "*.wav", "*.ogg"]
        n, size = pack.build(src, patterns, os.path.join(out, "assets.stmdec"), key)
        print("素材打包：%d 个文件，%.1f KB" % (n, size / 1024.0))

    # 4. 启动器
    with open(os.path.join(out, "start.py"), "w", encoding="utf-8") as f:
        f.write(LAUNCHER.format(key=key))
    with open(os.path.join(out, "start.bat"), "w", encoding="gbk", errors="replace") as f:
        f.write(BAT)
    with open(os.path.join(out, "打包成exe.bat"), "w", encoding="gbk",
              errors="replace") as f:
        f.write(EXE_BAT.format(name=name))

    print("发布版已经生成：%s" % out)
    print("  双击 start.bat 试跑，或者双击「打包成exe.bat」封成单个 exe。")
    print("  提醒：口令就写在 start.py 里，玩家认真找是能翻出来的。")

    if do_exe:
        print()
        try:
            rc = subprocess.call([sys.executable, "-m", "PyInstaller", "--version"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except OSError:
            rc = 1
        if rc == 0:
            print("PyInstaller 在，双击发布目录里的「打包成exe.bat」就能封成单文件 exe。")
        else:
            print("还没装 PyInstaller。先跑：")
            print("  %s -m pip install pyinstaller" % sys.executable)
            print("装完再双击发布目录里的「打包成exe.bat」。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
