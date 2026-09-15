#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""引擎自检：改完引擎跑一下这个，比开窗口快得多。

    python tools/selftest.py

覆盖：语法解析 / 无头推进（两条分支）/ 加解密往返 / 篡改检测 /
      资源包打包与读取 / 界面能不能画出一帧（用 SDL 的 dummy 驱动，不弹窗口）/
      stm.os 受控文件操作（读 / 建 / 改 + 备份 / 移回收站）/
      python 代码块（解析 / 逐行提示 + 等待 / 变量回写 / 发布版跳过）
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
            elif blk["t"] == "wait":
                # python 代码块的逐行间隔：无头测试没必要真等
                sess.next_block()
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
        elif app.state == 10:         # WAIT（python 代码块的间隔）：跳过等待
            app.wait_timer = 1e9
            app.update(0.0)
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


def test_pyblock():
    print("\n== 9. python 代码块 ==")
    # 每一行后面标了它在本文件里的行号，专门用来验「切块之后行号有没有错位」
    src = "\n".join([
        "<",                        # 1
        'title="t"',                # 2
        ">",                        # 3
        "<",                        # 4
        "Start:",                   # 5
        'stmg.python("none")',      # 6
        "<",                        # 7
        "python:",                  # 8
        'print("1")',               # 9
        'print("2")',               # 10
        "total = 1 + 2",            # 11
        ">",                        # 12
        '"看到提示了吗？"',          # 13
        '"算出来是 " + str(total)',  # 14
        ">",                        # 15
        "<",                        # 16
        '"e"',                      # 17
        ">",                        # 18
    ])
    sc = parser.parse_text(src)
    check("python 代码块没报语法错", sc.error_count() == 0,
          "\n".join(str(i) for i in sc.issues))
    nodes = [s for s in sc.walk() if s["k"] == "pycode"]
    check("解析出 1 个 python 代码块", len(nodes) == 1, str(len(nodes)))
    check("代码行原样抠出来了",
          bool(nodes) and nodes[0]["code"] == ['print("1")', 'print("2")',
                                               "total = 1 + 2"],
          repr(nodes[0]["code"]) if nodes else "无")
    check("默认间隔是 3 秒", bool(nodes) and nodes[0]["delay"] == 3.0,
          str(nodes[0]["delay"]) if nodes else "无")
    check("代码块之后行号没被挤错位",
          [s["line"] for s in sc.walk() if s["k"] == "say"] == [13, 14],
          str([s["line"] for s in sc.walk() if s["k"] == "say"]))
    check("stmg.python(\"none\") 被当成合法写法", not sc.issues)

    # 逐行飘提示 + 行间等待
    sess = Session(sc, None, True)
    toasts, waits, says = [], [], []
    for _ in range(40):
        blk = sess.block
        toasts.extend(sess.toasts)
        if blk["t"] == "say":
            says.append(blk["text"])
        elif blk["t"] == "wait":
            waits.append(blk.get("dur"))
        elif blk["t"] in ("end", "fatal"):
            break
        sess.next_block()
    check("print 的内容变成了右上角提示", toasts == ["1", "2"], str(toasts))
    check("两行提示之间等 3 秒", waits == [3.0], str(waits))
    check("提示飘完剧情照常往下走",
          bool(says) and "看到提示了吗" in says[0], str(says))
    check("代码里算出来的变量带回了剧本",
          "算出来是 3" in says, str(says))

    # 冒号后面写数字 = 改间隔
    sc2 = parser.parse_text("\n".join([
        "<", 'title="t"', ">", "<", "Start:",
        "<python: 5", 'print("x")', ">", '"d"', ">",
    ]))
    n2 = [s for s in sc2.walk() if s["k"] == "pycode"]
    check("<python: 5 同一行的写法也认", bool(n2) and not sc2.error_count(),
          "\n".join(str(i) for i in sc2.issues))
    check("间隔改成了 5 秒", bool(n2) and n2[0]["delay"] == 5.0)

    # 发布版：整块跳过，不产生等待
    sess_rel = Session(sc, None, False)
    rel_toasts, rel_waits = [], 0
    for _ in range(40):
        blk = sess_rel.block
        rel_toasts.extend(sess_rel.toasts)
        if blk["t"] == "wait":
            rel_waits += 1
        if blk["t"] in ("end", "fatal"):
            break
        sess_rel.next_block()
    check("发布版整块跳过（不会等 3 秒）", rel_waits == 0, str(rel_waits))
    check("发布版会明确说一句被忽略了",
          any("发布版" in t for t in rel_toasts), str(rel_toasts))


