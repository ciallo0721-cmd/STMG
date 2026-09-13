#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STMG 启动器 —— 管项目、跑游戏、查语法、打包、发布。

界面用 CustomTkinter 写的（现代化外观、圆角、跟随系统深浅色）。
启动器本身不需要 pygame，引擎坏了它照样能开。

双击 STMG启动器.bat，或者：

    .venv\\Scripts\\python.exe launcher.py
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _fail_no_ctk():
    """没装 CustomTkinter 时给一句人话，而不是甩一堆 traceback。"""
    msg = ("缺少 CustomTkinter，启动器打不开。\n\n"
           "装一下就好（在 STMG 目录下执行）：\n"
           "    .venv\\Scripts\\python.exe -m pip install customtkinter\n\n"
           "国内网络慢的话加个镜像：\n"
           "    -i https://mirrors.aliyun.com/pypi/simple/")
    print(msg)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "STMG 启动器", 0x10)
    except Exception:                                  # noqa: BLE001
        pass
    sys.exit(1)


try:
    import customtkinter as ctk
except ImportError:
    _fail_no_ctk()

from stmg import project as proj                       # noqa: E402

PY = sys.executable
START = os.path.join(HERE, "start.py")
CHECK = os.path.join(HERE, "tools", "check.py")
PACK = os.path.join(HERE, "stmenc", "start.py")
HTMLPUB = os.path.join(HERE, "tools", "htmlpub.py")
STM2RPY = os.path.join(HERE, "tools", "stm2renpy.py")

ACCENT = "#5b7cfa"
ACCENT_HOVER = "#4169e1"
DANGER = "#c0483f"
CARD = ("#ffffff", "#1b1e28")
BG = ("#eef1f7", "#14161d")
INK = ("#1d2030", "#e9ecf5")
SUB = ("#6b7285", "#98a0b8")
BORDER = ("#c9cede", "#333849")
HOVER = ("#e8ebf3", "#232735")
LOG_BG = "#11131a"
LOG_FG = "#cfd6e6"


