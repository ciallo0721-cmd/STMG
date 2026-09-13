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
import re
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
        # 不在按钮回调里同步建窗口：挪到 after 里，卡死/报错都能定位
        self.log_line("可视化编辑：准备打开 %s" % p)
        self.after(10, self._open_visual_editor, p)

    def _open_visual_editor(self, p):
        try:
            ed = VisualEditor(self, p)
            self._editor = ed          # 持住引用，防止窗口被垃圾回收
            n = len(ed.lines) if hasattr(ed, "lines") else -1
            self.log_line("可视化编辑：窗口已创建，加载 %d 行（若此条没出现就是建窗口时卡住/报错）" % n)
        except Exception as e:                         # noqa: BLE001
            # tkinter 回调异常只进 stderr，玩家看不到——这里兜底写进日志
            self.log_line("可视化编辑打不开：%s: %s" % (type(e).__name__, e))

    def report_callback_exception(self, exc, val, tb):
        """tkinter 回调的任何未捕获异常，直接写进日志区（不再只进 stderr）。"""
        import traceback as _tb
        self.log_line("回调异常：%s: %s | %s"
                      % (type(val).__name__, val,
                         _tb.format_tb(tb)[-1].strip() if tb else ""))

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


class BaseDialog(ctk.CTkToplevel):
    def __init__(self, master, title, w=420, h=260):
        # 禁用 CTk 的 Windows 标题栏 withdraw 杂技（会把窗口藏起来不还）
        self._deactivate_windows_window_header_manipulation = True
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


