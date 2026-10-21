"""Live loader catalogs and isolated upstream installer integration."""
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from installer import DATA, SOURCES, Installer, get_json, library_files, maven_path, request, rewrite, safe_path, version_name

KINDS = ("原版", "Fabric", "Forge", "NeoForge", "OptiFine")


def sort_key(value):
    return tuple((1, int(p)) if p.isdigit() else (0, p.lower())
                 for p in re.split(r"(\d+)", value))


def catalog(kind, minecraft, source):
    """Return installable entries, never automatically choose one."""
    version_name(minecraft)
    if kind == "Fabric":
        base = SOURCES["mirror"] + "/fabric-meta" if source == "bmclapi" else "https://meta.fabricmc.net"
        rows, _ = get_json(f"{base}/v2/versions/loader/{minecraft}", source)
        return [{"version": row["loader"]["version"],
                 "label": row["loader"]["version"] + (" · 稳定" if row["loader"]["stable"] else " · 预览"),
                 "base": base} for row in rows]
    if kind == "Forge":
        if source == "bmclapi":
            rows, _ = get_json(SOURCES["mirror"] + "/forge/minecraft/" + minecraft, source)
            result = []
            for row in rows:
                for file in row["files"]:
                    if file["category"] == "installer" and file["format"] == "jar":
                        coordinate = f"{minecraft}-{row['version']}" + ("-" + row["branch"] if row.get("branch") else "")
                        result.append({"version": row["version"], "label": row["version"],
                                       "coordinate": coordinate, "sha1": file["hash"]})
            return sorted(result, key=lambda x: sort_key(x["version"]), reverse=True)
        with request("https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml") as response:
            tree = ET.fromstring(response.read())
        prefix = minecraft + "-"
        return [{"version": v[len(prefix):], "label": v[len(prefix):], "coordinate": v}
                for v in sorted((e.text for e in tree.findall("./versioning/versions/version")
                                 if e.text.startswith(prefix)), key=sort_key, reverse=True)]
    if kind == "NeoForge":
        artifact = "forge" if minecraft == "1.20.1" else "neoforge"
        base = SOURCES["mirror"] + "/neoforge" if source == "bmclapi" else "https://maven.neoforged.net"
        endpoint = "/meta/api/maven/details/releases/net/neoforged/" if source == "bmclapi" else "/api/maven/versions/releases/net/neoforged/"
        data, _ = get_json(base + endpoint + artifact, source)
        versions = ([item["name"] for item in data["files"] if item["type"] == "DIRECTORY"]
                    if source == "bmclapi" else data["versions"])
        result = []
        for v in versions:
            if neoforge_minecraft(v, artifact) == minecraft:
                result.append({"version": v, "label": v, "artifact": artifact})
        return sorted(result, key=lambda x: sort_key(x["version"]), reverse=True)
    if kind == "OptiFine":
        # OptiFine has no public JSON catalog; BMCLAPI provides structured metadata.
        rows, _ = get_json(SOURCES["mirror"] + "/optifine/versionList", "bmclapi")
        return sorted([{"version": f"{r['type']}_{r['patch']}",
                        "label": f"{r['type']}_{r['patch']} · {r.get('forge', '独立安装')}",
                        "type": r["type"], "patch": r["patch"], "filename": r["filename"]}
                       for r in rows if r["mcversion"] == minecraft],
                      key=lambda x: ("pre" not in x["patch"], sort_key(x["version"])), reverse=True)
    if kind == "原版":
        return []
    raise ValueError("未知加载器")


def neoforge_minecraft(version, artifact="neoforge"):
    if artifact == "forge":
        return version.split("-")[0]
    parts = version.split("-")[0].split(".")
    if len(parts) >= 3 and parts[0] == "0":
        return parts[1]
    if len(parts) >= 4 and parts[0].isdigit() and int(parts[0]) >= 26:
        # New year-based MC versions: 26.3 -> NeoForge 26.3.0.x.
        return ".".join(parts[:2] if parts[2] == "0" else parts[:3])
    if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
        return f"1.{parts[0]}" + (f".{parts[1]}" if parts[1] != "0" else "")
    return None


