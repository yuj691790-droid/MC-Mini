# MC Mini

独立、轻量的 Minecraft Java 下载与安装工具。Windows x64，Python 标准库 + Tk。
支持原版、Fabric、Forge、NeoForge、OptiFine；可选 Mojang/加载器官方源或 BMCLAPI。

## 使用

1. 双击 `MC-Mini.exe`（构建后位于 `dist`）；无需安装 Python。
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
- 8 路下载；有 SHA-1 的文件进行完整性验证，已有正确文件直接复用。
- 临时文件下载完成后替换；全流程成功后才发布版本 JSON。
- TLS/超时/连接中断及服务器 5xx 错误最多重试一次；其他错误直接显示，
  可选择另一个源并重新安装；不自动切源。哈希错误不重试。
- 取消会等待当前网络读取返回（超时 45 秒）；已完成文件保留供下次复用。
- 同名版本 JSON 不同则拒绝覆盖，以免破坏用户已有整合包。
- 目前针对 Windows x64；游戏版本及第三方镜像自身的可用性由上游决定。

`sources.json` 内保存下载入口和从本地 PCL 提取的扩展组件源。
原版安装器采用 v2 清单以获取版本 JSON 哈希；该地址是本工具选用，
不是声称从样本中提取。提取依据见 [EXTRACTION.md](EXTRACTION.md)。

## 从源码运行

Python 3.11+，含 Tk；运行时无 pip 依赖。

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

- `installer.py`：下载、哈希校验、Maven 路径与原版安装。
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