class VisualEditor(BaseDialog):
    """行级可视化剧本编辑器：左边带类型标注的行列表，右边改 / 插 / 删。

    直接编辑源文件行，保存前自动留 .bak 备份；不做 AST 回写，所以
    注释、缩进、排版都原样保留，语法检查器照常可用。
    """

    def __init__(self, app, path):
        # CTk 在 Windows 上改标题栏深色时会 withdraw 整个窗口再择机恢复；
        # 外观模式回调会在窗口显示并 grab 之后再次触发这个流程，把窗口
        # 永久藏起来（grab 还握着 → 整个应用点哪都没反应）。
        # 编辑器直接禁用这套标题栏杂技：代价只是标题栏保持浅色。
        self._deactivate_windows_window_header_manipulation = True
        super().__init__(app, "可视化编辑 —— %s" % os.path.basename(path), 980, 640)
        self.app = app
        self.path = path
        self.lines = []
        self.mode = "line"          # line=行级 / blocks=积木 / code=半代码
        self._blk_sel = None        # 积木模式下选中的块下标
        self.app.log_line("可视化编辑：①窗口基座 OK")
        self.resizable(True, True)
        self._build_ui()
        self.app.log_line("可视化编辑：②组件搭建 OK")
        self.reload_file()
        # grab 保险：窗口销毁时必须释放模态 grab，否则整个应用点哪都没反应
        self.bind("<Destroy>", self._safe_destroy, add="+")
        self.after(300, self._grab_status)
        # 显示保险：万一窗口又被 CTk 藏起来，强制拉回；拉不回就放手 grab
        for ms in (400, 900, 1500):
            self.after(ms, self._ensure_visible)

    # ------------------------------------------------------------------ #
    # 模式切换与整体布局
    # ------------------------------------------------------------------ #
    def _set_mode(self, mode):
        if mode == self.mode:
            return
        if self.mode == "blocks":
            self._blk_sync_back()       # 离开积木模式前把树写回行
        self.mode = mode
        self._build_ui()

    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()
        app = self.app
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(top, text=self.path, font=app.f(12), text_color=SUB
                     ).pack(side="left")
        for text, fn, hot in [("保存", self.do_save, True),
                              ("语法检查", self.do_check, False),
                              ("刷新", self.reload_file, False)]:
            ctk.CTkButton(top, text=text, width=84, height=32, corner_radius=9,
                          font=app.f(12.5), fg_color=ACCENT if hot else "transparent",
                          text_color="#ffffff" if hot else INK,
                          border_width=0 if hot else 1, border_color=BORDER,
                          hover_color=ACCENT_HOVER if hot else HOVER,
                          command=fn).pack(side="right", padx=(6, 0))
        # 三种编辑模式：行级 / 拖拽积木 / 半代码
        for m, label in (("code", "半代码"), ("blocks", "拖拽积木"), ("line", "行级")):
            hot = self.mode == m
            ctk.CTkButton(top, text=("● " if hot else "") + label, width=92,
                          height=32, corner_radius=9, font=app.f(12.5),
                          fg_color=ACCENT if hot else "transparent",
                          text_color="#ffffff" if hot else INK,
                          border_width=0 if hot else 1, border_color=BORDER,
                          hover_color=ACCENT_HOVER if hot else HOVER,
                          command=lambda m=m: self._set_mode(m)
                          ).pack(side="right", padx=(6, 0))

        if self.mode == "blocks":
            self._build_block_body()
        elif self.mode == "code":
            self._build_code_body()
        else:
            self._build_line_body()

    def _build_line_body(self):
        app = self.app
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=6)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(body, font=("Microsoft YaHei", 11),
                                  activestyle="dotbox", relief="flat")
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

        bgrid = ctk.CTkFrame(right, fg_color="transparent")
        bgrid.pack(fill="x", padx=14, pady=6)
        bgrid.grid_columnconfigure(0, weight=1)
        bgrid.grid_columnconfigure(1, weight=1)
        btns = [("应用到选中行", self.do_replace),
                ("在下方插入", self.do_insert_after),
                ("在上方插入", self.do_insert_before),
                ("删除选中行", self.do_delete)]
        for i, (text, fn) in enumerate(btns):
            hot = (i == 0)
            ctk.CTkButton(bgrid, text=text, height=34, corner_radius=9,
                          font=app.f(12.5),
                          fg_color=ACCENT if hot else "transparent",
                          text_color="#ffffff" if hot else INK,
                          border_width=0 if hot else 1, border_color=BORDER,
                          hover_color=ACCENT_HOVER if hot else HOVER,
                          command=fn).grid(row=i // 2, column=i % 2,
                                           sticky="ew", padx=4, pady=5)
        self.tip = ctk.CTkLabel(right, text="双击列表行可快速载入。\n保存前会自动备份 .bak。",
                                font=app.f(11.5), text_color=SUB,
                                justify="left", anchor="w")
        self.tip.pack(fill="x", padx=14, pady=(4, 12), side="bottom")
        self.refresh_list(0)

    def _ensure_visible(self):
        try:
            if self.state() == "withdrawn":
                self.deiconify()
                self.lift()
                self.focus_force()
                self.app.log_line("可视化编辑：检测到窗口被隐藏，已强制显示")
        except Exception:                              # noqa: BLE001
            pass
        try:
            if not self.winfo_viewable():
                self.grab_release()                    # 宁可不要模态，也不能锁死应用
                self.app.log_line("可视化编辑：窗口不可见，已释放模态锁")
        except Exception:                              # noqa: BLE001
            pass

    def _grab_status(self):
        try:
            self.app.log_line("可视化编辑：grab 归属 = %s" % (self.grab_current(),))
        except Exception as e:                         # noqa: BLE001
            self.app.log_line("可视化编辑：grab 查询失败 %r" % e)

    def _safe_destroy(self, ev=None):
        if ev is not None and ev.widget is not self:
            return      # 子组件销毁也会冒泡，只在自己销毁时处理
        try:
            self.grab_release()
        except Exception:                              # noqa: BLE001
            pass
        try:
            self.app.log_line("可视化编辑：窗口已关闭")
        except Exception:                              # noqa: BLE001
            pass

    # ---- 文件 ---- #
    def reload_file(self):
        try:
            with open(self.path, "r", encoding="utf-8-sig") as f:
                self.lines = f.read().splitlines()
        except Exception as e:                         # noqa: BLE001
            self.app.log_line("可视化编辑：读不了 %s（%s）" % (self.path, e))
            self.destroy()
            return
        if self.mode == "blocks":
            self._tree_from_lines()
            self._canvas_render()
            self.app.log_line("可视化编辑：③已加载 %d 行" % len(self.lines))
        elif self.mode == "code":
            self._fill_code()
            self.app.log_line("可视化编辑：③已加载 %d 行" % len(self.lines))
        else:
            self.refresh_list(0)
            self.app.log_line("可视化编辑：③已加载 %d 行" % len(self.lines))

    def refresh_list(self, keep=0):
        self.listbox.delete(0, tk.END)
        for i, ln in enumerate(self.lines, 1):
            self.listbox.insert(tk.END, "%4d │ %-4s │ %s" % (i, _classify_line(ln), ln))
        if self.lines:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(min(keep, len(self.lines) - 1))

    def _sel(self):
        sel = self.listbox.curselection()
        # browse 模式下鼠标点击只会产生单项；多项只可能是程序叠加，
        # 取最后一项（最近一次 set 的行）。
        return sel[-1] if sel else None

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
        if self.mode == "blocks":
            self._blk_sync_back()
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

    # ------------------------------------------------------------------ #
    # 积木模式（拖拽积木）
    # ------------------------------------------------------------------ #
    def _sections(self):
        """按顶层 < > 把文件切段，返回 [(内容起始行, 内容结束行)]（不含标记行）。"""
        secs, start = [], None
        for i, ln in enumerate(self.lines):
            s = ln.strip()
            if s == "<" and start is None:
                start = i
            elif s in (">", "</>") and start is not None:
                secs.append((start + 1, i))
                start = None
        return secs

    def _find_secs(self):
        """找出 头部 / 正文(带 Start:) / 结局 三段。"""
        secs = self._sections()
        header = body = ending = None
        for a, b in secs:
            chunk = "\n".join(self.lines[a:b])
            if re.search(r"^\s*Start\s*:", chunk, re.M):
                body = (a, b)
            elif header is None and body is None:
                header = (a, b)
        for a, b in reversed(secs):
            if (a, b) != body and (a, b) != header:
                ending = (a, b)
                break
        return header, body, ending

    def _analyze_blocks(self):
        """正文按缩进切成顶层积木块。块 = {start, end(不含), kind}，span 含子块。"""
        _h, body, _e = self._find_secs()
        blocks = []
        if not body:
            return body, blocks
        a, b = body
        i = a
        while i < b:
            ln = self.lines[i]
            if not ln.strip():
                i += 1
                continue
            ind = len(ln) - len(ln.lstrip(" \t"))
            if ind > 0:                      # 没块头的缩进行：并入上一块
                if blocks and blocks[-1]["end"] == i:
                    blocks[-1]["end"] = i + 1
                i += 1
                continue
            j = i + 1
            while j < b:
                l2 = self.lines[j]
                if not l2.strip():
                    j += 1
                    continue
                if len(l2) - len(l2.lstrip(" \t")) > 0:
                    j += 1
                    continue
                break
            kind = _classify_line(ln)
            # Choose: 后面同缩进的选项行并进同一块
            if kind == "选择支" and j < b:
                nxt = self.lines[j]
                if re.match(r'^\s*"[^"]*"\s*[:：]', nxt) and \
                        len(nxt) - len(nxt.lstrip(" \t")) == 0:
                    k = j + 1
                    while k < b and re.match(r'^\s*"[^"]*"\s*[:：]', self.lines[k]):
                        k += 1
                    j = k
                    kind = "选择支"
            blocks.append({"start": i, "end": j, "kind": kind})
            i = j
        return body, blocks

    _BLK_COLOR = {"标签": "#5b7cfa", "选择支": "#8e6ff0", "条件": "#8e6ff0",
                  "询问": "#3a9d6e", "赋值": "#c98a2d", "调用": "#4a90c4",
                  "旁白": "#3a9d6e", "台词": "#3a9d6e", "注释": "#98a0b8",
                  "配置": "#98a0b8", "其它": "#98a0b8"}

    def _blk_desc(self, blk):
        ln = self.lines[blk["start"]].strip()
        kind = blk["kind"]
        if kind == "标签":
            name = ln.rstrip(":").strip()
            if name.lower() == "start":
                return "当启动 start.py / bat 时"
            return "当接收到「%s」时" % name
        if kind == "选择支":
            return "让玩家选择（%d 行）" % (blk["end"] - blk["start"])
        if kind == "条件":
            return "如果满足条件（%d 行）" % (blk["end"] - blk["start"])
        if kind == "询问":
            return "询问玩家输入"
        if kind == "赋值":
            return "设置变量：" + ln
        if kind == "旁白":
            return "旁白：" + ln.strip('"')[:16]
        if kind == "台词":
            m = re.match(r'^(?P<who>[^"\s][^"]*?)\s*[:：]?\s*(?P<text>".*)$', ln)
            if m:
                return "%s 说：%s" % (m.group("who"),
                                      m.group("text").strip('"')[:14])
            return "台词：" + ln[:16]
        if kind == "调用":
            return "执行：" + ln[:22]
        return ln[:20] if ln else kind

    def _build_block_body(self):
        app = self.app
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=6)
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        # 左：积木箱（按分类竖排）
        palette = ctk.CTkScrollableFrame(body, width=186, label_text="积木箱",
                                         label_font=app.f(12, True))
        palette.grid(row=0, column=0, rowspan=2, sticky="nsew")
        specs = [
            ("开始（帽子积木）", [
                ("当接收到「消息」", lambda: {"t": "hat", "label": "消息N",
                                              "emit": True, "stack": []}),
            ]),
            ("台词（动作积木）", [
                ("旁白", lambda: {"t": "say", "who": "", "text": "这里"}),
                ("角色说话", lambda: {"t": "say", "who": "角色", "text": "这里"}),
            ]),
            ("舞台（动作积木）", [
                ("换背景", lambda: {"t": "call", "raw": 'S.cg("bg/这里.png")'}),
                ("叠图片", lambda: {"t": "call", "raw": 'S.picture("png/这里.png")'}),
                ("立绘登场", lambda: {"t": "call", "raw": 'S.character("png/这里.png")'}),
                ("清空立绘", lambda: {"t": "call", "raw": 'S.hide("all")'}),
            ]),
            ("音频（动作积木）", [
                ("BGM", lambda: {"t": "call", "raw": 'S.play("music/这里.mp3")'}),
                ("音效", lambda: {"t": "call", "raw": 'S.sound("music/这里.wav")'}),
                ("语音", lambda: {"t": "call", "raw": 'S.voice("music/这里.wav")'}),
                ("停 BGM", lambda: {"t": "call", "raw": 'S.stop("bgm")'}),
            ]),
            ("变量（红色积木）", [
                ("设置变量", lambda: {"t": "set", "raw": "SET 好感度 = 0"}),
            ]),
            ("控制（C形积木）", [
                ("选择支", lambda: {"t": "choose", "options": ["选项A", "选项B"]}),
                ("如果…", lambda: {"t": "if", "cond": '"选项A"', "stack": []}),
                ("否则…", lambda: {"t": "else", "stack": []}),
                ("跳到标签", lambda: {"t": "call", "raw": 'S.jump("消息N")'}),
                ("结束游戏", lambda: {"t": "call", "raw": "S.end()"}),
            ]),
            ("询问（动作积木）", [
                ("问玩家问题", lambda: {"t": "question", "raw": 'STM.Q = "这里"'}),
            ]),
        ]
        for cat, items in specs:
            ctk.CTkLabel(palette, text=cat, font=app.f(11.5, True), text_color=INK,
                         anchor="w").pack(fill="x", padx=6, pady=(8, 2))
            for label, mk in items:
                btn = ctk.CTkButton(palette, text="≡ " + label, height=26,
                                    corner_radius=7, font=app.f(11), anchor="w",
                                    fg_color="transparent", text_color=INK,
                                    border_width=1, border_color=BORDER,
                                    hover_color=HOVER)
                btn.pack(fill="x", padx=6, pady=2)
                btn.bind("<ButtonPress-1>", lambda e, mk=mk: self._pal_press(mk))
                btn.bind("<B1-Motion>", self._pal_motion)
                btn.bind("<ButtonRelease-1>", self._pal_release)

        # 上：提示条 + end 部分
        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        ctk.CTkLabel(bar, text="从左边拖积木进来 · 拖积木可挪位置 · 双击改内容 · 右键删除",
                     font=app.f(11), text_color=SUB).pack(side="left")
        ctk.CTkButton(bar, text="end 部分…", width=92, height=26, corner_radius=7,
                      font=app.f(11.5), fg_color="transparent", text_color=INK,
                      border_width=1, border_color=BORDER, hover_color=HOVER,
                      command=self._edit_ending).pack(side="right")

        # 中：无限画布（tkinter.Canvas 手绘积木）
        self.canvas = tk.Canvas(body, bg="#f4f5f9", highlightthickness=0)
        self.canvas.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        self.canvas.bind("<Button-1>", self._cv_press)
        self.canvas.bind("<B1-Motion>", self._cv_motion)
        self.canvas.bind("<ButtonRelease-1>", self._cv_release)
        self.canvas.bind("<Double-Button-1>", self._cv_double)
        self.canvas.bind("<Button-3>", self._cv_right)
        self.canvas.bind("<MouseWheel>", self._cv_wheel)
        self._tree_from_lines()
        self._canvas_render()

    def _refresh_blocks(self):
        import re as _re  # noqa: F401  (re 已在模块级)
        for w in self.blk_list.winfo_children():
            w.destroy()
        app = self.app
        body, blocks = self._analyze_blocks()
        _h, _b, ending = self._find_secs()

        def row(i, blk):
            color = self._BLK_COLOR.get(blk["kind"], "#98a0b8")
            sel = (self._blk_sel == i)
            card = ctk.CTkFrame(self.blk_list, fg_color=HOVER if sel else CARD,
                                corner_radius=10,
                                border_width=2 if sel else 1,
                                border_color=ACCENT if sel else BORDER)
            card.pack(fill="x", padx=6, pady=4)
            bar = ctk.CTkFrame(card, fg_color=color, corner_radius=6, width=6)
            bar.pack(side="left", fill="y", padx=(8, 6), pady=8)
            ctk.CTkLabel(card, text=self._blk_desc(blk), font=app.f(12.5),
                         text_color=INK, anchor="w").pack(side="left", fill="x",
                                                          expand=True, padx=2)
            for sym, fn in (("↑", lambda i=i: self._blk_move(i, -1)),
                            ("↓", lambda i=i: self._blk_move(i, 1)),
                            ("✕", lambda i=i: self._blk_del(i))):
                ctk.CTkButton(card, text=sym, width=30, height=26,
                              corner_radius=7, font=app.f(12),
                              fg_color="transparent", text_color=SUB,
                              hover_color=HOVER, command=fn
                              ).pack(side="right", padx=2, pady=6)
            card.bind("<Button-1>", lambda e, i=i: self._blk_pick(i))

        for i, blk in enumerate(blocks):
            row(i, blk)

        # 结局段：当 end 部分结束时
        endcard = ctk.CTkFrame(self.blk_list, fg_color=CARD, corner_radius=10,
                               border_width=1, border_color=BORDER)
        endcard.pack(fill="x", padx=6, pady=(12, 4))
        ctk.CTkFrame(endcard, fg_color="#6b5bb5", corner_radius=6, width=6
                     ).pack(side="left", fill="y", padx=(8, 6), pady=8)
        txt = "当 end 部分结束时" if ending else "还没有 end 部分（结局画面）"
        ctk.CTkLabel(endcard, text=txt, font=app.f(12.5), text_color=INK,
                     anchor="w").pack(side="left", fill="x", expand=True, padx=2)
        ctk.CTkButton(endcard, text="编辑" if ending else "＋新建", width=64,
                      height=26, corner_radius=7, font=app.f(12),
                      fg_color="transparent", text_color=INK, border_width=1,
                      border_color=BORDER, hover_color=HOVER,
                      command=self._edit_ending).pack(side="right", padx=6, pady=6)

        hint = ctk.CTkLabel(self.blk_list,
                            text="点左边积木添加 · ↑↓ 调顺序 · ✕ 删除 · 点积木选中\n"
                                 "改台词内容：切「行级」双击那行 · 保存前自动 .bak",
                            font=app.f(11), text_color=SUB, justify="left")
        hint.pack(fill="x", padx=8, pady=8)

    def _blk_pick(self, i):
        self._blk_sel = i
        self._refresh_blocks()

    def _blk_insert_pos(self):
        body, blocks = self._analyze_blocks()
        if self._blk_sel is not None and 0 <= self._blk_sel < len(blocks):
            return blocks[self._blk_sel]["end"]
        return body[1] if body else len(self.lines)

    def _blk_add(self, template):
        """把调色板积木插到选中块之后（没选中就插到正文末尾）。"""
        pos = self._blk_insert_pos()
        n_msg = len([l for l in self.lines if re.match(r"^\s*消息\d+\s*:", l)])
        lines = []
        for t in template:
            t = t.replace("消息N", "消息%d" % (n_msg + 1))
            lines.append(t)
        self.lines[pos:pos] = lines
        self._blk_sel = None
        self._refresh_blocks()

    def _blk_move(self, i, delta):
        _body, blocks = self._analyze_blocks()
        j = i + delta
        if not (0 <= j < len(blocks)):
            return
        a, b = blocks[i]["start"], blocks[i]["end"]
        c, d = blocks[j]["start"], blocks[j]["end"]
        s1, e1, s2, e2 = min(a, c), min(b, d), max(a, c), max(b, d)
        mid = self.lines[e1:s2]
        span_a = self.lines[a:b]
        span_b = self.lines[c:d]
        self.lines[s1:e2] = (span_b if i < j else span_a) + mid + \
                            (span_a if i < j else span_b)
        self._blk_sel = j
        self._refresh_blocks()

    def _blk_del(self, i):
        _body, blocks = self._analyze_blocks()
        if not (0 <= i < len(blocks)):
            return
        del self.lines[blocks[i]["start"]:blocks[i]["end"]]
        self._blk_sel = None
        self._refresh_blocks()

    def _edit_ending(self):
        _h, _b, ending = self._find_secs()
        if ending:
            a, b = ending
            EndEditDialog(self.app, self, a, b)
        else:
            # 没有结局段：追加一段新的
            self.lines += ["<", '"感谢游玩"', ">"]
            self._refresh_blocks()

    # ------------------------------------------------------------------ #
    # 积木画布：树模型 ↔ .stm 行，Canvas 手绘 + 拖拽
    # ------------------------------------------------------------------ #
    _CV_COLORS = {"say": "#8e6ff0", "call": "#5b8def", "set": "#d4537e",
                  "comment": "#9aa0b0", "question": "#3a9d6e"}
    _CV_HAT = "#f0c33c"      # 事件黄
    _CV_CTRL = "#ef8f3c"     # 控制橙

    def _tree_from_lines(self):
        """把正文段解析成积木树：帽子(标签) → 堆叠(动作/C形)。"""
        _h, body, _e = self._find_secs()
        self._tree = []
        cur = {"t": "hat", "label": "", "emit": False, "stack": []}
        self._tree.append(cur)

        if body:
            a, b = body
            i = a
            while i < b:
                ln = self.lines[i]
                if not ln.strip():
                    i += 1
                    continue
                s = ln.strip()
                m = re.match(r"^([\w\u4e00-\u9fff]+)\s*:\s*$", s)
                if m and len(ln) - len(ln.lstrip(" \t")) == 0 \
                        and m.group(1).lower() not in (
                            "choose", "if", "else", "question", "set",
                            "endif", "endchoose"):
                    cur = {"t": "hat", "label": m.group(1), "emit": True,
                           "stack": []}
                    self._tree.append(cur)
                    i += 1
                    continue
                node, i = self._parse_stmt(i, b, len(ln) - len(ln.lstrip(" \t")))
                if node:
                    cur["stack"].append(node)
        if len(self._tree) == 1 and not self._tree[0]["stack"] \
                and not self._tree[0]["emit"]:
            self._tree[0]["label"] = "Start"      # 空剧本给个默认帽子

    def _parse_stack(self, i, end, base):
        """解析 [i,end) 中缩进 > base 的连续语句（C 形积木的肚子里）。"""
        out = []
        while i < end:
            ln = self.lines[i]
            if not ln.strip():
                i += 1
                continue
            ind = len(ln) - len(ln.lstrip(" \t"))
            if ind <= base:
                break
            node, i = self._parse_stmt(i, end, ind)
            if node:
                out.append(node)
        return out, i

    def _parse_stmt(self, i, end, ind):
        """解析一条语句（含 C 形的子堆叠），返回 (node, 下一行号)。"""
        s = self.lines[i].strip()
        low = s.lower()
        if low == "choose:":
            i += 1
            opts = []
            while i < end:
                l2 = self.lines[i].strip()
                if not l2:
                    i += 1
                    continue
                if re.match(r'^"[^"]*"(?::"([^"]*)")*\s*:?\s*$', l2) or \
                        re.match(r'^(?:"[^"]*"\s*[:：]?)+$', l2):
                    opts += re.findall(r'"([^"]*)"', l2)
                    i += 1
                    continue
                break
            return {"t": "choose", "options": opts}, i
        if low.startswith("if ") and low.endswith(":"):
            kids, j = self._parse_stack(i + 1, end, ind)
            return {"t": "if", "cond": s[3:-1].strip(), "stack": kids}, j
        if low == "else:":
            kids, j = self._parse_stack(i + 1, end, ind)
            return {"t": "else", "stack": kids}, j
        if s.startswith("<--"):
            return {"t": "comment", "raw": s}, i + 1
        if low.startswith("stm.q"):
            node = {"t": "question", "raw": s}
            i += 1
            while i < end and not self.lines[i].strip():
                i += 1
            if i < end and self.lines[i].strip().lower() == "question:":
                node["has_q"] = True
                i += 1
            return node, i
        if low.startswith("set ") or re.match(r"^[\w.\u4e00-\u9fff]+\s*=\s*", s) \
                and "=" in s and not s.startswith('"'):
            return {"t": "set", "raw": s}, i + 1
        if s.startswith('"'):
            return {"t": "say", "who": "", "text": s.strip('"')}, i + 1
        m = re.match(r'^(?P<who>[^"\s][^"]*?)\s*[:：]\s*(?P<text>".*)$', s)
        if m:
            return {"t": "say", "who": m.group("who"),
                    "text": m.group("text").strip('"')}, i + 1
        return {"t": "call", "raw": s}, i + 1

    def _tree_to_body_lines(self):
        out = []
        for hat in self._tree:
            if hat.get("emit", True):
                out.append(hat["label"] + ":")
            for n in hat["stack"]:
                self._emit_node(n, 0, out)
        return out

    def _emit_node(self, node, ind, out):
        pad = "    " * ind
        t = node["t"]
        if t == "hat":
            if node.get("emit", True):
                out.append(pad + node["label"] + ":")
            for n in node["stack"]:
                self._emit_node(n, ind, out)
        elif t == "say":
            txt = node.get("text", "").replace('"', "")
            out.append(pad + (node["who"] + '"' + txt + '"'
                              if node.get("who") else '"' + txt + '"'))
        elif t == "question":
            out.append(pad + node["raw"])
            if node.get("has_q"):
                out.append(pad + "Question:")
        elif t == "if":
            out.append(pad + "If " + node["cond"] + ":")
            for n in node["stack"]:
                self._emit_node(n, ind + 1, out)
        elif t == "else":
            out.append(pad + "Else:")
            for n in node["stack"]:
                self._emit_node(n, ind + 1, out)
        elif t == "choose":
            out.append(pad + "Choose:")
            if node["options"]:
                out.append(pad + ":".join('"%s"' % o for o in node["options"]))
        else:                                   # call / set / comment
            out.append(pad + node["raw"])

    def _blk_sync_back(self):
        """把积木树写回 self.lines 的正文段（头/结局段原样保留）。"""
        if not getattr(self, "_tree", None):
            return
        _h, body, _e = self._find_secs()
        if not body:
            return
        a, b = body
        self.lines[a:b] = self._tree_to_body_lines()

    # ---------- 渲染 ---------- #
    def _node_text(self, node):
        t = node["t"]
        if t == "hat":
            if node["label"].lower() == "start":
                return "当启动 start.py / bat 时"
            if not node["label"]:
                return "（开头段落）"
            return "当接收到「%s」时" % node["label"]
        if t == "say":
            return ("%s说：%s" % (node["who"], node["text"]) if node.get("who")
                    else "旁白：%s" % node["text"])
        if t == "call":
            return node["raw"]
        if t == "set":
            return node["raw"]
        if t == "comment":
            return "注释 " + node["raw"].strip("<-> ")
        if t == "question":
            return "问玩家：" + node["raw"].replace("STM.Q = ", "")
        if t == "if":
            return "如果 %s" % node["cond"]
        if t == "else":
            return "否则"
        if t == "choose":
            return "让玩家选择"
        return "?"

    def _canvas_render(self):
        cv = self.canvas
        cv.delete("all")
        rows = max(4, len(self._tree))
        cv.configure(scrollregion=(0, 0, 2200, 320 * rows + 400))
        self._hits = []
        self._zones = []
        x0, y = 24, 20
        self._last_bottom = 0
        for hat in self._tree:
            y = self._draw_hat(hat, x0, y) + 30
            self._last_bottom = y

    def _draw_hat(self, hat, x, y):
        cv = self.canvas
        w = max(170, 18 + 7 * len(self._node_text(hat)))
        cv.create_rectangle(x, y, x + w, y + 24, fill=self._CV_HAT,
                            outline="#b98f1e", width=1)
        cv.create_text(x + 8, y + 12, anchor="w", text=self._node_text(hat),
                       font=("Microsoft YaHei", 10), fill="#1d2030")
        self._hits.append({"x1": x, "y1": y, "x2": x + w, "y2": y + 24,
                           "node": hat, "part": "block"})
        ys = []
        cy = y + 24
        zy0 = cy
        # 先占位再画子块：self._zones 逆序查找时，越里层的堆区越先匹配，
        # 这样积木才能落进 C 形积木的肚子里（而不是被外层堆截胡）。
        zone = {"x1": x, "y1": zy0, "x2": x + 620, "y2": cy + 10,
                "stack": hat["stack"], "ys": ys}
        pos = len(self._zones)
        self._zones.insert(pos, zone)
        for node in hat["stack"]:
            top = cy
            cy = self._draw_node(node, x + 14, cy)
            ys.append(((top + cy) / 2.0, len(ys)))
        zone["y2"] = cy + 10
        if not ys:      # 空堆画个虚线提示
            cv.create_text(x + 24, cy + 12, anchor="w", text="（拖积木到这里）",
                           font=("Microsoft YaHei", 9), fill="#b0b4c4")
        return cy

    def _draw_node(self, node, x, y):
        cv = self.canvas
        t = node["t"]
        if t in ("if", "else"):
            head = ("如果 %s" % node["cond"]) if t == "if" else "否则"
            hw = max(96, 16 + 7 * len(head))
            cv.create_rectangle(x, y, x + hw, y + 20, fill=self._CV_CTRL,
                                outline="#c26a1d", width=1)
            cv.create_text(x + 7, y + 10, anchor="w", text=head,
                           font=("Microsoft YaHei", 10), fill="#ffffff")
            self._hits.append({"x1": x, "y1": y, "x2": x + hw, "y2": y + 20,
                               "node": node, "part": "block"})
            cy = y + 20
            ys = []
            # 同帽子堆：先占位再画子块，让里层堆区优先匹配
            zone = {"x1": x, "y1": y, "x2": x + 560, "y2": cy + 8,
                    "stack": node["stack"], "ys": ys}
            pos = len(self._zones)
            self._zones.insert(pos, zone)
            for child in node["stack"]:
                top = cy
                cy = self._draw_node(child, x + 16, cy)
                ys.append(((top + cy) / 2.0, len(ys)))
            zone["y2"] = cy + 8
            cv.create_line(x + 3, y + 20, x + 3, cy + 6, fill=self._CV_CTRL, width=3)
            cv.create_line(x + 3, cy + 6, x + 26, cy + 6, fill=self._CV_CTRL, width=3)
            return cy + 14
        if t == "choose":
            hw = 108
            cv.create_rectangle(x, y, x + hw, y + 20, fill=self._CV_CTRL,
                                outline="#c26a1d", width=1)
            cv.create_text(x + 7, y + 10, anchor="w", text="让玩家选择",
                           font=("Microsoft YaHei", 10), fill="#ffffff")
            self._hits.append({"x1": x, "y1": y, "x2": x + hw, "y2": y + 20,
                               "node": node, "part": "block"})
            cy = y + 24
            for i, opt in enumerate(node["options"]):
                cv.create_rectangle(x + 14, cy, x + 190, cy + 20,
                                    fill="#f6d8a8", outline="#c26a1d", width=1)
                cv.create_text(x + 22, cy + 10, anchor="w", text="选项：%s" % opt,
                               font=("Microsoft YaHei", 10), fill="#4a2c08")
                self._hits.append({"x1": x + 14, "y1": cy, "x2": x + 190,
                                   "y2": cy + 20, "node": node, "part": "opt",
                                   "idx": i})
                cy += 24
            cv.create_rectangle(x + 14, cy, x + 80, cy + 18, fill="#fbe3c4",
                                outline="#c26a1d", width=1)
            cv.create_text(x + 47, cy + 9, text="＋选项", font=("Microsoft YaHei", 9),
                           fill="#7a4a10")
            self._hits.append({"x1": x + 14, "y1": cy, "x2": x + 80, "y2": cy + 18,
                               "node": node, "part": "addopt"})
            cv.create_line(x + 3, y + 20, x + 3, cy + 20, fill=self._CV_CTRL, width=3)
            return cy + 28
        color = self._CV_COLORS.get(t, "#5b8def")
        label = self._node_text(node)
        w = max(96, 16 + 7 * len(label))
        h = 20
        cv.create_rectangle(x, y, x + w, y + h, fill=color, outline="")
        cv.create_text(x + 8, y + h / 2, anchor="w", text=label,
                       font=("Microsoft YaHei", 10), fill="#ffffff")
        self._hits.append({"x1": x, "y1": y, "x2": x + w, "y2": y + h,
                           "node": node, "part": "block"})
        return y + h + 6

    # ---------- 命中与拖拽 ---------- #
    def _hit_top(self, x, y):
        for h in reversed(self._hits):
            if h["x1"] <= x <= h["x2"] and h["y1"] <= y <= h["y2"]:
                return h
        return None

    def _remove_node(self, node):
        def walk(lst):
            for i, n in enumerate(lst):
                if n is node:
                    return lst, i
                if n["t"] == "hat":
                    r = walk(n["stack"])
                    if r:
                        return r
                elif n["t"] in ("if", "else"):
                    r = walk(n["stack"])
                    if r:
                        return r
            return None
        r = walk(self._tree)
        if r:
            lst, i = r
            lst.pop(i)
            return (lst, i)
        return None

    def _find_drop(self, node, x, y):
        """算 (堆区, 插入序号)；帽子或落空返回 None。"""
        if node["t"] == "hat":
            return None
        for z in reversed(self._zones):
            if z["y1"] - 12 <= y <= z["y2"] + 12:
                idx = sum(1 for cy, _i in z["ys"] if cy < y)
                return z, min(idx, len(z["stack"]))
        return None

    def _drop_node_at(self, node, x, y):
        f = self._find_drop(node, x, y)
        if f is None:
            if node["t"] == "hat":          # 帽子永远在顶层
                self._tree.append(node)
            elif getattr(self, "_drag_origin", None):
                lst, i = self._drag_origin
                lst.insert(i, node)         # 落不进任何堆：弹回原位
            self._canvas_render()
            return
        z, idx = f
        z["stack"].insert(idx, node)
        self._canvas_render()

    # ---------- 放置指示器（白色实线包裹轮廓 + 呼吸动画） ---------- #
    def _drag_start(self):
        self._dragging = True
        self._hint_phase = 0
        try:
            if getattr(self, "_hint_job", None):
                self.after_cancel(self._hint_job)
        except Exception:                      # noqa: BLE001
            pass
        self._hint_job = self.after(180, self._hint_anim)

    def _drag_stop(self):
        self._dragging = False
        try:
            if getattr(self, "_hint_job", None):
                self.after_cancel(self._hint_job)
        except Exception:                      # noqa: BLE001
            pass
        self._hint_job = None
        self.canvas.delete("hint")

    def _hint_anim(self):
        if not getattr(self, "_dragging", False):
            return
        self._hint_phase += 1
        self._hint_draw()
        self._hint_job = self.after(180, self._hint_anim)

    def _show_drop_hint(self, node, x, y):
        cv = self.canvas
        cv.delete("hint")
        f = self._find_drop(node, x, y)
        if f is None:
            if node["t"] == "hat" and getattr(self, "_last_bottom", 0):
                y0 = self._last_bottom + 4
                self._hint_geom = (24, y0, 320, y0 + 28)
            else:
                self._hint_geom = None
                return
        else:
            z, idx = f
            if idx == 0 or not z["ys"]:
                y0 = z["y1"]
            else:
                y0 = z["ys"][idx - 1][0] + 13     # 上一个积木的中点偏下半格
            y0 = max(y0, z["y1"])
            h = 34 if node["t"] in ("if", "else", "choose") else 24
            self._hint_geom = (z["x1"] + 10, y0, z["x1"] + 310, y0 + h)
        self._hint_draw()

    def _hint_draw(self):
        geom = getattr(self, "_hint_geom", None)
        if not geom:
            return
        cv = self.canvas
        cv.delete("hint")
        x1, y1, x2, y2 = geom
        w = 2 if self._hint_phase % 2 == 0 else 4     # 呼吸：线宽一粗一细
        cv.create_rectangle(x1, y1, x2, y2, outline="#ffffff", width=w,
                            tags="hint")
        for cx, cy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            cv.create_rectangle(cx - 3, cy - 3, cx + 3, cy + 3, fill="#ffffff",
                                outline="", tags="hint")

    def _cv_press(self, e):
        x, y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        hit = self._hit_top(x, y)
        if hit and hit["part"] == "block":
            node = hit["node"]
            self._drag_origin = self._remove_node(node)
            self._drag_node = node
            self._drag_start()

    def _cv_motion(self, e):
        node = getattr(self, "_drag_node", None)
        if not node:
            return
        x, y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        self.canvas.delete("ghost")
        self.canvas.create_rectangle(x - 70, y - 11, x + 90, y + 11,
                                     fill="#ffffff", outline=ACCENT,
                                     tags="ghost")
        self.canvas.create_text(x, y, text=self._node_text(node)[:16],
                                font=("Microsoft YaHei", 10), tags="ghost")
        self._show_drop_hint(node, x, y)

    def _cv_release(self, e):
        node = getattr(self, "_drag_node", None)
        if not node:
            return
        self._drag_stop()
        self._drag_node = None
        self._drop_node_at(node, self.canvas.canvasx(e.x),
                           self.canvas.canvasy(e.y))

    def _cv_double(self, e):
        x, y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        hit = self._hit_top(x, y)
        if not hit:
            return
        if hit["part"] == "block":
            self._edit_node_dialog(hit["node"])
        elif hit["part"] == "opt":
            node = hit["node"]
            old = node["options"][hit["idx"]]
            EditOneFieldDialog(self.app, "改选项", "选项文字：", old,
                               lambda v: node["options"].__setitem__(
                                   hit["idx"], v) or self._canvas_render())
        elif hit["part"] == "addopt":
            node = hit["node"]
            node["options"].append("新选项")
            self._canvas_render()

    def _cv_right(self, e):
        x, y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        hit = self._hit_top(x, y)
        if hit and hit["part"] == "block":
            self._remove_node(hit["node"])
            self._canvas_render()

    def _cv_wheel(self, e):
        self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

    # ---------- 调色板拖拽 ---------- #
    def _pal_press(self, mk):
        node = mk()
        n = len([h for h in self._tree if h.get("emit")]) if getattr(self, "_tree", None) else 0
        if node.get("label") == "消息N":
            node["label"] = "消息%d" % (n + 1)
        if node.get("raw") and "消息N" in node["raw"]:
            node["raw"] = node["raw"].replace("消息N", "消息%d" % max(1, n))
        self._pal_node = node
        self._drag_start()

    def _pal_motion(self, e):
        node = getattr(self, "_pal_node", None)
        if not node:
            return
        px = e.x_root - self.canvas.winfo_rootx()
        py = e.y_root - self.canvas.winfo_rooty()
        self.canvas.delete("ghost")
        if 0 <= px <= self.canvas.winfo_width() and 0 <= py <= self.canvas.winfo_height():
            self.canvas.create_rectangle(px - 60, py - 10, px + 80, py + 10,
                                         fill="#ffffff", outline=ACCENT,
                                         tags="ghost")
            self.canvas.create_text(px + 10, py, anchor="w",
                                    text=self._node_text(node)[:14],
                                    font=("Microsoft YaHei", 10), tags="ghost")
            self._show_drop_hint(node, self.canvas.canvasx(0) + px,
                                 self.canvas.canvasy(0) + py)

    def _pal_release(self, e):
        node = getattr(self, "_pal_node", None)
        if not node:
            return
        self._pal_node = None
        self._drag_stop()
        px = e.x_root - self.canvas.winfo_rootx()
        py = e.y_root - self.canvas.winfo_rooty()
        # 不做窗口边界检查：落点靠堆区匹配，落不进任何堆就弹回原位
        self._drop_node_at(node, self.canvas.canvasx(0) + px,
                           self.canvas.canvasy(0) + py)

    # ---------- 双击编辑 ---------- #
    def _edit_node_dialog(self, node):
        t = node["t"]
        if t == "say":
            fields = [("角色（留空 = 旁白）", node.get("who", ""), "who"),
                      ("台词", node.get("text", ""), "text")]
        elif t in ("call", "set", "comment"):
            fields = [("内容（一行）", node["raw"], "raw")]
        elif t == "question":
            fields = [("提示文字（STM.Q = …）", node["raw"], "raw")]
        elif t == "if":
            fields = [("条件（如 \"选项A\" 或 好感度 >= 10）", node["cond"], "cond")]
        elif t == "hat":
            if node["label"].lower() == "start":
                self.app.log_line("Start 帽子不用改名喵")
                return
            fields = [("标签名（S.jump 就跳到这里）", node["label"], "label")]
        elif t == "choose":
            node["options"] = node["options"] or ["选项A"]
            fields = [("选项（用逗号分隔）", "，".join(node["options"]), "options")]
        else:
            return
        EditBlockDialog(self.app, node, fields, self)

    def _apply_node_edit(self, node, values):
        for key, val in values:
            if key == "options":
                node["options"] = [o.strip() for o in re.split(r"[，,]", val)
                                   if o.strip()]
            elif key == "text":
                node["text"] = val.replace('"', "")
            elif key == "who":
                node["who"] = val.strip()
            else:
                node[key] = val.strip()
        self._canvas_render()

    # ------------------------------------------------------------------ #
    # 半代码模式
    # ------------------------------------------------------------------ #
    def _build_code_body(self):
        app = self.app
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=6)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.code_box = ctk.CTkTextbox(body, font=("Consolas", 12.5))
        self.code_box.grid(row=0, column=0, sticky="nsew")
        self._fill_code()
        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ctk.CTkLabel(bar, text="直接写 .stm 源码；「应用」后可切回积木/行级继续编辑。",
                     font=app.f(11.5), text_color=SUB).pack(side="left")
        ctk.CTkButton(bar, text="还原", width=80, height=30, corner_radius=9,
                      font=app.f(12.5), fg_color="transparent", text_color=INK,
                      border_width=1, border_color=BORDER, hover_color=HOVER,
                      command=self._fill_code).pack(side="right", padx=(6, 0))
        ctk.CTkButton(bar, text="应用到剧本", width=110, height=30,
                      corner_radius=9, font=app.f(12.5), fg_color=ACCENT,
                      text_color="#ffffff", hover_color=ACCENT_HOVER,
                      command=self._apply_code).pack(side="right")

    def _fill_code(self):
        self.code_box.delete("1.0", "end")
        self.code_box.insert("1.0", "\n".join(self.lines))

    def _apply_code(self):
        txt = self.code_box.get("1.0", "end").rstrip("\n")
        self.lines = txt.splitlines() if txt else []
        self.app.log_line("可视化编辑：半代码已应用（%d 行），记得点「保存」" % len(self.lines))


