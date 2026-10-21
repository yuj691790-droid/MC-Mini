# MC-Mini：轻量化MC下载器

独立、轻量的 Minecraft Java 下载与安装工具。Windows x64，Python 标准库 + Tk。
支持原版、Fabric、Forge、NeoForge、OptiFine；可选 Mojang/加载器官方源或 BMCLAPI。

## 使用

1. 运行构建出的 `MC-Mini.exe`；已内置 aria2、许可证和对应源码，无需安装 Python，单个 EXE 即可运行。
   兼容旧便携布局：没有内置 aria2 时，仍可使用同级 `aria2/aria2c.exe`。
2. 选择游戏目录。程序放在 PCL 文件夹内或其直接子目录时，会读取
   `PCL/Setup.ini` 的 `LaunchFolderSelect`，优先使用 PCL 已选择的目录。
3. 选择 MC 版本，再选择“原版”或一种加载器。加载器版本会实时联网获取；
   手动选择需要的版本后，点击“下载并安装所选版本”。
4. 完成后点击“打开 PCL”。在 PCL 的版本选择页刷新列表，
   选择相同游戏目录与新版本，然后登录并启动。如果目录不在 PCL 列表中，手动添加。

本工具不修改 PCL 或 PCL 配置、不读取账号凭据。PCL 若已运行，使用现有窗口即可。
它安装游戏文件，但不代替 PCL 的登录、游戏用 Java 安装/选择、原生库解压和启动参数生成。
不同游戏版本需要相应 Java；由 PCL 启动前检查。
不安装模组包、Fabric API、Bedrock 或服务端。

## 界面与下载进度

深色界面，底部进度条显示当前下载批次的真实字节百分比和实时总速度（MB/s，1 MB = 1,000,000 字节）。
进度包含已校验缓存；切换到下一个下载批次时重新计算。未知总大小时显示“计算大小中”。
下载结束、取消或报错后速度归零；原白色日志框已移除，诊断日志仍保存在游戏目录。
实时数据通过带随机密钥、仅监听本机的 aria2 RPC 获取，不需要手工配置。

## 实时更新

- 启动时读取远端 Minecraft 版本清单，不把版本名单写死在程序中。
- 窗口开启期间每 10 分钟刷新一次；正在下载/安装时跳过本轮。
- “刷新版本”立即检查新版本，显示更新时间、新增数量和最新正式版/快照。
- 选中 MC、切换加载器或更换源时，重新获取兼容加载器列表。
- “刷新加载器”可立即检查新发布的组件；MC 定时刷新后也更新当前加载器列表。
- 刷新保留当前 MC 选择，但组件版本需重新确认，避免静默升级。
- 仅在本程序运行期间检查，不创建系统定时任务，不自动安装更新。
- 镜像可能比官方晚同步；选“快照”或“全部”才能在主列表看到快照。

## 加载器安装

| 组件 | 列表与安装方式 |
| --- | --- |
| Fabric | Fabric Meta 按 MC 查询版本；获取启动配置，下载依赖并生成独立版本 |
| Forge | 官方 Maven 元数据或 BMCLAPI 版本接口；运行官方安装器执行客户端补丁 |
| NeoForge | NeoForged Maven API 或 BMCLAPI 元数据；按 MC 版本筛选后运行官方安装器 |
| OptiFine | BMCLAPI 提供结构化版本清单；从所选源下载，通过其安装器生成独立版本 |

Forge / NeoForge / OptiFine 需要在界面选择 `java.exe`。
程序会从 PATH、JAVA_HOME 及常见 Minecraft Java 目录查找初始值；
这只是路径发现，不代表它与所有 MC 版本都兼容。请使用与目标 MC 匹配的 Java。
原版和 Fabric 安装本身不需要 Java。

首先安装原版，再安装选定组件。Forge / NeoForge / OptiFine 在
`.mcmini/install-*` 临时目录中运行上游安装器，使用独立的空 launcher_profiles，
成功后才发布生成的版本；不会把临时 profiles 写回用户配置。
下载缓存位于 `.mcmini/cache`，安装日志位于 `.mcmini/logs/loader-install.log`。
可取消运行中的安装器及其子进程。

一次选择一种组件。OptiFine 独立安装；列表中的 Forge 信息是上游兼容提示，
不代表本工具会把两者组合安装。Fabric、Forge、NeoForge 也不混装。
已有同名 Forge/NeoForge/OptiFine 版本会被保留并提示，不覆盖用户定制版本。

选 BMCLAPI 时，本工具的依赖预下载经过镜像；
Forge/NeoForge 上游安装器内部仍可能访问官方服务或自行下载处理器所需内容，
不能保证整个安装过程只连接镜像。BMCLAPI 的 NeoForge 构件位于 `/maven` 且省略
`releases` 段（与 PCL 的映射相同）；镜像不提供个别 `.sha1` 时，本工具从官方
Maven 读取该哈希，安装器本体仍走镜像。网络失败会显示错误与日志位置。
旧安装器或未来接口格式若不兼容，会报错；实时列表不意味着无需维护即可支持所有未来格式。

## 下载行为

