"""Small Windows GUI and scriptable CLI for the independent installer."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from installer import Installer, manifest
from loaders import KINDS, catalog, find_java, install_loader

HOME = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def detect():
    for folder in (HOME, HOME.parent, Path.cwd()):
        exe = folder / "Plain Craft Launcher 2.exe"
        if exe.is_file():
            setup = folder / "PCL" / "Setup.ini"
            if setup.is_file():
                for line in setup.read_text(encoding="utf-8-sig").splitlines():
                    if line.startswith("LaunchFolderSelect:"):
                        selected = line.split(":", 1)[1]
                        if Path(selected).is_dir():
                            return selected, str(exe)
            return str(folder / ".minecraft"), str(exe)
    return str(Path(os.environ["APPDATA"]) / ".minecraft"), ""


class DownloadProgress(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, height=42, background="#172235", highlightthickness=0)
        self.percent = 0.0
        self.speed = 0.0
        self.caption = "等待下载"
        self.bind("<Configure>", lambda _: self.draw())

    def update_progress(self, completed, total, speed):
        self.percent = min(100.0, max(0.0, completed / total * 100)) if total else None
        self.speed = speed / 1_000_000
        self.caption = "下载中" if speed else "已传输" if total and completed >= total else "等待传输"
        self.draw()

    def stop(self, caption):
        self.speed = 0.0
        self.caption = caption
        self.draw()

    def draw(self):
        self.delete("all")
        width, height = self.winfo_width(), 38
        def rounded(x, y, w, h, color):
            r = min(10, w / 2)
            self.create_polygon(x+r,y,x+w-r,y,x+w,y,x+w,y+r,x+w,y+h-r,x+w,y+h,
                                x+w-r,y+h,x+r,y+h,x,y+h,x,y+h-r,x,y+r,x,y,
                                smooth=True, fill=color, outline="")
        rounded(0, 2, width, height, "#0e1727")
        fill = width * (self.percent or 0) / 100
        if fill > 0:
            rounded(0, 2, fill, height, "#366ac4")
        percent = f"{self.percent:.1f}%" if self.percent is not None else "计算大小中"
        self.create_text(width/2, height/2+2,
                         text=f"{self.caption}   ·   {percent}   ·   {self.speed:.2f} MB/s",
                         fill="#f1f5fc", font=("Microsoft YaHei UI", 11, "bold"))


class App:
    def __init__(self, root):
        self.root = root
        root.title("MC-Mini · 轻量化 MC 下载器")
        root.geometry("980x740")
        root.minsize(850, 650)
        root.configure(background="#101827")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10), background="#101827", foreground="#e5edf9")
        style.configure("TFrame", background="#101827")
        style.configure("Card.TFrame", background="#172235")
        style.configure("TLabel", background="#101827", foreground="#dbe6f7")
        style.configure("Muted.TLabel", foreground="#93a6c3")
        style.configure("Card.TLabel", background="#172235", foreground="#b7c7df")
        style.configure("TEntry", fieldbackground="#101b2d", foreground="#edf3ff", bordercolor="#30435f", padding=7)
        style.configure("TCombobox", fieldbackground="#101b2d", background="#22334e", foreground="#edf3ff", arrowcolor="#a9c7f5", padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", "#101b2d")], foreground=[("readonly", "#edf3ff"), ("disabled", "#6d7f99")])
        root.option_add("*TCombobox*Listbox.background", "#172235")
        root.option_add("*TCombobox*Listbox.foreground", "#edf3ff")
        root.option_add("*TCombobox*Listbox.selectBackground", "#315a91")
        style.configure("TButton", background="#22334e", foreground="#edf3ff", borderwidth=0, padding=(14, 8))
        style.map("TButton", background=[("active", "#304969"), ("disabled", "#1a293f")], foreground=[("disabled", "#62738d")])
        style.configure("Accent.TButton", background="#346cd0", foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", "#4381eb"), ("disabled", "#263b5d")])
        style.configure("Treeview", background="#172235", fieldbackground="#172235", foreground="#e5edf9", borderwidth=0, rowheight=32)
        style.configure("Treeview.Heading", background="#202f47", foreground="#9bb6dd", relief="flat", padding=8)
        style.map("Treeview", background=[("selected", "#284e80")], foreground=[("selected", "#ffffff")])
        style.map("Treeview.Heading", background=[("active", "#293c59")])
        style.configure("Vertical.TScrollbar", background="#314765", troughcolor="#172235", borderwidth=0, arrowcolor="#91a8c9")
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.entries = {}
        self.busy = False
        self.choices = []
        self.loaded_key = None
        self.pending_catalog = False
        folder, exe = detect()
        self.folder, self.exe = tk.StringVar(value=folder), tk.StringVar(value=exe)
        self.source = tk.StringVar(value="BMCLAPI")
        self.filter = tk.StringVar(value="正式版")
        self.search = tk.StringVar()
        self.kind = tk.StringVar(value="原版")
        self.loader_version = tk.StringVar()
        self.java = tk.StringVar(value=find_java())
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill="both", expand=True)
        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(0, 15))
        ttk.Label(header, text="MC-Mini", font=("Microsoft YaHei UI", 24, "bold"), foreground="#f1f6ff").pack(side="left")
        ttk.Label(header, text="轻量化 MC 下载器", style="Muted.TLabel").pack(side="left", padx=15, pady=(9, 0))
        ttk.Label(header, text="●  aria2 下载引擎", foreground="#76d6bf").pack(side="right", pady=(9, 0))
        paths = ttk.Frame(frame, style="Card.TFrame", padding=14)
        paths.pack(fill="x")
        for label, variable, command in (
            ("游戏目录", self.folder, self.pick_folder),
            ("PCL 程序", self.exe, self.pick_exe),
            ("安装用 Java", self.java, self.pick_java),
        ):
            row = ttk.Frame(paths, style="Card.TFrame")
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=11, style="Card.TLabel").pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="浏览", command=command).pack(side="left", padx=(8, 0))
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=14)
        source_box = ttk.Combobox(bar, textvariable=self.source, values=["BMCLAPI", "Mojang"], state="readonly", width=12)
        source_box.pack(side="left")
        source_box.bind("<<ComboboxSelected>>", lambda _: self.selection_changed(force=True))
        category = ttk.Combobox(bar, textvariable=self.filter, values=["正式版", "快照", "历史版", "全部"], state="readonly", width=9)
        category.pack(side="left", padx=8)
        category.bind("<<ComboboxSelected>>", lambda _: self.show_versions())
        self.refresh = ttk.Button(bar, text="刷新版本", command=self.refresh_versions)
        self.refresh.pack(side="left")
        ttk.Entry(bar, textvariable=self.search, width=20).pack(side="right")
        ttk.Label(bar, text="搜索  ", style="Muted.TLabel").pack(side="right")
        self.search.trace_add("write", lambda *_: self.show_versions())
        container = ttk.Frame(frame, style="Card.TFrame")
        container.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(container, columns=("type", "date"), show="tree headings", selectmode="browse", height=6)
        for column, title in (("#0", "Minecraft 版本"), ("type", "版本类型"), ("date", "发布时间")):
            self.tree.heading(column, text=title, anchor="w")
        self.tree.column("#0", width=340)
        self.tree.column("type", width=170)
        self.tree.column("date", width=180)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(container, command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.selection_changed())
        loader_row = ttk.Frame(frame)
        loader_row.pack(fill="x", pady=(14, 8))
        self.kind_box = ttk.Combobox(loader_row, textvariable=self.kind, values=KINDS, state="readonly", width=12)
        self.kind_box.pack(side="left")
        self.kind_box.bind("<<ComboboxSelected>>", lambda _: self.selection_changed())
        self.loader_box = ttk.Combobox(loader_row, textvariable=self.loader_version, state="disabled")
        self.loader_box.pack(side="left", fill="x", expand=True, padx=8)
        self.loader_refresh = ttk.Button(loader_row, text="刷新加载器", command=lambda: self.selection_changed(force=True))
        self.loader_refresh.pack(side="right")
        ttk.Label(frame, text="先选 MC，再选组件版本  ·  OptiFine 独立安装  ·  使用 PCL 登录并启动", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
        footer = ttk.Frame(frame, style="Card.TFrame", padding=14)
        footer.pack(fill="x")
        actions = ttk.Frame(footer, style="Card.TFrame")
        actions.pack(fill="x", pady=(0, 10))
        self.install_button = ttk.Button(actions, text="↓  下载并安装", style="Accent.TButton", command=self.install)
        self.install_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="取消", state="disabled", command=self.cancel.set)
        self.cancel_button.pack(side="left", padx=8)
        ttk.Button(actions, text="打开 PCL  →", command=self.open_pcl).pack(side="right")
        self.progress_bar = DownloadProgress(footer)
        self.progress_bar.pack(fill="x")
        self.status = tk.StringVar(value="刷新版本列表后，选择需要安装的版本。")
        ttk.Label(footer, textvariable=self.status, style="Card.TLabel", wraplength=850).pack(anchor="w", pady=(8, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)
        self.refresh_versions()
        root.after(600000, self.auto_refresh)

    def pick_folder(self):
        if not self.busy:
            value = filedialog.askdirectory(initialdir=self.folder.get())
            if value:
                self.folder.set(value)

    def pick_exe(self):
        value = filedialog.askopenfilename(filetypes=[("PCL 程序", "*.exe")])
        if value:
            self.exe.set(value)

    def pick_java(self):
        value = filedialog.askopenfilename(title="选择用于安装的 java.exe", filetypes=[("Java", "java.exe")])
        if value:
            self.java.set(value)

    def current_key(self):
        selection = self.tree.selection()
        return (selection[0] if selection else "", self.kind.get(),
                "bmclapi" if self.source.get() == "BMCLAPI" else "official")

    def selection_changed(self, force=False):
        key = self.current_key()
        if not force and self.loaded_key == key:
            return
        self.loaded_key = None
        self.choices = []
        self.loader_version.set("")
        self.loader_box.configure(values=[], state="disabled")
        if self.busy:
            self.pending_catalog = True
            return
        if not key[0] or key[1] == "原版":
            self.loaded_key = key
            return
        self.status.set(f"正在联网获取 {key[0]} 的 {key[1]} 版本…")
        self.start(lambda: self.events.put(("catalog", (key, catalog(key[1], key[0], key[2])))))

    def auto_refresh(self):
        if not self.busy:
            self.refresh_versions()
        self.root.after(600000, self.auto_refresh)

    def start(self, operation):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.refresh.configure(state="disabled")
        self.install_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.loader_refresh.configure(state="disabled")
        def worker():
            try:
                operation()
            except Exception as error:
                self.events.put(("error", str(error)))
            finally:
                self.events.put(("done", None))
        threading.Thread(target=worker, daemon=True).start()

    def refresh_versions(self):
        if self.busy:
            return
        source = "bmclapi" if self.source.get() == "BMCLAPI" else "official"
        self.status.set("正在获取版本列表…")
        self.start(lambda: self.events.put(("manifest", manifest(source))))

    def show_versions(self):
        selection = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        types = {"正式版": {"release"}, "快照": {"snapshot"}, "历史版": {"old_alpha", "old_beta"}}
        for name, entry in self.entries.items():
            if self.search.get().lower() not in name.lower():
                continue
            if self.filter.get() != "全部" and entry["type"] not in types[self.filter.get()]:
                continue
            self.tree.insert("", "end", iid=name, text=name, values=(entry["type"], entry["releaseTime"][:10]))
        if selection and self.tree.exists(selection[0]):
            self.tree.selection_set(selection[0])

    def install(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("选择版本", "请先选择要安装的 Minecraft 版本。")
            return
        entry = self.entries[selection[0]]
        folder = self.folder.get().strip()
        if not folder:
            messagebox.showerror("游戏目录", "请选择游戏目录。")
            return
        source = "bmclapi" if self.source.get() == "BMCLAPI" else "official"
        kind, java = self.kind.get(), self.java.get().strip()
        choice = None
        if kind != "原版":
            index = self.loader_box.current()
            if self.loaded_key != self.current_key() or index < 0:
                messagebox.showinfo("选择加载器", "请等待兼容版本列表加载完成，然后选择一个加载器版本。")
                return
            choice = self.choices[index]
        if kind not in ("原版", "Fabric") and not Path(java).is_file():
            messagebox.showerror("需要 Java", "请选择用于安装的 java.exe。建议使用与该 MC 版本匹配的 Java。")
            return
        self.progress_bar.update_progress(0, 1, 0)
        def operation():
            engine = Installer(folder, source, lambda msg: self.events.put(("log", msg)), self.cancel,
                               lambda done, total, speed: self.events.put(("progress", (done, total, speed))))
            path = install_loader(engine, entry, kind, choice, java)
            self.events.put(("installed", (path.name, str(path.parent.parent))))
        self.start(operation)

    def open_pcl(self):
        path = Path(self.exe.get())
        if not path.is_file() or path.suffix.lower() != ".exe":
            messagebox.showerror("PCL 程序", "请浏览并选择 PCL 的 exe 文件。")
            return
        try:
            subprocess.Popen([str(path.resolve())], cwd=path.resolve().parent)
        except OSError as error:
            messagebox.showerror("无法打开 PCL", str(error))

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == "progress":
                self.progress_bar.update_progress(*value)
            elif kind == "manifest":
                previous = set(self.entries)
                self.entries = {item["id"]: item for item in value["versions"]}
                self.show_versions()
                added = len(set(self.entries) - previous) if previous else 0
                self.status.set(f"{datetime.now():%H:%M:%S} 已更新 {len(self.entries)} 个 MC 版本" +
                                (f"，发现 {added} 个新版本。" if added else "。") +
                                f" 最新正式版 {value['latest']['release']}；快照 {value['latest']['snapshot']}。")
                self.loaded_key = None
                self.pending_catalog = True
            elif kind == "catalog":
                key, choices = value
                if key == self.current_key():
                    self.loaded_key = key
                    self.choices = choices
                    self.loader_box.configure(values=[c["label"] for c in choices],
                                              state="readonly" if choices else "disabled")
                    self.status.set(f"{key[0]} · {key[1]}：找到 {len(choices)} 个版本，请手动选择。" if choices
                                    else f"{key[0]} 暂无可用的 {key[1]} 版本，可改选 MC 或加载器。")
                else:
                    self.pending_catalog = True
            elif kind == "done":
                self.busy = False
                self.refresh.configure(state="normal")
                self.install_button.configure(state="normal")
                self.cancel_button.configure(state="disabled")
                self.loader_refresh.configure(state="normal")
                if self.pending_catalog:
                    self.pending_catalog = False
                    self.root.after(0, self.selection_changed)
            elif kind == "installed":
                name, folder = value
                self.status.set(f"{name} 安装完成。请在 PCL 选择对应游戏目录和版本。")
                self.progress_bar.update_progress(1, 1, 0)
                self.progress_bar.stop("安装完成")
                messagebox.showinfo("安装完成", f"版本：{name}\n游戏目录：{folder}\n\n点击“打开 PCL”，在版本选择中刷新并选择此版本。\n若目录未显示，请先添加上述游戏目录。\n登录账号并点击启动；Java 由 PCL 管理。")
            else:
                self.status.set(value)
                if kind == "error":
                    self.progress_bar.stop("已停止")
                    messagebox.showerror("操作未完成", value + "\n\n可更换下载源后重新安装，完整文件会自动复用。")
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            self.cancel.set()
            self.status.set("正在取消，请等待网络请求结束后关闭窗口。")
        else:
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="MC Mini Minecraft and loader installer")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--install", metavar="VERSION")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--source", choices=["official", "bmclapi"], default="bmclapi")
    parser.add_argument("--loader", choices=KINDS, default="原版")
    parser.add_argument("--loader-version")
    parser.add_argument("--list-loaders", metavar="MC_VERSION")
    parser.add_argument("--java", default=find_java())
    args = parser.parse_args()
    if args.list_loaders:
        for choice in catalog(args.loader, args.list_loaders, args.source):
            print(choice["version"], choice["label"])
        return
    if args.list or args.install:
        data = manifest(args.source)
        if args.list:
            for entry in data["versions"]:
                print(entry["id"], entry["type"])
        if args.install:
            if args.directory is None:
                parser.error("--install requires --directory")
            entries = {entry["id"]: entry for entry in data["versions"]}
            choice = None
            if args.loader != "原版":
                choices = catalog(args.loader, args.install, args.source)
                choice = next((c for c in choices if c["version"] == args.loader_version), None)
                if choice is None:
                    parser.error("Choose an available --loader-version (use --list-loaders)")
            install_loader(Installer(args.directory, args.source), entries[args.install], args.loader, choice, args.java)
    else:
        root = tk.Tk()
        App(root)
        root.mainloop()


if __name__ == "__main__":
    main()