class EndEditDialog(BaseDialog):
    """编辑「当 end 部分结束时」的结局内容。"""

    def __init__(self, app, editor, a, b):
        self._deactivate_windows_window_header_manipulation = True
        super().__init__(app, "编辑 end 部分（结局画面）", 620, 460)
        self.editor = editor
        self.a, self.b = a, b
        ctk.CTkLabel(self, text="结局在剧本跑完（S.end 或正文结束）后显示。",
                     font=app.f(12), text_color=SUB).pack(anchor="w", padx=16,
                                                          pady=(14, 4))
        self.box = ctk.CTkTextbox(self, font=("Consolas", 13))
        self.box.pack(fill="both", expand=True, padx=16, pady=6)
        self.box.insert("1.0", "\n".join(editor.lines[a:b]))
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(bar, text="取消", width=90, height=34, corner_radius=9,
                      font=app.f(12.5), fg_color="transparent", text_color=INK,
                      border_width=1, border_color=BORDER, hover_color=HOVER,
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(bar, text="保存到剧本", width=120, height=34,
                      corner_radius=9, font=app.f(12.5), fg_color=ACCENT,
                      text_color="#ffffff", hover_color=ACCENT_HOVER,
                      command=self._save).pack(side="right", padx=(0, 8))

    def _save(self):
        txt = self.box.get("1.0", "end").rstrip("\n")
        self.editor.lines[self.a:self.b] = txt.splitlines() if txt else []
        self.editor.app.log_line("可视化编辑：end 部分已更新，记得点「保存」")
        self.destroy()


class EditBlockDialog(BaseDialog):
    """编辑一个积木的字段（say 的角色/台词、if 的条件、choose 的选项…）。"""

    def __init__(self, app, node, fields, editor):
        self._deactivate_windows_window_header_manipulation = True
        super().__init__(app, "编辑积木", 480, 120 + 56 * len(fields))
        self.node = node
        self.editor = editor
        self.vars = []
        ctk.CTkLabel(self, text=self.editor._node_text(node), font=app.f(13, True),
                     text_color=INK, anchor="w").pack(fill="x", padx=18,
                                                      pady=(14, 6))
        for label, initial, key in fields:
            ctk.CTkLabel(self, text=label, font=app.f(12), text_color=SUB,
                         anchor="w").pack(fill="x", padx=18, pady=(4, 0))
            var = ctk.StringVar(value=initial)
            ctk.CTkEntry(self, textvariable=var, font=app.f(12.5)
                         ).pack(fill="x", padx=18, pady=2)
            self.vars.append((key, var))
        ctk.CTkButton(self, text="确定", height=34, corner_radius=9,
                      font=app.f(12.5), fg_color=ACCENT, text_color="#ffffff",
                      hover_color=ACCENT_HOVER, command=self._save
                      ).pack(fill="x", padx=18, pady=(14, 16))

    def _save(self):
        values = [(k, v.get()) for k, v in self.vars]
        self.editor._apply_node_edit(self.node, values)
        self.destroy()


class EditOneFieldDialog(BaseDialog):
    """单字段小对话框（改选项文字等）。"""

    def __init__(self, app, title, label, initial, on_save):
        self._deactivate_windows_window_header_manipulation = True
        super().__init__(app, title, 420, 190)
        self.on_save = on_save
        ctk.CTkLabel(self, text=label, font=app.f(12), text_color=SUB,
                     anchor="w").pack(fill="x", padx=18, pady=(14, 0))
        self.var = ctk.StringVar(value=initial)
        ctk.CTkEntry(self, textvariable=self.var, font=app.f(12.5)
                     ).pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(self, text="确定", height=32, corner_radius=9,
                      font=app.f(12.5), fg_color=ACCENT, text_color="#ffffff",
                      hover_color=ACCENT_HOVER, command=self._save
                      ).pack(fill="x", padx=18, pady=(6, 14))

    def _save(self):
        try:
            self.on_save(self.var.get())
        finally:
            self.destroy()


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