class Launcher(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.cfg = proj.load_cfg()
        self.q = queue.Queue()
        self.busy = False
        self.projects = []
        self.current = None
        self._rows = {}
        self._fonts = {}

        self.title("STMG 启动器")
        self.geometry(self.cfg.get("window", "1040x700"))
        self.minsize(920, 620)
        self.configure(fg_color=BG)

        self._build()
        self.refresh()
        self.after(120, self._poll)

    # ------------------------------------------------------------------ #
    def f(self, size=13, bold=False):
        # Tk 只认整数号，11.5 这种会直接报错，这里统一取整
        size = int(round(size))
        key = (size, bold)
        if key not in self._fonts:
            try:
                self._fonts[key] = ctk.CTkFont(family="Microsoft YaHei UI",
                                               size=size,
                                               weight="bold" if bold else "normal")
            except Exception:                          # noqa: BLE001
                self._fonts[key] = ctk.CTkFont(size=size)
        return self._fonts[key]

    def _build(self):
        self.grid_columnconfigure(0, weight=0, minsize=280)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ---------- 顶栏 ----------
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(18, 8))
        head.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(head, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(left, text="STMG", font=self.f(24, True),
                     text_color=INK).pack(side="left")
        ctk.CTkLabel(left, text="Super Text Markdown Galgame", font=self.f(12),
                     text_color=SUB).pack(side="left", padx=(10, 0), pady=(8, 0))

        self.mode_menu = ctk.CTkOptionMenu(head, values=["跟随系统", "浅色", "深色"],
                                           width=112, height=30, font=self.f(12),
                                           command=self.on_mode)
        self.mode_menu.set("跟随系统")
        self.mode_menu.grid(row=0, column=1, sticky="e")

        # ---------- 左：项目列表 ----------
        panel = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        panel.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=(0, 8))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(panel, text="项目", font=self.f(14, True), text_color=INK
                     ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 6))

        self.listbox = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.listbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.listbox.grid_columnconfigure(0, weight=1)

        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 14))
        ctk.CTkButton(row, text="新建项目", width=100, height=34, corner_radius=9,
                      font=self.f(12), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self.new_project).pack(side="left")
        ctk.CTkButton(row, text="添加…", width=80, height=34, corner_radius=9,
                      font=self.f(12), fg_color="transparent", border_width=1,
                      border_color=BORDER, text_color=INK, hover_color=HOVER,
                      command=self.add_project).pack(side="left", padx=8)

        # ---------- 右：详情 + 操作 ----------
        right = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        right.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(0, 8))
        right.grid_columnconfigure(0, weight=1)

        self.lbl_title = ctk.CTkLabel(right, text="没有选中项目", font=self.f(18, True),
                                      text_color=INK, anchor="w")
        self.lbl_title.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 2))
        self.lbl_path = ctk.CTkLabel(right, text="", font=self.f(11.5), text_color=SUB,
                                     anchor="w", justify="left", wraplength=580)
        self.lbl_path.grid(row=1, column=0, sticky="ew", padx=20)
        self.lbl_meta = ctk.CTkLabel(right, text="", font=self.f(11.5), text_color=SUB,
                                     anchor="w")
        self.lbl_meta.grid(row=2, column=0, sticky="ew", padx=20, pady=(2, 14))

        ctk.CTkButton(right, text="启动游戏", height=46, corner_radius=12,
                      font=self.f(15, True), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self.run_game).grid(row=3, column=0, sticky="ew",
                                                  padx=20, pady=(0, 12))

        grid = ctk.CTkFrame(right, fg_color="transparent")
        grid.grid(row=4, column=0, sticky="ew", padx=20)
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="btn")
        acts = [
            ("语法检查", self.run_check, False),
            ("无头试跑", self.run_auto, False),
            ("编辑剧本", self.edit_script, False),
            ("可视化编辑", self.visual_edit, False),
            ("打包发布", self.run_pack, False),
            ("发布为 HTML", self.run_html, True),
            ("转为 Ren'Py", self.run_stm2renpy, True),
            ("打开文件夹", self.open_folder, False),
            ("内嵌引擎", self.embed_engine, False),
            ("清空日志", self.clear_log, False),
            ("移除项目", self.remove_project, False),
        ]
        for i, (text, fn, hot) in enumerate(acts):
            danger = text == "移除项目"
            if hot and not danger:
                fg, bw, border, tc, hv = ACCENT, 0, ACCENT, "#ffffff", ACCENT_HOVER
            elif danger:
                fg, bw, border, tc, hv = "transparent", 1, DANGER, DANGER, ("#f7e5e3", "#3a2320")
            else:
                fg, bw, border, tc, hv = "transparent", 1, BORDER, INK, HOVER
            ctk.CTkButton(grid, text=text, height=38, corner_radius=10,
                          font=self.f(12.5), fg_color=fg, border_width=bw,
                          border_color=border, text_color=tc, hover_color=hv,
                          command=fn).grid(row=i // 3, column=i % 3, sticky="ew",
                                           padx=5, pady=5)

        ctk.CTkLabel(right,
                     text="内嵌引擎 —— 把 stmg/ 拷进项目，项目完全开放，改项目里的 stmg/*.py 即可自定义\n"
                          "发布为 HTML —— 生成能直接双击 / 丢上网页的版本\n"
                          "转为 Ren'Py —— 把剧本转成 .rpy，产物在 dist/<项目名>_renpy/",
                     font=self.f(11), text_color=SUB, anchor="w", justify="left"
                     ).grid(row=5, column=0, sticky="ew", padx=20, pady=(12, 16))

        # ---------- 下：日志 ----------
        bottom = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 18))
        bottom.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(bottom, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bar, text="输出", font=self.f(13, True), text_color=INK
                     ).grid(row=0, column=0, sticky="w")
        self.lbl_state = ctk.CTkLabel(bar, text="就绪", font=self.f(11.5), text_color=SUB)
        self.lbl_state.grid(row=0, column=1, sticky="e")

        self.log = ctk.CTkTextbox(bottom, height=150, corner_radius=10,
                                  fg_color=LOG_BG, text_color=LOG_FG,
                                  font=self.f(11.5), wrap="word")
        self.log.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.log.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # 数据
    # ------------------------------------------------------------------ #
    def refresh(self, keep=None):
        self.projects = proj.list_projects(self.cfg.get("recent"))
        for w in self.listbox.winfo_children():
            w.destroy()
        sel = keep if keep is not None else (self.current or {}).get("path")
        self._rows = {}
        for p in self.projects:
            outside = os.path.normcase(os.path.dirname(p["path"])) != \
                os.path.normcase(proj.PROJECTS_DIR)
            name = (p["title"] or p["name"]) + ("   (外部)" if outside else "")
            b = ctk.CTkButton(self.listbox, text=name, anchor="w", height=38,
                              corner_radius=9, font=self.f(12.5),
                              fg_color="transparent", text_color=INK, hover_color=HOVER,
                              command=lambda pp=p: self.show(pp))
            b.pack(fill="x", pady=2)
            self._rows[os.path.normcase(p["path"])] = b

        if not self.projects:
            self.current = None
            self.lbl_title.configure(text="还没有项目")
            self.lbl_path.configure(text="点左下角「新建项目」，会生成一份能直接跑的模板。")
            self.lbl_meta.configure(text="")
            return

        target = None
        for p in self.projects:
            if sel and os.path.normcase(p["path"]) == os.path.normcase(sel):
                target = p
        target = target or self.projects[0]
        self.show(target)

    def show(self, p):
        self.current = p
        for k, b in self._rows.items():
            if os.path.normcase(p["path"]) == k:
                b.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER,
                            text_color="#ffffff")
            else:
                b.configure(fg_color="transparent", hover_color=HOVER, text_color=INK)
        self.lbl_title.configure(text=p["title"] or p["name"])
        self.lbl_path.configure(text=p["path"])
        self.lbl_meta.configure(text="%s 修改 · %s 句台词 · %s"
                                     % (p["mtime_text"], p["says"], p["size_text"]))
        proj.push_recent(p["path"])

    # ------------------------------------------------------------------ #
    # 日志 / 状态
    # ------------------------------------------------------------------ #
    def log_line(self, text):
        self.q.put(text)

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _poll(self):
        dirty = False
        while True:
            try:
                text = self.q.get_nowait()
            except queue.Empty:
                break
            if not dirty:
                self.log.configure(state="normal")
                dirty = True
            self.log.insert("end", text + "\n")
            self.log.see("end")
        if dirty:
            self.log.configure(state="disabled")
        self.lbl_state.configure(text="忙…" if self.busy else "就绪",
                                 text_color=ACCENT if self.busy else SUB)
        self.after(120, self._poll)

    def _run(self, args, title, capture=True):
        if self.busy:
            InfoDialog(self, "等一下", "上一个任务还没跑完。")
            return
        self.busy = True
        self.log_line("")
        self.log_line("=" * 62)
        self.log_line("$ " + " ".join('"%s"' % a if " " in a else a
                                      for a in [os.path.basename(args[0])] + args[1:]))

        def worker():
            try:
                kw = {}
                if capture:
                    kw["stdout"] = subprocess.PIPE
                    kw["stderr"] = subprocess.STDOUT
                p = subprocess.Popen(args, cwd=HERE,
                                     env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                     **kw)
                if capture and p.stdout:
                    for raw in iter(p.stdout.readline, b""):
                        self.log_line(raw.decode("utf-8", "replace").rstrip())
                p.wait()
                self.log_line("-- 退出码 %d --" % p.returncode)
            except Exception as e:                     # noqa: BLE001
                self.log_line("启动失败：%s" % e)
            finally:
                self.busy = False
                self.log_line("[%s] 结束" % title)

        threading.Thread(target=worker, daemon=True).start()

    def _need(self):
        if not self.current:
            InfoDialog(self, "先选一个项目", "左边列表里点一个项目。")
            return False
        return True

    # ------------------------------------------------------------------ #
    # 主操作
    # ------------------------------------------------------------------ #
    def _local_start(self):
        """项目内嵌了引擎（带 start.py + stmg/）就用项目自己的。"""
        if not self.current:
            return START
        s = os.path.join(self.current["path"], "start.py")
        return s if os.path.isfile(s) else START

    def run_game(self):
        if not self._need():
            return
        script = proj.script_of(self.current["path"])
        self.log_line("启动游戏：%s" % self.current["title"])
        try:
            subprocess.Popen([PY, self._local_start(), script], cwd=self.current["path"],
                             env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        except Exception as e:                         # noqa: BLE001
            self.log_line("启动失败：%s" % e)

    def run_check(self):
        if not self._need():
            return
        if self._local_start() != START:
            # 内嵌引擎的项目：用项目自己的引擎查，改动 stmg/ 也能反映出来
            self._run([PY, self._local_start(), "--check",
                       proj.script_of(self.current["path"])], "语法检查")
            return
        self._run([PY, CHECK, self.current["path"], "--verbose"], "语法检查")

    def run_auto(self):
        if not self._need():
            return
        self._run([PY, self._local_start(), "--auto", proj.script_of(self.current["path"])],
                  "无头试跑")

    def embed_engine(self):
        if not self._need():
            return
        p = self.current["path"]
        if os.path.isfile(os.path.join(p, "stmg", "__init__.py")):
            self.log_line("这个项目已经内嵌引擎了。想更新就删掉项目里的 stmg/ 再点一次。")
            return
        self.log_line("内嵌引擎到项目 %s ..." % self.current["name"])
        done = proj.embed_engine(p)
        self.log_line("完成，共 %d 个文件。直接改项目里的 stmg/*.py 就能自定义引擎，"
                      "只影响这个项目，不用动启动器源码。" % len(done))

    def run_pack(self):
        if not self._need():
            return
        out = os.path.join(HERE, "dist", self.current["name"])
        self._run([PY, PACK, self.current["path"], "--out", out], "打包发布")

    def run_html(self):
        if not self._need():
            return
        dlg = HtmlDialog(self)
        if not dlg.result:
            return
        out = os.path.join(HERE, "dist", "%s_web" % self.current["name"])
        args = [PY, HTMLPUB, self.current["path"], "--out", out,
                "--engine", dlg.result["engine"]]
        if dlg.result["assets"] == "inline":
            args.append("--inline")
        elif dlg.result["assets"] == "none":
            args.append("--no-assets")
        self._run(args, "发布为 HTML")
        self.log_line("产物：%s —— 双击 index.html 就能玩。" % out)

    def run_stm2renpy(self):
        if not self._need():
            return
        out = os.path.join(HERE, "dist", "%s_renpy" % self.current["name"])
        self._run([PY, STM2RPY, self.current["path"], "--out", out], "转为 Ren'Py")

    def edit_script(self):
        if not self._need():
            return
        p = proj.script_of(self.current["path"])
        try:
            os.startfile(p)                            # noqa: S606 - Windows 专用
            self.log_line("已用系统默认编辑器打开：%s" % p)
        except Exception as e:                         # noqa: BLE001
            self.log_line("打不开：%s" % e)

    def visual_edit(self):
        if not self._need():
            return
        p = proj.script_of(self.current["path"])
        VisualEditor(self, p)

    def open_folder(self):
        if not self._need():
            return
        try:
            os.startfile(self.current["path"])          # noqa: S606
        except Exception as e:                         # noqa: BLE001
            self.log_line("打不开：%s" % e)

    def new_project(self):
        dlg = NewProjectDialog(self)
        if not dlg.result:
            return
        try:
            path = proj.create_project(dlg.result["name"], dlg.result["title"],
                                       dlg.result["size"])
        except OSError as e:
            InfoDialog(self, "建不了", str(e))
            return
        self.log_line("新建项目：%s" % path)
        self.log_line("  已排好 script.stm / options.stm / 素材文件夹。")
        self.log_line("  custom/gui.py —— 改界面（对话框位置、标题图、标题曲…）")
        self.log_line("  custom/markdown.py —— 加自己的内联标记")
        self.refresh(keep=path)

    def add_project(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="选一个含 script.stm 的项目文件夹")
        if not d:
            return
        if not proj.is_project(d):
            InfoDialog(self, "不是项目", "这个文件夹里没有 script.stm。")
            return
        proj.push_recent(d)
        self.refresh(keep=d)
        self.log_line("已添加：%s" % d)

    def remove_project(self):
        if not self._need():
            return
        p = self.current
        ok = ConfirmDialog(
            self, "移除项目",
            "要把这个项目从列表里移走吗？\n\n"
            "项目：%s\n路径：%s\n\n"
            "注意：不是删除。整个文件夹会被挪到\nprojects\\_trash\\ 下面，随时能拖回来。"
            % (p["title"], p["path"])).result
        if not ok:
            return
        if os.path.normcase(os.path.dirname(p["path"])) != \
                os.path.normcase(proj.PROJECTS_DIR):
            cfg = proj.load_cfg()
            cfg["recent"] = [x for x in cfg.get("recent", [])
                             if os.path.normcase(x) != os.path.normcase(p["path"])]
            proj.save_cfg(cfg)
            self.log_line("已从列表移除（磁盘文件没动）：%s" % p["path"])
        else:
            dst = proj.trash_project(p["path"])
            self.log_line("已挪到回收处：%s" % dst)
        self.current = None
        self.refresh(keep=None)

    def on_mode(self, value):
        ctk.set_appearance_mode({"跟随系统": "system", "浅色": "light",
                                 "深色": "dark"}[value])


# --------------------------------------------------------------------------- #
# 对话框
# --------------------------------------------------------------------------- #
def _classify_line(line):
    """给一行剧本打类型标签，列表里一眼能看出这是什么语句。"""
    import re as _re
    s = line.strip()
    if not s:
        return "空行"
    if s in ("<", ">", "</>"):
        return "块"
    if s.startswith("<--"):
        return "注释"
    if _re.match(r"(?i)^(choose)\s*:", s):
        return "选择支"
    if _re.match(r"(?i)^(question)\b", s):
        return "询问"
    if _re.match(r"(?i)^(if)\b", s):
        return "条件"
    if _re.match(r"(?i)^(else)\s*:", s):
        return "否则"
    if _re.match(r"(?i)^(end(if|choose))\b", s):
        return "收尾"
    if _re.match(r"(?i)^(set)\b", s):
        return "赋值"
    if _re.match(r"^[\w\u4e00-\u9fff]+\s*:\s*$", s):
        return "标签"
    if _re.match(r"^[A-Za-z_][\w.]*\s*\(", s):
        return "调用"
    if _re.match(r"^[^\s=]+\s*=\s*", s):
        return "配置"
    if s.startswith('"'):
        return "旁白"
    if '"' in s:
        return "台词"
    return "其它"


class VisualEditor(ctk.CTkToplevel):
    """行级可视化剧本编辑器：左边带类型标注的行列表，右边改 / 插 / 删。

    直接编辑源文件行，保存前自动留 .bak 备份；不做 AST 回写，所以
    注释、缩进、排版都原样保留，语法检查器照常可用。
    """

    def __init__(self, app, path):
        super().__init__(app)
        self.app = app
        self.path = path
        self.lines = []
        self.title("可视化编辑 —— %s" % os.path.basename(path))
        self.configure(fg_color=BG)
        self.geometry("980x640")
        self.after(60, self._center)
        self.after(140, self.grab_set)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(top, text=path, font=app.f(12), text_color=SUB).pack(side="left")
        for text, fn, hot in [("保存", self.do_save, True),
                              ("语法检查", self.do_check, False),
                              ("刷新", self.reload_file, False)]:
            fg = ACCENT if hot else "transparent"
            tc = "#ffffff" if hot else INK
            bw = 0 if hot else 1
            ctk.CTkButton(top, text=text, width=90, height=32, corner_radius=9,
                          font=app.f(12.5), fg_color=fg, text_color=tc,
                          border_width=bw, border_color=BORDER,
                          hover_color=ACCENT_HOVER if hot else HOVER,
                          command=fn).pack(side="right", padx=(6, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=6)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(body, font=("Microsoft YaHei", 11),
                                  activestyle="dotline", relief="flat")
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.listbox.bind("<Double-Button-1>", lambda e: self.load_into_entry())

        right = ctk.CTkFrame(body, fg_color=CARD, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.tag_label = ctk.CTkLabel(right, text="选中行后编辑", font=app.f(13, True),
                                      text_color=INK, anchor="w")
        self.tag_label.pack(fill="x", padx=14, pady=(14, 4))
        self.entry = ctk.CTkTextbox(right, height=140, font=app.f(12.5))
        self.entry.pack(fill="x", padx=14)

        btns = [("应用到选中行", self.do_replace),
                ("在下方插入", self.do_insert_after),
                ("在上方插入", self.do_insert_before),
                ("删除选中行", self.do_delete)]
        for i, (text, fn) in enumerate(btns):
            hot = (i == 0)
            ctk.CTkButton(right, text=text, height=34, corner_radius=9,
                          font=app.f(12.5),
                          fg_color=ACCENT if hot else "transparent",
                          text_color="#ffffff" if hot else INK,
                          border_width=0 if hot else 1, border_color=BORDER,
                          hover_color=ACCENT_HOVER if hot else HOVER,
                          command=fn).grid(row=i // 2, column=i % 2,
                                           sticky="ew", padx=14, pady=6)
        right.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(1, weight=1)
        self.tip = ctk.CTkLabel(right, text="双击列表行可快速载入。\n保存前会自动备份 .bak。",
                                font=app.f(11.5), text_color=SUB,
                                justify="left", anchor="w")
        self.tip.pack(fill="x", padx=14, pady=(4, 12), side="bottom")
        self.reload_file()

    # ---- 文件 ---- #
    def reload_file(self):
        try:
            with open(self.path, "r", encoding="utf-8-sig") as f:
                self.lines = f.read().splitlines()
        except Exception as e:                         # noqa: BLE001
            self.app.log_line("可视化编辑：读不了 %s（%s）" % (self.path, e))
            self.destroy()
            return
        self.refresh_list(keep=0)

    def refresh_list(self, keep=0):
        self.listbox.delete(0, tk.END)
        for i, ln in enumerate(self.lines, 1):
            self.listbox.insert(tk.END, "%4d │ %-4s │ %s" % (i, _classify_line(ln), ln))
        if self.lines:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(min(keep, len(self.lines) - 1))

    def _sel(self):
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def _entry_text(self):
        return self.entry.get("1.0", "end").rstrip("\n")

    def on_select(self, _e=None):
        i = self._sel()
        if i is not None:
            self.tag_label.configure(text="第 %d 行 · %s" % (i + 1, _classify_line(self.lines[i])))

    def load_into_entry(self):
        i = self._sel()
        if i is not None:
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", self.lines[i])

    def do_replace(self):
        i = self._sel()
        if i is None:
            return
        self.lines[i] = self._entry_text()
        self.refresh_list(keep=i)

    def do_insert_after(self):
        i = self._sel()
        self.lines.insert((i + 1) if i is not None else len(self.lines),
                          self._entry_text())
        self.refresh_list(keep=(i + 1) if i is not None else len(self.lines) - 1)

    def do_insert_before(self):
        i = self._sel()
        self.lines.insert(i if i is not None else 0, self._entry_text())
        self.refresh_list(keep=i if i is not None else 0)

    def do_delete(self):
        i = self._sel()
        if i is None:
            return
        self.lines.pop(i)
        self.refresh_list(keep=i)

    def do_save(self):
        bak = self.path + ".bak"
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8-sig") as f:
                    with open(bak, "w", encoding="utf-8") as g:
                        g.write(f.read())
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.lines) + "\n")
            self.app.log_line("可视化编辑：已保存（备份在 %s）" % bak)
        except Exception as e:                         # noqa: BLE001
            self.app.log_line("可视化编辑：保存失败：%s" % e)

    def do_check(self):
        self.do_save()
        root = os.path.dirname(self.path)
        try:
            r = subprocess.run([sys.executable, os.path.join(proj.ROOT, "tools", "check.py"), root],
                               capture_output=True, text=True, timeout=60)
            out = (r.stdout or r.stderr or "").strip().splitlines()
            tail = "\n".join(out[-12:]) if out else "（没有输出）"
        except Exception as e:                         # noqa: BLE001
            tail = str(e)
        InfoDialog(self.app, "语法检查", tail)


class BaseDialog(ctk.CTkToplevel):
    def __init__(self, master, title, w=420, h=260):
        super().__init__(master)
        self.result = None
        self.title(title)
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.transient(master)
        self.geometry("%dx%d" % (w, h))
        self.after(60, self._center)
        self.after(140, self.grab_set)

    def _center(self):
        try:
            self.update_idletasks()
            px, py = self.master.winfo_rootx(), self.master.winfo_rooty()
            pw, ph = self.master.winfo_width(), self.master.winfo_height()
            x = px + (pw - self.winfo_width()) // 2
            y = py + (ph - self.winfo_height()) // 3
            self.geometry("+%d+%d" % (max(0, x), max(0, y)))
        except Exception:                              # noqa: BLE001
            pass


class InfoDialog(BaseDialog):
    def __init__(self, master, title, text):
        super().__init__(master, title, 430, 210)
        f = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        f.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkButton(f, text="知道了", height=38, corner_radius=10, font=master.f(13),
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self.destroy).pack(side="bottom", fill="x",
                                                 padx=18, pady=18)
        ctk.CTkLabel(f, text=title, font=master.f(15, True), text_color=INK,
                     anchor="w").pack(anchor="w", padx=18, pady=(18, 6))
        ctk.CTkLabel(f, text=text, font=master.f(12.5), text_color=SUB, anchor="w",
                     justify="left", wraplength=350).pack(anchor="w", padx=18)
        self.wait_window(self)


class ConfirmDialog(BaseDialog):
    def __init__(self, master, title, text):
        super().__init__(master, title, 460, 300)
        f = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        f.pack(fill="both", expand=True, padx=14, pady=14)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=18, pady=18)
        ctk.CTkButton(row, text="取消", height=38, corner_radius=10, font=master.f(13),
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      text_color=INK, hover_color=HOVER,
                      command=self.destroy).pack(side="left", expand=True, fill="x")
        ctk.CTkButton(row, text="确定", height=38, corner_radius=10, font=master.f(13),
                      fg_color=DANGER, hover_color="#a33b33",
                      command=self._ok).pack(side="left", expand=True, fill="x",
                                             padx=(10, 0))
        ctk.CTkLabel(f, text=title, font=master.f(15, True), text_color=INK,
                     anchor="w").pack(anchor="w", padx=18, pady=(18, 6))
        ctk.CTkLabel(f, text=text, font=master.f(12.5), text_color=SUB, anchor="w",
                     justify="left", wraplength=380).pack(anchor="w", padx=18)
        self.wait_window(self)

    def _ok(self):
        self.result = True
        self.destroy()


