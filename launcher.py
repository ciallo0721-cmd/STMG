#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STMG 启动器 —— 管项目、跑游戏、查语法、打包发布。

普通 Python + tkinter 写的（标准库自带，不用装东西）。
之所以不像 Ren'Py 那样用剧本语言自举，是因为启动器要处理文件对话框、
子进程、滚动列表这些活，用 tkinter 反而更短更稳。

双击 STMG启动器.bat，或者：

    .venv\\Scripts\\python.exe launcher.py
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from stmg import project as proj                       # noqa: E402

PY = sys.executable
START = os.path.join(HERE, "start.py")
CHECK = os.path.join(HERE, "tools", "check.py")
PACK = os.path.join(HERE, "stmenc", "start.py")

BG = "#f4f5fa"
CARD = "#ffffff"
LINE = "#d7d9e6"
INK = "#2b2d3a"
SUB = "#7a7d92"
ACCENT = "#4c6ef5"
DANGER = "#d64545"


class Launcher(object):
    def __init__(self, root):
        self.root = root
        self.cfg = proj.load_cfg()
        self.queue = queue.Queue()
        self.busy = False
        self.projects = []
        self.current = None

        root.title("STMG 启动器")
        root.geometry(self.cfg.get("window", "920x640"))
        root.minsize(820, 560)
        root.configure(bg=BG)

        self._init_style()
        self._build()
        self.refresh()
        self.root.after(100, self._poll)

    # ------------------------------------------------------------------ #
    def _init_style(self):
        try:
            import tkinter.font as tkfont
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
                f = tkfont.nametofont(name)
                f.configure(family="Microsoft YaHei UI", size=10)
            tkfont.nametofont("TkHeadingFont").configure(
                family="Microsoft YaHei UI", size=10, weight="bold")
        except Exception:                       # noqa: BLE001 - 字体缺失不影响功能
            pass
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=INK)
        s.configure("Card.TLabel", background=CARD, foreground=INK)
        s.configure("Sub.TLabel", background=CARD, foreground=SUB)
        s.configure("Title.TLabel", background=BG, foreground=INK,
                    font=("Microsoft YaHei UI", 15, "bold"))
        s.configure("TButton", padding=(10, 6))
        s.configure("Go.TButton", padding=(10, 6),
                    background=ACCENT, foreground="white")
        s.map("Go.TButton", background=[("active", "#3b5bdb")])

    def _build(self):
        head = ttk.Frame(self.root, padding=(16, 14, 16, 8))
        head.pack(fill="x")
        ttk.Label(head, text="STMG 启动器", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="Super Text Markdown Galgame",
                  foreground=SUB).pack(side="left", padx=(10, 0), pady=(6, 0))

        body = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        body.pack(fill="both", expand=True)

        # ---- 左：项目列表 ----
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="项目").pack(anchor="w", pady=(0, 6))

        box = tk.Frame(left, bg=LINE, bd=0)
        box.pack(fill="y", expand=True)
        self.listbox = tk.Listbox(box, width=30, bd=0, highlightthickness=0,
                                  activestyle="none", bg=CARD, fg=INK,
                                  selectbackground=ACCENT, selectforeground="white",
                                  font=("Microsoft YaHei UI", 10))
        sb = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        sb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self.on_pick)
        self.listbox.bind("<Double-Button-1>", lambda e: self.run_game())

        row = ttk.Frame(left, padding=(0, 8, 0, 0))
        row.pack(fill="x")
        ttk.Button(row, text="新建项目", command=self.new_project).pack(side="left")
        ttk.Button(row, text="添加...", command=self.add_project).pack(side="left", padx=6)

        # ---- 右：项目卡片 ----
        right = ttk.Frame(body, style="Card.TFrame", padding=16)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))

        self.lbl_title = ttk.Label(right, text="没有选中项目", style="Card.TLabel",
                                   font=("Microsoft YaHei UI", 14, "bold"))
        self.lbl_title.pack(anchor="w")
        self.lbl_path = ttk.Label(right, text="", style="Sub.TLabel", wraplength=520,
                                  justify="left")
        self.lbl_path.pack(anchor="w", pady=(4, 0))
        self.lbl_meta = ttk.Label(right, text="", style="Sub.TLabel")
        self.lbl_meta.pack(anchor="w", pady=(2, 0))

        pad = ttk.Frame(right, style="Card.TFrame", padding=(0, 14, 0, 0))
        pad.pack(fill="x")
        btns = [
            ("启动游戏", self.run_game, "Go.TButton"),
            ("语法检查", self.run_check, "TButton"),
            ("无头试跑", self.run_auto, "TButton"),
            ("打包发布", self.run_pack, "TButton"),
            ("编辑剧本", self.edit_script, "TButton"),
            ("打开文件夹", self.open_folder, "TButton"),
        ]
        grid = ttk.Frame(pad, style="Card.TFrame")
        grid.pack(anchor="w")
        for i, (text, fn, style) in enumerate(btns):
            b = ttk.Button(grid, text=text, command=fn, style=style, width=12)
            b.grid(row=i // 2, column=i % 2, padx=(0, 8), pady=4, sticky="w")

        ttk.Label(pad, text="危险操作", style="Sub.TLabel").pack(anchor="w",
                                                                pady=(14, 2))
        ttk.Button(pad, text="移除项目", command=self.remove_project).pack(anchor="w")

        # ---- 下：日志 ----
        bottom = ttk.Frame(self.root, padding=(16, 0, 16, 14))
        bottom.pack(fill="both")
        bar = ttk.Frame(bottom)
        bar.pack(fill="x")
        ttk.Label(bar, text="输出").pack(side="left")
        ttk.Button(bar, text="清空", command=self.clear_log).pack(side="right")
        self.log = tk.Text(bottom, height=11, bg="#1e2030", fg="#d8dae8",
                           insertbackground="#d8dae8", relief="flat", wrap="word",
                           font=("Consolas", 9), padx=10, pady=8)
        self.log.pack(fill="both", expand=True, pady=(4, 0))
        self.log.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # 数据
    # ------------------------------------------------------------------ #
    def refresh(self, keep=None):
        self.projects = proj.list_projects(self.cfg.get("recent"))
        self.listbox.delete(0, tk.END)
        sel = keep if keep is not None else (self.current or {}).get("path")
        for i, p in enumerate(self.projects):
            mark = "" if os.path.normcase(os.path.dirname(p["path"])) == \
                os.path.normcase(proj.PROJECTS_DIR) else "  (外部)"
            self.listbox.insert(tk.END, "  %s%s" % (p["title"] or p["name"], mark))
            if sel and os.path.normcase(p["path"]) == os.path.normcase(sel):
                self.listbox.selection_set(i)
                self.show(p)
        if self.projects and not sel:
            self.listbox.selection_set(0)
            self.show(self.projects[0])

    def on_pick(self, _event=None):
        s = self.listbox.curselection()
        if s:
            self.show(self.projects[s[0]])

    def show(self, p):
        self.current = p
        self.lbl_title.configure(text=p["title"] or p["name"])
        self.lbl_path.configure(text=p["path"])
        self.lbl_meta.configure(text="%s 修改 · %s 句台词 · %s"
                                     % (p["mtime_text"], p["says"], p["size_text"]))
        proj.push_recent(p["path"])

    # ------------------------------------------------------------------ #
    # 日志
    # ------------------------------------------------------------------ #
    def log_line(self, text):
        self.queue.put(text)

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", tk.END)
        self.log.configure(state="disabled")

    def _poll(self):
        while True:
            try:
                text = self.queue.get_nowait()
            except queue.Empty:
                break
            self.log.configure(state="normal")
            self.log.insert(tk.END, text + "\n")
            self.log.see(tk.END)
            self.log.configure(state="disabled")
        self.root.after(120, self._poll)

    def _run(self, args, title, cwd=None, capture=True):
        """子进程跑东西，输出实时丢进日志。"""
        if self.busy:
            messagebox.showinfo("等一下", "上一个任务还没跑完。")
            return
        self.busy = True
        self.log_line("")
        self.log_line("=" * 58)
        self.log_line("$ " + " ".join('"%s"' % a if " " in a else a
                                      for a in [os.path.basename(args[0])]
                                      + args[1:]))

        def worker():
            try:
                kw = {}
                if capture:
                    kw["stdout"] = subprocess.PIPE
                    kw["stderr"] = subprocess.STDOUT
                p = subprocess.Popen(args, cwd=cwd or HERE,
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
            messagebox.showinfo("先选一个项目", "左边列表里点一个项目。")
            return False
        return True

    # ------------------------------------------------------------------ #
    # 操作
    # ------------------------------------------------------------------ #
    def run_game(self):
        if not self._need():
            return
        script = proj.script_of(self.current["path"])
        self.log_line("启动游戏：%s" % self.current["title"])
        try:
            subprocess.Popen([PY, START, script], cwd=self.current["path"],
                             env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        except Exception as e:                         # noqa: BLE001
            self.log_line("启动失败：%s" % e)

    def run_check(self):
        if not self._need():
            return
        self._run([PY, CHECK, self.current["path"], "--verbose"], "语法检查")

    def run_auto(self):
        if not self._need():
            return
        self._run([PY, START, "--auto", proj.script_of(self.current["path"])],
                  "无头试跑")

    def run_pack(self):
        if not self._need():
            return
        out = os.path.join(HERE, "dist", self.current["name"])
        self._run([PY, PACK, self.current["path"], "--out", out], "打包发布")

    def edit_script(self):
        if not self._need():
            return
        p = proj.script_of(self.current["path"])
        try:
            os.startfile(p)                            # noqa: S606 - Windows 专用
            self.log_line("已用系统默认编辑器打开：%s" % p)
        except Exception as e:                         # noqa: BLE001
            self.log_line("打不开：%s" % e)

    def open_folder(self):
        if not self._need():
            return
        try:
            os.startfile(self.current["path"])         # noqa: S606
        except Exception as e:                         # noqa: BLE001
            self.log_line("打不开：%s" % e)

    def new_project(self):
        dlg = NewProjectDialog(self.root)
        if not dlg.result:
            return
        try:
            path = proj.create_project(dlg.result["name"], dlg.result["title"],
                                       dlg.result["size"])
        except OSError as e:
            messagebox.showerror("建不了", str(e))
            return
        self.log_line("新建项目：%s" % path)
        self.log_line("  已经把 script.stm / options.stm / 素材文件夹都排好了。")
        self.refresh(keep=path)

    def add_project(self):
        d = filedialog.askdirectory(title="选一个含 script.stm 的项目文件夹")
        if not d:
            return
        if not proj.is_project(d):
            messagebox.showwarning("不是项目", "这个文件夹里没有 script.stm。")
            return
        proj.push_recent(d)
        self.refresh(keep=d)
        self.log_line("已添加：%s" % d)

    def remove_project(self):
        if not self._need():
            return
        p = self.current
        # 破坏性操作：先说清楚动什么，再要一次确认
        ok = messagebox.askyesno(
            "移除项目",
            "要把这个项目从列表里移走吗？\n\n"
            "项目：%s\n路径：%s\n\n"
            "注意：不是删除。整个文件夹会被挪到\n"
            "projects\\_trash\\ 下面，随时能拖回来。"
            % (p["title"], p["path"]))
        if not ok:
            return
        if os.path.normcase(os.path.dirname(p["path"])) != \
                os.path.normcase(proj.PROJECTS_DIR):
            # 引擎外的项目，只从列表里摘掉，绝不动磁盘
            cfg = proj.load_cfg()
            cfg["recent"] = [x for x in cfg.get("recent", [])
                             if os.path.normcase(x) != os.path.normcase(p["path"])]
            proj.save_cfg(cfg)
            self.log_line("已从列表移除（磁盘文件没动）：%s" % p["path"])
        else:
            dst = proj.trash_project(p["path"])
            self.log_line("已挪到回收处：%s" % dst)
        self.refresh(keep=None)


class NewProjectDialog(tk.Toplevel):
    def __init__(self, master):
        tk.Toplevel.__init__(self, master)
        self.title("新建项目")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.result = None
        self.transient(master)
        self.grab_set()

        f = ttk.Frame(self, padding=18)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="项目文件夹名").grid(row=0, column=0, sticky="w", pady=4)
        self.e_name = ttk.Entry(f, width=30)
        self.e_name.grid(row=0, column=1, pady=4)
        self.e_name.insert(0, "my_story")

        ttk.Label(f, text="游戏标题").grid(row=1, column=0, sticky="w", pady=4)
        self.e_title = ttk.Entry(f, width=30)
        self.e_title.grid(row=1, column=1, pady=4)
        self.e_title.insert(0, "我的第一个游戏")

        ttk.Label(f, text="分辨率").grid(row=2, column=0, sticky="w", pady=4)
        self.e_size = ttk.Combobox(f, width=27, state="readonly",
                                   values=["1280x720", "1920x1080",
                                           "854x480", "800x600", "1024x576"])
        self.e_size.current(0)
        self.e_size.grid(row=2, column=1, pady=4)

        ttk.Label(f, text="会自动生成 script.stm、options.stm 和素材文件夹。",
                  foreground=SUB).grid(row=3, column=0, columnspan=2,
                                       sticky="w", pady=(10, 0))
        btns = ttk.Frame(f)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="创建", style="Go.TButton",
                   command=self.ok).pack(side="right", padx=6)

        self.e_name.focus_set()
        self.bind("<Return>", lambda _e: self.ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.wait_window(self)

    def ok(self):
        name = self.e_name.get().strip()
        if not name:
            messagebox.showwarning("还差一步", "项目文件夹名不能为空。", parent=self)
            return
        self.result = {"name": name,
                       "title": self.e_title.get().strip() or name,
                       "size": self.e_size.get()}
        self.destroy()


def main():
    proj.ensure_dirs()
    root = tk.Tk()
    app = Launcher(root)

    def on_close():
        proj.save_cfg(dict(proj.load_cfg(),
                           window="%dx%d" % (root.winfo_width(), root.winfo_height())))
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    app.log_line("STMG 启动器就绪。左边选项目，右边点按钮。")
    app.log_line("第一次用？点「新建项目」，会自动生成一份能跑的模板。")
    root.mainloop()


if __name__ == "__main__":
    main()