def test_mod():
    print("\n== 10. 美化包（mod/）==")
    from stmg import mod

    packs = {p["id"]: p for p in mod.list_mods()}
    check("默认包 none 在", "none" in packs, str(sorted(packs)))
    check("示例包 example_sakura 在", "example_sakura" in packs)
    check("默认包校验通过", not mod.errors_of(mod.verify(packs["none"]["path"])),
          "; ".join(mod.errors_of(mod.verify(packs["none"]["path"]))))
    check("示例包校验通过",
          not mod.errors_of(mod.verify(packs["example_sakura"]["path"])))

    man = mod.manifest(packs["example_sakura"]["path"])
    check("清单认得出「美化包」类型", man.get("kind") == mod.KIND)
    check("清单有名字", bool(man.get("name")))

    t = mod.load_theme(ROOT, "example_sakura")
    check("美化包的 CONFIG 读出来了", t["config"].get("box_radius") == 16,
          str(t["config"].get("box_radius")))
    check("美化包带了网页版样式", "deco-petal" in (t["css"] or ""))
    check("美化包带了网页版脚本", "STMGTheme" in (t["js"] or ""))

    from stmg import uiconf
    check("不带美化包 = 引擎默认值", uiconf.load(ROOT)["box_radius"] == 10)
    check("带上美化包就生效", uiconf.load(ROOT, "example_sakura")["box_radius"] == 16)
    check("--no-mod 能临时关掉", uiconf.load(ROOT, "example_sakura", True)["box_radius"] == 10)
    check("找不到的包会安全回退", mod.load_theme(ROOT, "没有这个包")["ok"] is False)

    # ---- 严格限制：临时造几个违规包，必须被判死 ----
    tmp = tempfile.mkdtemp()
    try:
        def bad(name, files):
            p = os.path.join(tmp, "mod", name)
            os.makedirs(p, exist_ok=True)
            for rel, text in files.items():
                full = os.path.join(p, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(text)
            return p

        ok_head = '{"kind": "beautify", "name": "x", "version": "1", "author": "y"}\n'

        p = bad("py_call", {"mod.json": ok_head,
                            "gui.py": 'CONFIG = {}\nimport os\nopen("a.txt", "w")\n'})
        errs = mod.errors_of(mod.verify(p))
        check("拦住 import / open（不许执行 pycode）", len(errs) >= 2, "; ".join(errs))

        p = bad("py_expr", {"mod.json": ok_head,
                            "gui.py": 'import os\nCONFIG = {"box_h": os.getcwd()}\n'})
        check("拦住 CONFIG 里的表达式", bool(mod.errors_of(mod.verify(p))))

        p = bad("py_engine", {"mod.json": ok_head, "gui.py": "CONFIG = {}\n",
                              "patch.py": "CONFIG = {}\nfrom stmg import gui\n"})
        errs = mod.errors_of(mod.verify(p))
        check("拦住多余的 .py", any("只允许一个" in m for m in errs), "; ".join(errs))

        p = bad("py_enginefiles", {"mod.json": ok_head, "gui.py": "CONFIG = {}\n",
                                   "stmg/gui.py": "CONFIG = {}\n",
                                   "start.py": "CONFIG = {}\n"})
        errs = mod.errors_of(mod.verify(p))
        check("拦住 stmg/ 目录和 start.py",
              any("stmg/" in m for m in errs) and any("start.py" in m for m in errs),
              "; ".join(errs))

        p = bad("css_remote", {"mod.json": ok_head, "gui.py": "CONFIG = {}\n",
                               "theme.css": '#dialogue{background:url("https://x/a.png")}\n'
                                            '@import "http://y/b.css";\n'})
        errs = mod.errors_of(mod.verify(p))
        check("拦住远程 url / @import", len(errs) >= 2, "; ".join(errs))

        p = bad("js_escape", {"mod.json": ok_head, "gui.py": "CONFIG = {}\n",
                              "theme.js": 'STMGTheme.register({});\n'
                                          'eval("1"); localStorage.getItem("s");'
                                          'fetch("http://x");\n'})
        errs = mod.errors_of(mod.verify(p))
        check("拦住 eval / localStorage / fetch", len(errs) >= 3, "; ".join(errs))

        binp = bad("exe", {"mod.json": ok_head, "gui.py": "CONFIG = {}\n"})
        with open(os.path.join(binp, "patch.bat"), "w", encoding="utf-8") as f:
            f.write("echo hi\n")
        check("拦住可执行文件",
              any(".bat" in m for m in mod.errors_of(mod.verify(binp))))

        t2 = mod.load_theme(tmp, "py_call")
        check("不合格的包会被安全回退", t2["ok"] is False and not t2["config"])

        # ---- 新建骨架 ----
        newp = mod.create_mod(tmp, "我的主题", name="我的主题", author="测试")
        check("能新建美化包骨架", os.path.isfile(os.path.join(newp, mod.MANIFEST_NAME)))
        check("新建的骨架本身就是合格的",
              not mod.errors_of(mod.verify(newp)),
              "; ".join(mod.errors_of(mod.verify(newp))))
        try:
            mod.create_mod(tmp, "我的主题")
            check("重名会拒绝覆盖", False)
        except OSError:
            check("重名会拒绝覆盖", True)

        # ---- 启用状态往返 ----
        with open(os.path.join(tmp, "mod", "active.json"), "w", encoding="utf-8") as f:
            f.write('{"mod": "我的主题"}\n')
        check("active.json 读得回来", mod.active_id(tmp) == "我的主题",
              str(mod.active_id(tmp)))
        check("按根目录找得到包", mod.find_mod("我的主题", tmp) is not None)
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
    test_pyblock()
    test_mod()
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
