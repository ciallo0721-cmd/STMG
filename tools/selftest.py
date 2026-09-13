#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""引擎自检：改完引擎跑一下这个，比开窗口快得多。

    python tools/selftest.py

覆盖：语法解析 / 无头推进（两条分支）/ 加解密往返 / 篡改检测 /
      资源包打包与读取 / 界面能不能画出一帧（用 SDL 的 dummy 驱动，不弹窗口）/
      stm.os 受控文件操作（读 / 建 / 改 + 备份 / 移回收站）
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from stmg import crypto, options as optmod, pack, parser          # noqa: E402
from stmg.session import Session                                  # noqa: E402

DEMO = os.path.join(ROOT, "demo", "script.stm")
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("OK" if cond else "!!", name,
                           ("  -> " + detail) if detail and not cond else ""))


def test_parse():
    print("\n== 1. 语法解析 ==")
    sc = parser.parse_file(DEMO)
    check("demo 没有语法错误", sc.error_count() == 0,
          "\n".join(str(i) for i in sc.issues))
    check("分辨率读对了", sc.size == (1280, 720), str(sc.size))
    says = [s for s in sc.walk() if s["k"] == "say"]
    check("台词条数 > 10", len(says) > 10, str(len(says)))
    ifs = [s for s in sc.walk() if s["k"] == "if"]
    check("If 解析出 4 个", len(ifs) == 4, str(len(ifs)))
    check("If 的正文不为空", all(s["body"] for s in ifs))
    return sc


def test_headless(sc):
    print("\n== 2. 无头推进 ==")
    op = optmod.load_options(optmod.find_options(DEMO))
    for pick, label, expect in ((0, "选「读纸条」", "纸条上写着"),
                                (1, "选「先睡一觉」", "睡了一觉")):
        sess = Session(sc, op, True)
        texts, guard = [], 0
        while True:
            blk = sess.block
            if blk["t"] == "say":
                texts.append(blk["text"])
                sess.next_block()
            elif blk["t"] == "choose":
                sess.answer(blk["options"][pick])
            elif blk["t"] == "question":
                sess.answer("小明")
            else:
                break
            guard += 1
            if guard > 500:
                break
        joined = "\n".join(texts)
        check("%s 走到了正确分支" % label, expect in joined)
        check("%s 拿到玩家输入" % label, "小明" in joined)
        check("%s 没有崩溃" % label, not sess.crashed)