class NewProjectDialog(BaseDialog):
    def __init__(self, master):
        super().__init__(master, "新建项目", 470, 400)
        f = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        f.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(f, text="新建项目", font=master.f(16, True), text_color=INK
                     ).pack(anchor="w", padx=20, pady=(18, 10))

        def field(label, value, values=None):
            ctk.CTkLabel(f, text=label, font=master.f(12.5), text_color=SUB
                         ).pack(anchor="w", padx=20, pady=(6, 2))
            if values:
                w = ctk.CTkOptionMenu(f, values=values, height=36, font=master.f(13))
                w.set(value)
            else:
                w = ctk.CTkEntry(f, height=36, font=master.f(13))
                w.insert(0, value)
            w.pack(fill="x", padx=20)
            return w

        self.e_name = field("项目文件夹名", "my_story")
        self.e_title = field("游戏标题", "我的第一个游戏")
        self.e_size = field("分辨率", "1280x720",
                            ["1280x720", "1920x1080", "1024x576", "854x480", "800x600"])

        ctk.CTkLabel(f, text="会生成 script.stm、options.stm、素材文件夹，\n"
                             "以及 custom/gui.py（改界面）和 custom/markdown.py（改标记）。",
                     font=master.f(11.5), text_color=SUB, justify="left", anchor="w"
                     ).pack(anchor="w", padx=20, pady=(12, 0))

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=20, pady=18)
        ctk.CTkButton(row, text="取消", height=38, corner_radius=10, font=master.f(13),
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      text_color=INK, hover_color=HOVER,
                      command=self.destroy).pack(side="right", expand=True, fill="x",
                                                 padx=(10, 0))
        ctk.CTkButton(row, text="创建", height=38, corner_radius=10, font=master.f(13),
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._ok).pack(side="right", expand=True, fill="x")
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.e_name.focus_set()
        self.wait_window(self)

    def _ok(self):
        name = self.e_name.get().strip()
        if not name:
            self.e_name.configure(border_color=DANGER)
            return
        self.result = {"name": name,
                       "title": self.e_title.get().strip() or name,
                       "size": self.e_size.get()}
        self.destroy()