- 版本 JSON、客户端 JAR、Windows 依赖库与原生库 JAR、资源索引、资源对象、日志配置。
- 旧版本的 virtual 和 map_to_resources 资源布局。
- 单个 aria2 进程管理队列，最多同时下载 8 个文件；小文件 1 连接，1 MB 起 2 连接，8 MB 起最多 4 连接；有 SHA-1 的文件进行完整性验证，已有正确文件直接复用。
- 临时文件下载完成并校验后替换；全流程成功后才发布版本 JSON。
- 文件下载使用 aria2，最多尝试 5 次，重试间隔 2 秒；保持 TLS 证书验证。
  失败或取消后保留 `.mcmini-part` / `.aria2` 断点，下次安装继续。对可映射地址同时提供所选源和备用源；所选源排在前面，分段下载时可同时使用多个地址。
  最终文件仍经本程序校验后发布，原文件不会被未校验的下载覆盖。
- 取消会结束 aria2 进程并保留断点。版本目录等元数据请求仍由 Python 读取，超时 45 秒；所选源网络失败时尝试可映射的备用地址一次，哈希或 JSON 错误直接报错。
- 下载诊断日志：游戏目录下 `.mcmini/logs/aria2-download.log`。
- 同名版本 JSON 不同则拒绝覆盖，以免破坏用户已有整合包。
- 目前针对 Windows x64；游戏版本及第三方镜像自身的可用性由上游决定。

`sources.json` 内保存下载入口和从本地 PCL 提取的扩展组件源。
原版安装器采用 v2 清单以获取版本 JSON 哈希；该地址是本工具选用，
不是声称从样本中提取。提取依据见 [EXTRACTION.md](EXTRACTION.md)。

## 从源码运行

Python 3.11+，含 Tk；运行时无 pip 依赖。先执行 `python fetch_aria2.py` 准备独立下载器。

```powershell
python app.py
python app.py --list --source official
python app.py --list-loaders 1.20.1 --loader Fabric
python app.py --install 1.20.1 --loader Fabric --loader-version 0.16.10 --directory 'D:\Games\.minecraft'
python app.py --install 1.20.1 --loader Forge --loader-version 47.4.0 --java 'C:\Java\bin\java.exe' --directory 'D:\Games\.minecraft'
python -m unittest -v
```

构建独立 EXE（需要联网获取 PyInstaller；编译 OptiFine 桥接器需要 JDK 9+ 的
`javac`，没有时复用已编译的 `java/OptiFineBridge.class`）：

```powershell
.\build.ps1
```

构建工具仅装入本项目 `.venv`。`--windowed` EXE 用于图形界面；
命令行模式请使用 `python app.py`，以便在终端看到日志。
OptiFine 的微型 Java 桥接器由 `OptiFineBridge.java` 编译；
源码运行时也需要 `java/OptiFineBridge.class`，可执行
`javac --release 8 -d java OptiFineBridge.java` 生成。EXE 已内置桥接器。
找不到 `javac` 时，构建脚本会复用已有的 `java/OptiFineBridge.class`，
仅在它缺失或比源码旧时报错。

## 代码结构

- `installer.py`：下载源映射、Maven 路径与原版安装。
- `aria2_downloads.py`：aria2 队列、断点续传、进程取消与校验发布。
- `fetch_aria2.py`：按固定 SHA-256 获取 aria2 及许可证/对应源码。
- `loaders.py`：四种组件的动态目录、安装与隔离发布。
- `app.py`：界面、刷新周期、用户选择与命令行。
- `OptiFineBridge.java`：调用 OptiFine 公开安装入口，不包含其实现。

## 许可证与授权范围

本项目当前采用 **CC BY-NC-SA 4.0 + 署名豁免**：**非商业、相同方式共享，无需署名**。
完整说明见 [LICENSE](LICENSE) 与 [CC 协议全文](LICENSE-CC-BY-NC-SA-4.0.txt)。
无需标注本项目作者，但仍需保留许可协议通知/链接、免责声明、原作品链接及修改标记。
非商业限制意味着当前版本属于源码可见项目，不属于通常允许商业使用的开源许可。

已按 MIT 发布的 `v1.0.0` 和对应历史代码仍保留原 MIT 授权；本次变更不追溯撤销这些权利。
不包含 PCL 可执行文件、反编译源码、Minecraft 文件、账户信息或游戏目录。
上述授权仅适用于本项目许可人有权授权的内容；PCL、Minecraft、加载器等第三方内容仍遵循各自许可证。
发布 GitHub 时只提交本文件夹源码，不要提交上级 PCL 文件夹。

接口参考：[BMCLAPI 文档](https://bmclapidoc.bangbang93.com/)、
[Fabric Meta](https://github.com/FabricMC/fabric-meta/blob/master/README.md)、
[Forge Installer](https://github.com/MinecraftForge/Installer)、
[NeoForge 客户端安装](https://docs.neoforged.net/user/docs/client/)。

## aria2 第三方组件

aria2 1.37.0 作为独立命令行程序内置于 EXE，运行时解包后作为独立进程执行，采用 GPL-2.0-or-later，
不适用 MC Mini 的非商业限制。`aria2/` 包含原始 COPYING、附加声明、
Windows 构建说明和同版本源码归档；本项目没有修改 aria2。
可执行 `MC-Mini.exe --export-aria2 <目标目录>` 导出这些第三方文件；本项目的非商业限制不适用于它们。
下载器使用说明见 [aria2 官方文档](https://aria2.github.io/manual/en/html/aria2c.html)。

NeoForge 当前 Maven 地址由 `sources.json` 的 `neoforge_maven` 控制；`extracted` 保留最初的提取记录。
