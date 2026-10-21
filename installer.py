"""Shared downloads and vanilla Minecraft installation."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import threading
import urllib.parse
import urllib.error
import urllib.request

from aria2_downloads import fetch

DATA = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
SOURCES = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))


def safe_path(root, name):
    """Remote metadata must never write outside the selected directory."""
    root = Path(root).resolve()
    if "\\" in name or ":" in name:
        raise ValueError(f"非法文件路径：{name}")
    path = (root / name).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f"越界文件路径：{name}")
    return path


def version_name(name):
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", name) or name in (".", ".."):
        raise ValueError("非法版本名称")
    return name


def rewrite(url, source, kind="file"):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"不支持的下载 URL：{url}")
    official = {
        "piston-meta.mojang.com", "piston-data.mojang.com",
        "launchermeta.mojang.com", "launcher.mojang.com",
        "resources.download.minecraft.net", "libraries.minecraft.net",
    }
    if source == "bmclapi" and parsed.hostname in ("maven.minecraftforge.net", "files.minecraftforge.net",
                                                   "maven.fabricmc.net", "maven.neoforged.net", "neoforged.forgecdn.net"):
        path = parsed.path
        if parsed.hostname == "files.minecraftforge.net" and path.startswith("/maven/"):
            path = path[6:]
        if parsed.hostname in ("maven.neoforged.net", "neoforged.forgecdn.net"):
            # The mirror drops the "releases" segment; this matches PCL's own mapping.
            if path.startswith("/releases/"):
                path = path[len("/releases"):]
            return SOURCES["mirror"] + "/maven" + path
        return SOURCES["mirror"] + "/maven" + path
    if source == "bmclapi" and parsed.hostname in official:
        prefix = "/assets" if kind == "asset" else "/maven" if kind == "library" else ""
        return SOURCES["mirror"] + prefix + parsed.path
    return urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))


def request(url):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "MC-Mini/1.0"}),
        timeout=45,
    )


def checked(data, sha1=None, size=None):
    if size is not None and len(data) != size:
        raise ValueError("下载文件长度不匹配")
    if sha1 and hashlib.sha1(data).hexdigest() != sha1:
        raise ValueError("下载文件 SHA-1 不匹配")


def source_urls(url, source, kind="file"):
    alternate = "official" if source == "bmclapi" else "bmclapi"
    return list(dict.fromkeys(rewrite(url, selected, kind) for selected in (source, alternate)))


def get_json(url, source, sha1=None):
    candidates = source_urls(url, source)
    for index, candidate in enumerate(candidates):
        try:
            with request(candidate) as response:
                data = response.read()
        except urllib.error.URLError as error:
            if isinstance(error, urllib.error.HTTPError):
                error.close()
                if error.code < 500 and error.code not in (408, 429):
                    raise
            if index == len(candidates) - 1:
                raise
            continue
        checked(data, sha1)
        return json.loads(data), data


def manifest(source):
    return get_json(SOURCES["manifest"], source)[0]


def allowed(rules):
    result = not rules
    for rule in rules:
        os_rule = rule.get("os", {})
        matches = os_rule.get("name", "windows") == "windows"
        if "arch" in os_rule:
            matches &= bool(re.fullmatch(os_rule["arch"], "x86_64"))
        if "version" in os_rule:
            matches &= bool(re.search(os_rule["version"], platform.version()))
        matches &= not any(rule.get("features", {}).values())
        if matches:
            result = rule["action"] == "allow"
    return result


def maven_path(coordinate):
    name, _, extension = coordinate.partition("@")
    pieces = name.split(":")
    if len(pieces) not in (3, 4):
        raise ValueError(f"非法 Maven 坐标：{coordinate}")
    group, artifact, version = pieces[:3]
    suffix = "-" + pieces[3] if len(pieces) == 4 else ""
    return f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}{suffix}.{extension or 'jar'}"


def library_files(library):
    if not allowed(library.get("rules", [])):
        return []
    downloads = library.get("downloads")
    if downloads is None:
        path = maven_path(library["name"])
        return [{"path": path, "url": library.get("url", SOURCES["libraries"] + "/").rstrip("/") + "/" + path,
                 "sha1": library.get("sha1"), "size": library.get("size")}]
    result = []
    if "artifact" in downloads:
        result.append(downloads["artifact"])
    native = library.get("natives", {}).get("windows")
    if native:
        result.append(downloads["classifiers"][native.replace("${arch}", "64")])
    return result


class Installer:
    def __init__(self, root, source="bmclapi", log=print, cancel=None, progress=None):
        self.root = Path(root).resolve()
        self.source = source
        self.log = log
        self.progress = progress
        self.cancel = cancel or threading.Event()

    def stop_check(self):
        if self.cancel.is_set():
            raise InterruptedError("安装已取消；已校验文件可在下次安装时复用")

    def download(self, item):
        self.download_many([item])

    def download_many(self, items):
        rewritten = [(source_urls(url, self.source, kind), path, sha1, size, kind)
                     for url, path, sha1, size, kind in items]
        fetch(rewritten, self.cancel, self.log, self.root / '.mcmini/logs', progress=self.progress)

    def install(self, entry):
        name = version_name(entry["id"])
        self.log(f"读取 {name} 元数据…")
        meta, raw = get_json(entry["url"], self.source, entry.get("sha1"))
        if meta["id"] != name or "inheritsFrom" in meta:
            raise ValueError("元数据不是所选独立原版")
        target = safe_path(self.root, f"versions/{name}/{name}.json")
        if target.exists() and json.loads(target.read_bytes()) != meta:
            raise FileExistsError("已有同名但内容不同的版本；请改用另一个游戏目录")
        jobs = {}

        def add(info, rel, kind="file"):
            path = safe_path(self.root, rel)
            job = (info["url"], path, info.get("sha1"), info.get("size"), kind)
            if path in jobs and jobs[path] != job:
                raise ValueError(f"元数据包含冲突文件：{rel}")
            jobs[path] = job

        add(meta["downloads"]["client"], f"versions/{name}/{name}.jar")
        for library in meta["libraries"]:
            for info in library_files(library):
                add(info, "libraries/" + info["path"], "library")
        asset_info = meta["assetIndex"]
        index_path = safe_path(self.root, f"assets/indexes/{version_name(asset_info['id'])}.json")
        self.download((asset_info["url"], index_path, asset_info["sha1"], asset_info["size"], "file"))
        index = json.loads(index_path.read_bytes())
        for obj in index["objects"].values():
            sha = obj["hash"]
            if not re.fullmatch("[0-9a-f]{40}", sha):
                raise ValueError("非法资源哈希")
            rel = f"{sha[:2]}/{sha}"
            add({"url": SOURCES["assets"] + "/" + rel, "sha1": sha, "size": obj["size"]},
                "assets/objects/" + rel, "asset")
        logging = meta.get("logging", {}).get("client", {}).get("file")
        if logging:
            add(logging, "assets/log_configs/" + logging["id"])
        self.log(f"校验并下载 {len(jobs)} 个文件（8 路并发）…")
        self.download_many(list(jobs.values()))
        # Older versions require named copies in addition to content-addressed assets.
        for key in ("virtual", "map_to_resources"):
            if index.get(key):
                base = self.root / ("assets/virtual/" + asset_info["id"] if key == "virtual" else "resources")
                for asset_name, obj in index["objects"].items():
                    self.stop_check()
                    dest = safe_path(base, asset_name)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    sha = obj["hash"]
                    shutil.copyfile(self.root / f"assets/objects/{sha[:2]}/{sha}", dest)
        self.stop_check()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".json.mcmini-part")
        temp.write_bytes(raw)
        os.replace(temp, target)
        self.log(f"安装完成：{target.parent}")
        return target.parent