class HtmlDialog(BaseDialog):
    """发布为 HTML 的选项。"""

    def __init__(self, master):
        super().__init__(master, "发布为 HTML", 500, 470)
        f = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        f.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(f, text="发布为 HTML", font=master.f(16, True), text_color=INK
                     ).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(f, text="产物在 dist/<项目名>_web/，双击 index.html 就能玩。",
                     font=master.f(11.5), text_color=SUB, anchor="w"
                     ).pack(anchor="w", padx=20)

        ctk.CTkLabel(f, text="引擎", font=master.f(12.5), text_color=SUB, anchor="w"
                     ).pack(anchor="w", padx=20, pady=(16, 4))
        self.v_engine = ctk.CTkSegmentedButton(f, values=["WebAssembly", "内置解释器"],
                                               height=34, font=master.f(12.5))
        self.v_engine.set("WebAssembly")
        self.v_engine.pack(fill="x", padx=20)
        ctk.CTkLabel(f, text="WebAssembly：浏览器里跑真正的 Python 引擎，和桌面版一致\n"
                             "（首次打开要联网下一份 Pyodide，约 8MB，之后走缓存）\n"
                             "内置解释器：完全离线，行为一致但引擎版本可能落后",
                     font=master.f(11), text_color=SUB, justify="left", anchor="w"
                     ).pack(anchor="w", padx=20, pady=(6, 0))

        ctk.CTkLabel(f, text="素材", font=master.f(12.5), text_color=SUB, anchor="w"
                     ).pack(anchor="w", padx=20, pady=(14, 4))
        self.v_assets = ctk.CTkSegmentedButton(
            f, values=["assets 目录", "内联单文件", "不带素材"], height=34,
            font=master.f(12.5))
        self.v_assets.set("assets 目录")
        self.v_assets.pack(fill="x", padx=20)
        ctk.CTkLabel(f, text="assets 目录：整个文件夹可以上传到网页\n"
                             "内联单文件：素材全塞进一个 HTML，方便发人（会变大）\n"
                             "不带素材：只出播放器，缺图显示占位块",
                     font=master.f(11), text_color=SUB, justify="left", anchor="w"
                     ).pack(anchor="w", padx=20, pady=(6, 0))

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=20, pady=18)
        ctk.CTkButton(row, text="取消", height=38, corner_radius=10, font=master.f(13),
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      text_color=INK, hover_color=HOVER,
                      command=self.destroy).pack(side="right", expand=True, fill="x",
                                                 padx=(10, 0))
        ctk.CTkButton(row, text="开始发布", height=38, corner_radius=10,
                      font=master.f(13), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._ok).pack(side="right", expand=True, fill="x")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.wait_window(self)

    def _ok(self):
        self.result = {
            "engine": "wasm" if self.v_engine.get() == "WebAssembly" else "js",
            "assets": {"assets 目录": "copy", "内联单文件": "inline",
                       "不带素材": "none"}[self.v_assets.get()],
        }
        self.destroy()


# --------------------------------------------------------------------------- #
def main():
    proj.ensure_dirs()
    app = Launcher()

    def on_close():
        proj.save_cfg(dict(proj.load_cfg(),
                           window="%dx%d" % (app.winfo_width(), app.winfo_height())))
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_close)
    app.log_line("STMG 启动器就绪。左边选项目，右边点按钮。")
    app.log_line("第一次用？点「新建项目」，会生成一份能跑的模板。")
    app.mainloop()


if __name__ == "__main__":
    main()
