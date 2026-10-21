# 验证记录

2026-10-20，Windows x64，Python 3.14.2，Java 25（Microsoft OpenJDK）。

- `python -m unittest -v`：14 项通过。
  覆盖源地址转换、远端路径越界拒绝、Windows 原生库选择、
  损坏文件不替换已有文件、完整安装与缓存复用、加载器版本筛选、
  Fabric 发布原子性，以及 BMCLAPI 的 NeoForge 路径映射与 `.sha1` 回退。
- Mojang 清单读取成功：920 个版本，最新正式版 `26.3`、快照 `26.4-snapshot-5`。
  本轮复测时 BMCLAPI 清单在重定向节点出现 TLS EOF；程序按设计报错，
  没有静默切换到另一个源。
- 在隔离目录执行真实安装：
  `python app.py --install rd-132211 --directory <隔离目录> --source official`。
  478 个文件全部完成，生成客户端、库、资源、旧版虚拟资源和最终版本 JSON。
- 真实读取并验证元数据 SHA-1：
  `1.21.1`（70 个 Windows 库文件）、
  `26.3`（74 个）、`26.4-snapshot-4`（74 个）。
  后两者声明 Java 25，1.21.1 声明 Java 21。
  这三项仅验证元数据和依赖解析，未完整下载这三个版本。
- 四种加载器均在隔离目录完成真实安装（BMCLAPI 源，实际运行上游安装器）：

  | 组件 | 选择 | 生成的版本目录 | 库文件 | 缺失 |
  | --- | --- | --- | --- | --- |
  | Fabric | 0.16.10 / 1.20.1 | `fabric-loader-0.16.10-1.20.1` | 8 | 0 |
  | OptiFine | HD_U_I6 / 1.20.1 | `1.20.1-OptiFine_HD_U_I6` | 2 | 0 |
  | Forge | 47.4.0 / 1.20.1 | `1.20.1-forge-47.4.0` | 29 | 0 |
  | NeoForge | 21.1.215 / 1.21.1 | `neoforge-21.1.215` | 47 | 0 |

  四个版本 JSON 的 `inheritsFrom` 均等于所选原版，主类分别为
  `net.fabricmc.loader.impl.launch.knot.KnotClient`、
  `net.minecraft.launchwrapper.Launch`（OptiFine tweaker）、
  `cpw.mods.bootstraplauncher.BootstrapLauncher`（Forge / NeoForge）；
  逐项检查了库文件是否落在游戏目录中。
- 验证中发现并修复的真实缺陷：BMCLAPI 的 NeoForge 构件位于 `/maven` 下且
  省略 `releases` 段（与 PCL 中 `DlSourceLibraryGet` 的映射一致），
  并且不提供安装器的 `.sha1`。此前的 `/neoforge/releases/...` 映射会 404。
  现在构件仍走镜像，镜像缺少哈希时回退到官方 Maven 的 `.sha1`；
  该行为有对应单元测试。
- OptiFine 官方源的 `adloadx → downloadx` 链接解析实测可用；
  OptiFine 的实际安装使用 BMCLAPI 源。
- PyInstaller 6.20.0 重新构建成功，EXE 约 12.4 MB。
  `MC-Mini.exe --list` 退出码 0；启动 GUI 后窗口标题为
  `MC Mini · Minecraft 与加载器安装`，关闭窗口后进程自行退出。
- 当前目录不是 git 仓库；发布包为 `MC-Mini-source-MIT.zip`，
  只包含 `mc-mini` 下的源码文件。

未验证：账号登录后真正进入游戏（本机无可用账号，且 1.20.1 Forge 启动需要
Java 17/21，本机只安装了 Java 25）；全部 920 个版本逐一启动；
Forge 与 OptiFine 组合安装；官方源下 Forge/NeoForge 的完整安装流程
（仅验证了官方 `.sha1` 与官方安装器地址可达）。
