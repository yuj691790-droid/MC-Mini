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


class App:
    def __init__(self, root):
        self.root = root
        root.title("MC Mini · Minecraft 与加载器安装")
        root.geometry("900x760")
        root.minsize(780, 650)
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
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Minecraft 与加载器安装", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="启动时联网更新；窗口开启期间每 10 分钟刷新。选 MC → 选加载器版本 → 安装 → PCL 启动。").pack(anchor="w", pady=(3, 12))
        for label, variable, command in (
            ("游戏目录", self.folder, self.pick_folder),
            ("PCL 程序", self.exe, self.pick_exe),
            ("安装用 Java", self.java, self.pick_java),
        ):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=10).pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="浏览", command=command).pack(side="left", padx=(6, 0))
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=12)
        source_box = ttk.Combobox(bar, textvariable=self.source, values=["BMCLAPI", "Mojang"], state="readonly", width=12)
        source_box.pack(side="left")
        source_box.bind("<<ComboboxSelected>>", lambda _: self.selection_changed(force=True))
        self.refresh = ttk.Button(bar, text="刷新版本", command=self.refresh_versions)
        self.refresh.pack(side="left", padx=6)
        category = ttk.Combobox(bar, textvariable=self.filter, values=["正式版", "快照", "历史版", "全部"], state="readonly", width=9)
        category.pack(side="left")
        category.bind("<<ComboboxSelected>>", lambda _: self.show_versions())
        ttk.Entry(bar, textvariable=self.search, width=22).pack(side="right")
        ttk.Label(bar, text="搜索版本 ").pack(side="right")
        self.search.trace_add("write", lambda *_: self.show_versions())
        container = ttk.Frame(frame)
        container.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(container, columns=("type", "date"), show="tree headings", selectmode="browse", height=10)
        self.tree.heading("#0", text="版本")
        self.tree.heading("type", text="类型")
        self.tree.heading("date", text="发布时间")
        self.tree.column("#0", width=280)
        self.tree.column("type", width=120)
        self.tree.column("date", width=180)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(container, command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.selection_changed())
        loader_row = ttk.Frame(frame)
        loader_row.pack(fill="x", pady=(10, 0))
        self.kind_box = ttk.Combobox(loader_row, textvariable=self.kind, values=KINDS, state="readonly", width=12)
        self.kind_box.pack(side="left")
        self.kind_box.bind("<<ComboboxSelected>>", lambda _: self.selection_changed())
        self.loader_box = ttk.Combobox(loader_row, textvariable=self.loader_version, state="disabled")
        self.loader_box.pack(side="left", fill="x", expand=True, padx=6)
        self.loader_refresh = ttk.Button(loader_row, text="刷新加载器", command=lambda: self.selection_changed(force=True))
        self.loader_refresh.pack(side="right")
        ttk.Label(frame, text="每次安装一种组件；OptiFine 独立安装，不自动组合 Forge。Forge / NeoForge 补丁处理需要合适的 Java。").pack(anchor="w", pady=(5, 0))
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=10)
        self.install_button = ttk.Button(actions, text="下载并安装所选版本", command=self.install)
        self.install_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="取消", state="disabled", command=self.cancel.set)
        self.cancel_button.pack(side="left", padx=6)
        ttk.Button(actions, text="打开 PCL", command=self.open_pcl).pack(side="right")
        self.status = tk.StringVar(value="刷新版本列表后，选择需要安装的版本。")
        ttk.Label(frame, textvariable=self.status, wraplength=790).pack(anchor="w")
        self.output = tk.Text(frame, height=7, state="disabled", font=("Consolas", 9))
        self.output.pack(fill="x", pady=(8, 0))
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
        def operation():
            engine = Installer(folder, source, lambda msg: self.events.put(("log", msg)), self.cancel)
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
            if kind == "manifest":
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
                messagebox.showinfo("安装完成", f"版本：{name}\n游戏目录：{folder}\n\n点击“打开 PCL”，在版本选择中刷新并选择此版本。\n若目录未显示，请先添加上述游戏目录。\n登录账号并点击启动；Java 由 PCL 管理。")
            else:
                self.status.set(value)
                self.output.configure(state="normal")
                self.output.insert("end", value + "\n")
                self.output.see("end")
                self.output.configure(state="disabled")
                if kind == "error":
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