def test_crypto():
    print("\n== 3. 加解密 ==")
    plain = "这是一段用来测试加解密的中文文本，混排 English 和 12345。".encode("utf-8") * 40
    blob = crypto.encrypt(plain, "p@ssword-123")
    check("密文和明文不一样", blob != plain)
    check("解密还原", crypto.decrypt(blob, "p@ssword-123") == plain)
    bad_key = False
    try:
        crypto.decrypt(blob, "wrong")
    except crypto.DecryptError:
        bad_key = True
    check("错误口令被拒绝", bad_key)
    tampered = bytearray(blob)
    tampered[len(tampered) // 2] ^= 0x01
    caught = False
    try:
        crypto.decrypt(bytes(tampered), "p@ssword-123")
    except crypto.DecryptError:
        caught = True
    check("篡改一个字节能被发现", caught)

    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "a.stm")
        with open(src, "w", encoding="utf-8") as f:
            f.write("你好 STMG")
        dst = os.path.join(tmp, "a.stmdec")
        crypto.encrypt_file(src, dst, "k")
        check("文件级加解密",
              crypto.load_text(dst, "k") == "你好 STMG")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_pack():
    print("\n== 4. 资源包 ==")
    tmp = tempfile.mkdtemp()
    try:
        game = os.path.join(tmp, "game")
        os.makedirs(os.path.join(game, "music"))
        os.makedirs(os.path.join(game, "gui"))
        with open(os.path.join(game, "music", "bgm.mp3"), "wb") as f:
            f.write(b"FAKE-MP3" * 100)
        with open(os.path.join(game, "gui", "note.txt"), "w",
                  encoding="utf-8") as f:
            f.write("hi")
        out = os.path.join(tmp, "assets.stmdec")
        n, _size = pack.build(game, ["*.mp3", "*.txt"], out, "k")
        check("打包进去 2 个文件", n == 2, str(n))
        pk = pack.AssetPack(out, "k")
        check("能读出 music/bgm.mp3", pk.has("music/bgm.mp3"))
        check("内容一致", pk.read("music/bgm.mp3") == b"FAKE-MP3" * 100)
        pack.set_current(pk)
        check("open_binary 读包内文件",
              pack.open_binary("stmgpack:/gui/note.txt").read() == b"hi")
        check("不存在的文件返回 False", not pack.exists("music/none.mp3"))
        pack.set_current(None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_gui(sc):
    print("\n== 5. 界面能画出来 ==")
    try:
        import pygame
        from stmg.gui import App
    except ImportError as e:
        check("pygame 可用", False, str(e))
        return
    op = optmod.load_options(optmod.find_options(DEMO))
    app = App(sc, op, dev_mode=True)
    app.start_game()
    frames = 0
    for _ in range(40):
        app.draw()
        if app.state == 1:            # ADVANCE
            app.reveal = 1e9
            app.advance()
        elif app.state == 2:          # CHOOSE
            app.choose(0)
        elif app.state == 3:          # QUESTION
            app.submit_answer("小明")
        elif app.state in (7, 8):     # ERROR / ENDING
            break
        frames += 1
    check("画了 %d 帧没报错" % frames, frames > 10)
    check("跑到结局了", app.state == 8, "state=%s" % app.state)
    pygame.quit()


def test_project():
    print("\n== 6. 项目管理 / 新建项目 ==")
    from stmg import project as proj
    tmp = tempfile.mkdtemp()
    old = proj.PROJECTS_DIR
    try:
        proj.PROJECTS_DIR = os.path.join(tmp, "projects")
        proj.ensure_dirs()
        path = proj.create_project("测试项目", "测试标题")
        check("新建项目成功", os.path.isdir(path))
        check("script.stm 生成了", os.path.isfile(os.path.join(path, "script.stm")))
        check("options.stm 生成了", os.path.isfile(os.path.join(path, "options.stm")))
        check("素材文件夹齐了", all(os.path.isdir(os.path.join(path, d))
                                for d in ("bg", "png", "music", "gui")))
        sc = parser.parse_file(proj.script_of(path))
        check("模板剧本 0 语法错误", sc.error_count() == 0,
              "\n".join(str(i) for i in sc.issues))
        check("重名会自动换名字", proj.create_project("测试项目") != path)
        check("读得到标题", proj.info(path)["title"] == "测试标题")
        trashed = proj.trash_project(path)
        check("移除项目是挪走不是删除",
              not os.path.isdir(path) and os.path.isdir(trashed))
    finally:
        proj.PROJECTS_DIR = old
        shutil.rmtree(tmp, ignore_errors=True)


def test_errscreen():
    print("\n== 8. 游戏内错误界面（解析错误不进 CLI）==")
    try:
        from stmg.gui import App, ERROR
    except ImportError as e:
        check("pygame 可用", False, str(e))
        return
    broken = os.path.join(ROOT, "projects", "YandereContract2.0", "script.stm")
    if not os.path.isfile(broken):
        check("找到带错误的剧本", False, "缺 projects/YandereContract2.0/script.stm")
        return
    sc = parser.parse_file(broken)
    check("剧本确实有 20 个错误", sc.error_count() == 20, str(sc.error_count()))
    try:
        app = App(sc, None, dev_mode=True, script_errors=sc.issues)
    except Exception as e:                                 # noqa: BLE001
        check("带错误的剧本也能开窗口", False, "%s: %s" % (type(e).__name__, e))
        return
    check("开窗口后直接进错误界面", app.state == ERROR, "state=%s" % app.state)
    check("错误模式是 script", app.error_mode == "script")
    rows = app._error_rows()
    blob = "\n".join(t for t, _ in rows)
    check("行号进了界面", "行 2510" in blob and "行 3919" in blob)
    check("原始信息进了界面", "If 的正文既没缩进也没有 EndIf" in blob)
    check("提示也进了界面", "对照 README 的语法表" in blob)
    try:
        app.draw()
        check("错误界面画了一帧没崩", True)
    except Exception as e:                                 # noqa: BLE001
        check("错误界面画了一帧没崩", False, "%s: %s" % (type(e).__name__, e))


def test_launcher():
    print("\n== 7. 启动器能起来 ==")
    try:
        import launcher
    except ImportError as e:
        check("启动器能导入", False, "缺依赖：%s" % e)
        return
    try:
        app = launcher.Launcher()          # CustomTkinter 自己建窗口
        app.update_idletasks()
        check("主界面构建成功", app.listbox is not None)
        check("项目列表有内容", len(app.projects) >= 1, str(len(app.projects)))
        check("界面配置已载入", isinstance(getattr(app, "cfg", None), dict))
        app.update()
        app.destroy()
    except Exception as e:                             # noqa: BLE001
        check("主界面构建成功", False, "%s: %s" % (type(e).__name__, e))


def test_stmos():
    print("\n== 8. stm.os 受控文件操作 ==")
    from stmg import stmos
    sc = parser.parse_text("\n".join([
        "<", "title=\"t\"", ">",
        "<", "Start:",
        "stm.os(create(\"a.txt\"))",
        "stm.os(read(\"a.txt\"))",
        "stm.os(revision(\"a.txt\"),\"x\"to\"y\")",
        "stm.os(remove(\"a.txt\"))",
        ">",
        "<", "\"e\"", ">",
    ]))
    nodes = [s for s in sc.walk() if s["k"] == "stm_os"]
    check("解析出 4 个 stm_os 语句", len(nodes) == 4, str(len(nodes)))
    check("操作名解析正确",
          [n["op"] for n in nodes] == ["create", "read", "revision", "remove"])
    check("revision 的 find/replace 解析对",
          nodes[2]["find"] == "x" and nodes[2]["replace"] == "y")

    tmp = tempfile.mkdtemp()
    try:
        f = os.path.join(tmp, "t.txt")
        ok, _ = stmos.create_file(f)
        check("create 建出空文件", ok and os.path.isfile(f))
        ok, content = stmos.read_file(f)
        check("read 空文件得到空串", ok and content == "")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("axxb")
        ok, _ = stmos.revision_file(f, "x", "y")
        with open(f, encoding="utf-8") as fh:
            data = fh.read()
        check("revision 替换生效", data == "ayyb", data)
        check("revision 留了 .bak 备份", os.path.isfile(f + ".bak"))
        ok, _ = stmos.remove_file(f)
        check("remove 后原文件不在了", ok and not os.path.isfile(f))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("STMG 自检")
    sc = test_parse()
    test_headless(sc)
    test_crypto()
    test_pack()
    test_gui(sc)
    test_project()
    test_errscreen()
    test_launcher()
    test_stmos()
    print("\n" + "=" * 50)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        for name in FAIL:
            print("  失败：%s" % name)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
