# 《中国：毛的遗产》简体中文汉化补丁

**[下载 Windows 安装程序（.exe）](https://github.com/lingjieheti/china-maos-legacy-zh-cn/releases/latest/download/china-maos-legacy-zh-cn-Setup.exe)**

退出游戏，双击安装程序。它会自动找到 Steam 游戏目录，点击 **安装汉化** 即可。从 Steam 启动游戏，在主菜单点击 **简体中文**。

首次安装会自动下载社区翻译素材，耗时取决于网络。也可手动选择目录。游戏更新后，可点 **核验汉化** 检查当前安装。需要恢复原版时，点击 **还原原版**。

适配 Steam Windows x64 构建 **21377206**。[v1.2.1 修订说明](games/mao/COMMUNITY-1.2.1.md) · [校对记录](games/mao/AUDIT.md) · [补丁来源与技术说明](games/mao/README.md) · [游戏内截图](docs/mao-economy.webp)

<details>
<summary>从源码构建安装程序</summary>

在 Windows x64 和 Python 3.12 环境中运行：

```powershell
py -3.12 tools/build_setup.py
```

生成的独立 EXE 与 SHA-256 校验文件保存在 `dist` 目录。构建器从 Python.org 获取固定哈希的 Windows 嵌入式运行时。玩家直接使用上方的安装程序。

</details>
