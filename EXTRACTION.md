# 本地样本与下载源提取

检查日期：2026-10-20。

- 样本：`Plain Craft Launcher 2.exe`
- 文件长度：5,750,272 bytes
- SHA-256：`30EB93C62FC51EDE0898648E67455478A3D5A4F279938AE65AEC77B84CB9703F`
- 程序内版本常量：`2.13.1.1`，版本代码 `408`，Official Release。
- 文件夹名 `PCL 正式版 2.10.6` 不代表内部版本。
- 方法：ILSpy CLI 9.1.0.7988 静态反编译，检查 `PCL.ModDownload`、
  `PCL.ModDownloadLib`、`PCL.ModMain` 及启动参数分发；未修改样本。
- 原始分析文件曾放在上级 `.analysis`，不属于本 MIT 项目；2026-10-20 已删除。

> 2026-10-20 22:34 补注：本记录完成后，该 exe 在文件夹内被替换为
> `2.99.0.0`（413），长度 5,980,160 bytes，
> SHA-256 `6B6E1260CB5A1D6A303855F1C60CAB3D0BC1AEBBA7E40A964180188B271E7386`。
> 以上提取内容对应替换前的 `2.13.1.1` 样本，未对 `2.99.0.0` 重新提取。

## 原版接口

| 用途 | 官方地址 | BMCLAPI 地址 |
| --- | --- | --- |
| 版本列表 | `https://launchermeta.mojang.com/mc/game/version_manifest.json` | `https://bmclapi2.bangbang93.com/mc/game/version_manifest.json` |
| 资源对象 | `https://resources.download.minecraft.net/<前两位>/<SHA1>` | `https://bmclapi2.bangbang93.com/assets/<前两位>/<SHA1>` |
| Maven 依赖 | `https://libraries.minecraft.net/<path>` | `https://bmclapi2.bangbang93.com/maven/<path>` |
| 客户端与元数据 | 版本清单/JSON 指定的 Mojang URL | 替换 Mojang 主机名为 `bmclapi2.bangbang93.com`，保留路径 |

`ModDownload` 中资源源转换方法将资源主机映射到 `/assets`；
依赖库转换提供 `/maven`、`/libraries` 两种地址；
普通文件转换将 `piston-data`、`piston-meta`、`launcher`、
`launchermeta.mojang.com` 替换为 BMCLAPI 主机。
本工具采用 `/maven` 依赖路径，不实施多候选自动回退。

具体版本的 JAR 与资源索引 URL 由远端 JSON 提供，不是固定在程序里的版本列表。
本工具选用 `https://piston-meta.mojang.com/mc/game/version_manifest_v2.json`
作为附带哈希的清单入口，已对官方和镜像执行实际读取验证。

## 其他组件

从 `ModDownload` 提取到 Fabric、Forge、NeoForge、OptiFine、LiteLoader
的官方/镜像列表接口；详见 `sources.json` 的 `extracted`。
这些是提取结果，不代表已实现对应组件安装，也不代表每个历史服务仍在线。

NeoForge 的镜像地址另有一条规则：`DlSourceLibraryGet` 与它的安装代码把
`maven.neoforged.net/releases` 换成 `bmclapi2.bangbang93.com/maven`，
即去掉 `releases` 段；`/neoforge` 前缀只用于它的 Maven API 元数据。
实测该构件路径经 302 指向镜像节点，且镜像不提供对应 `.sha1`。
本工具按此映射下载，哈希缺失时从官方 Maven 读取。

## PCL 启动衔接

样本启动参数分发能看到 `--update`、`--gpu`、`--memory`、`--wait`，
未找到可供本工具使用的“指定版本启动”参数。
因此工具只打开用户选择的 PCL EXE，通过标准 `.minecraft/versions/<id>/<id>.json`
和同名 JAR 被 PCL 识别；用户在 PCL 中选择版本并启动。

本次提取不对下载功能变更的原因作判断。