def find_java():
    command = shutil.which("java")
    if command:
        return command
    roots = [Path(os.environ.get("LOCALAPPDATA", "")) / "Packages/Microsoft.4297127D64EC6_8wekyb3d8bbwe/LocalCache/Local/runtime",
             Path(os.environ.get("APPDATA", "")) / ".minecraft/runtime",
             Path(os.environ.get("PROGRAMFILES", "")) / "Java",
             Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft"]
    if os.environ.get("JAVA_HOME"):
        roots.insert(0, Path(os.environ["JAVA_HOME"]))
    for root in roots:
        if root.is_dir():
            matches = sorted(root.glob("**/bin/java.exe"))
            if matches:
                return str(matches[0])
    return ""


def download_libraries(installer, libraries, embedded=None, cache=None):
    for count, library in enumerate(libraries, 1):
        installer.stop_check()
        if count == 1 or count % 10 == 0:
            installer.log(f"加载器依赖 {count}/{len(libraries)}：{library['name']}")
        if library.get("clientreq") is False:
            continue
        for item in library_files(library):
            path = safe_path(installer.root, "libraries/" + item["path"])
            member = "maven/" + item["path"]
            if embedded is not None and member in embedded.namelist():
                data = embedded.read(member)
                if item.get("sha1") and hashlib.sha1(data).hexdigest() != item["sha1"]:
                    raise ValueError("内嵌库哈希错误：" + item["path"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            elif item["url"]:  # Empty URLs denote libraries produced by patch processors.
                download_path = safe_path(cache.root, "libraries/" + item["path"]) if cache else path
                (cache or installer).download((item["url"], download_path, item.get("sha1"), item.get("size"), "library"))
                if cache:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(download_path, path)


def publish_profile(root, profile):
    name = version_name(profile["id"])
    target = safe_path(root, f"versions/{name}/{name}.json")
    if target.exists():
        # Fabric's API timestamps vary between requests.
        existing = json.loads(target.read_bytes())
        strip = lambda x: {k: v for k, v in x.items() if k not in ("time", "releaseTime")}
        if strip(existing) != strip(profile):
            raise FileExistsError("已有同名但不同的加载器版本：" + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".json.mcmini-part")
    temp.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, target)
    return target.parent


def run_java(java, args, cwd, installer):
    logdir = installer.root / ".mcmini/logs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / "loader-install.log"
    installer.log("运行上游安装器；详细输出：" + str(log))
    with log.open("wb") as output:
        process = subprocess.Popen([java, "-Djava.awt.headless=true", *args], cwd=cwd,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        while process.poll() is None:
            if installer.cancel.wait(0.25):
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                process.wait()
                installer.stop_check()
    if process.returncode:
        tail = log.read_text(encoding="utf-8", errors="replace")[-1800:]
        raise RuntimeError(f"安装器退出码 {process.returncode}\n{tail}\n日志：{log}")


def installer_digest(url, source):
    """Read the published .sha1; BMCLAPI omits some, so fall back to the official file."""
    addresses = [rewrite(url + ".sha1", source)]
    if source == "bmclapi":
        addresses.append(url + ".sha1")
    text = ""
    for index, address in enumerate(addresses):
        try:
            with request(address) as response:
                text = response.read().decode("ascii", "replace")
            break
        except urllib.error.HTTPError as error:
            error.close()
            if error.code != 404 or index == len(addresses) - 1:
                raise
    digest = text.strip().split()[0].lower() if text.strip() else ""
    if not re.fullmatch("[0-9a-f]{40}", digest):
        raise ValueError("安装器 SHA-1 格式错误")
    return digest


def installer_url(kind, minecraft, choice, source):
    if kind == "Forge":
        coord = version_name(choice["coordinate"])
        return f"https://maven.minecraftforge.net/net/minecraftforge/forge/{coord}/forge-{coord}-installer.jar"
    if kind == "NeoForge":
        v = version_name(choice["version"])
        a = choice["artifact"]
        return f"https://maven.neoforged.net/releases/net/neoforged/{a}/{v}/{a}-{v}-installer.jar"
    if source == "bmclapi":
        return SOURCES["mirror"] + f"/optifine/{minecraft}/{choice['type']}/{choice['patch']}"
    filename = urllib.parse.quote(choice["filename"])
    with request("https://optifine.net/adloadx?f=" + filename) as response:
        page = response.read().decode("utf-8")
    match = re.search(r"""href=['"](downloadx\?[^'"]+)['"]""", page)
    if not match:
        raise ValueError("OptiFine 官方下载页未提供下载链接")
    return "https://optifine.net/" + html.unescape(match.group(1))


def install_loader(installer, entry, kind, choice, java=""):
    if kind == "原版":
        return installer.install(entry)
    if kind not in KINDS or not choice:
        raise ValueError("请先选择加载器版本")
    if kind != "Fabric" and not Path(java).is_file():
        raise ValueError("Forge / NeoForge / OptiFine 安装需要 Java，请选择 java.exe")
    vanilla = installer.install(entry)
    return install_component(installer, entry["id"], kind, choice, java, vanilla)


def install_component(installer, minecraft, kind, choice, java="", vanilla=None):
    """Install a component after the verified base game has been installed."""
    version_name(minecraft)
    version_name(choice["version"])
    vanilla = vanilla or installer.root / "versions" / minecraft
    installer.stop_check()
    installer.log(f"安装 {kind} {choice['version']}…")
    if kind == "Fabric":
        base = SOURCES["mirror"] + "/fabric-meta" if installer.source == "bmclapi" else "https://meta.fabricmc.net"
        profile, _ = get_json(f"{base}/v2/versions/loader/{minecraft}/{choice['version']}/profile/json", installer.source)
        if profile["inheritsFrom"] != minecraft:
            raise ValueError("Fabric 返回的基础版本不匹配")
        download_libraries(installer, profile["libraries"])
        installer.stop_check()
        return publish_profile(installer.root, profile)

    work = installer.root / ".mcmini"
    work.mkdir(parents=True, exist_ok=True)
    url = installer_url(kind, minecraft, choice, installer.source)
    jar = safe_path(work, f"installers/{kind}-{minecraft}-{choice['version']}.jar")
    digest = choice.get("sha1")
    if not digest and kind in ("Forge", "NeoForge"):
        digest = installer_digest(url, installer.source)
    installer.download((url, jar, digest, None, "file"))
    with tempfile.TemporaryDirectory(prefix="install-", dir=work) as folder:
        stage = Path(folder)
        base_dir = stage / "versions" / minecraft
        base_dir.mkdir(parents=True)
        for extension in ("json", "jar"):
            shutil.copyfile(vanilla / f"{minecraft}.{extension}", base_dir / f"{minecraft}.{extension}")
        # Upstream installers expect the official launcher's profile file.
        (stage / "launcher_profiles.json").write_text('{"profiles":{}}', encoding="utf-8")
        stage_installer = Installer(stage, installer.source, installer.log, installer.cancel, installer.progress)
        cache = Installer(work / "cache", installer.source, installer.log, installer.cancel, installer.progress)
        if kind == "OptiFine":
            bridge = DATA / "java"
            run_java(java, ["-cp", str(bridge) + os.pathsep + str(jar),
                            "OptiFineBridge", str(stage)], stage, installer)
        else:
            with zipfile.ZipFile(jar) as archive:
                config = json.loads(archive.read("install_profile.json"))
                if "versionInfo" in config:  # Legacy Forge packages.
                    profile = config["versionInfo"]
                    coordinate = config["install"]["path"]
                    dest = safe_path(stage, "libraries/" + maven_path(coordinate))
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(archive.read(config["install"]["filePath"]))
                    download_libraries(stage_installer, [lib for lib in profile["libraries"]
                                                        if lib["name"] != coordinate], archive, cache)
                    publish_profile(stage, profile)
                else:
                    if config["minecraft"] != minecraft:
                        raise ValueError("安装器与所选 Minecraft 版本不匹配")
                    profile = json.loads(archive.read(config["json"].lstrip("/")))
                    download_libraries(stage_installer, config["libraries"], archive, cache)
                    download_libraries(stage_installer, profile["libraries"], archive, cache)
                    # Upstream installers own patch execution and validate its outputs.
                    run_java(java, ["-jar", str(jar), "--installClient", str(stage)], stage, installer)
        candidates = [p for p in (stage / "versions").glob("*/*.json") if p.parent.name != minecraft]
        if len(candidates) != 1:
            raise RuntimeError("安装器未生成唯一的加载器版本；请查看 .mcmini/logs/loader-install.log")
        result = json.loads(candidates[0].read_bytes())
        if result.get("inheritsFrom", minecraft) != minecraft:
            raise ValueError("安装结果的基础版本不匹配")
        # Download e.g. launchwrapper referenced by OptiFine-generated metadata.
        download_libraries(stage_installer, [lib for lib in result.get("libraries", [])
                                            if not safe_path(stage, "libraries/" + maven_path(lib["name"])).exists()])
        installer.stop_check()
        name = version_name(result["id"])
        destination = safe_path(installer.root, "versions/" + name)
        if destination.exists():
            raise FileExistsError("目标加载器版本已存在，请在 PCL 使用它或选择其他版本：" + name)
        for path in (stage / "libraries").rglob("*"):
            if path.is_file():
                installer.stop_check()
                rel = path.relative_to(stage).as_posix()
                target = safe_path(installer.root, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name(target.name + ".mcmini-part")
                shutil.copyfile(path, temp)
                os.replace(temp, target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(candidates[0].parent, destination)
        installer.log("加载器安装完成：" + name)
        return destination
