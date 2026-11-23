# 《中国：毛的遗产》简体中文补丁

适配 **Steam Windows 版 1.8.5，Build 21377206**。中文使用游戏的英语语言槽。补丁由玩家电脑上的 Steam 原件构建，沿用原游戏的场景跳转、计分、存档和成就逻辑。

## 安装与还原

先安装 Steam 游戏和 Windows 版 Python 3.11 或更高版本，退出游戏。在完整发行包的根目录执行下列命令。

```powershell
py -3 games/mao/patch.py install
py -3 games/mao/patch.py verify
py -3 games/mao/patch.py restore
```

第一条安装中文，第二条核验当前补丁，第三条恢复安装前的文件。工具会在 Steam 库中查找游戏。自定义目录可在命令末尾加 `--game-data "D:\Games\Mao's Legacy\China_Data"`。如果系统使用 `python` 启动 Python，可将命令中的 `py -3` 替换为 `python`。

首次安装需要联网。程序在独立缓存中准备 UnityPy 1.25.4，对照固定提交下载社区翻译素材，并校验 Mono.Cecil 0.11.6 工具包，再用 Windows 自带的 .NET Framework C# 编译器生成补丁。整个过程不需要翻译服务或 API 密钥。原件保存在游戏安装目录的 `.nostalgames-zh-cn/backup/original`。缓存默认位于 `%LOCALAPPDATA%\Nostalgames-ZhCN\Mao`，可用 `--cache` 改变位置。

启动后先进入中文图形设置，再进入游戏。有旧俄语偏好时，可在游戏语言选择页点击英国旗帜进入简体中文。Steam 更新或完整性验证可能恢复游戏文件。如果版本仍匹配，重新运行安装命令即可。

## 文本与界面

- 翻译开场图形设置、画质和帧率选项，缩短警告文案。主菜单、教程、外交、政党、储备和科研界面使用中文显示，内部场景标识保留原值。
- 回译和校对国家、政治人物、派系、政策纲领和修正说明。例子包括“汪东兴”“叶剑英”“陈锡联”“中国国民党革命委员会”。补回寡头效果说明遗漏的生活水平和情报网两项数值。
- 为法国剧本补充原英文资源中缺失的政党表和资源索引。按同版本俄语底表校正法国姓名与 25 项人物特质，保留法语人名的通行译名。
- 将中文黑体写入九个原有字体资源，对启动设置的常规文字与按钮分别使用常规和半粗字重。在五个长文本排版入口按中西文字宽、标点与富文本标记预排换行。经济页统一预算卡片字号，给腐败和储备说明增加行距。储备数字按显示精度取整，实际游戏计算保留原值。

本轮复核另外纠正了新疆结局错列、外交路线条件、朝鲜战后国名及脚本查询键。逐类结果、复核命令和人工审读范围见[文本复核记录](AUDIT.md)。

## 已做的检查

构建程序校验原始文件和下载内容的 SHA-256，重新读取每个生成的 Unity 资源并逐对象比对。程序集检查覆盖 3,511 个原方法和 478,612 条原始 IL 指令，核对翻译引用、五个排版入口及两处储备数值显示。重复安装、校验、还原与再次安装已在独立目录演练。

首次发行版的实机抽查覆盖启动图形设置、新游戏、地图、悬停生活水平变化和经济页。各 DLC 分支、全部结局、所有显示分辨率及用户已有存档仍缺少逐项实测。部分历史图片、旗帜及教程内嵌原版截图仍沿用原图。该补丁只支持列明的 Steam 文件指纹。

## 来源

- 社区汉化文字、场景参考和 TMP 字体配置来自 LeXwDeX，固定至下列提交。安装时从上游读取所需数据，发布材料仅含本项目的改动和构建逻辑。[Mao’s Legacy Chinese Tools](https://github.com/LeXwDeX/Mao-s-Legacy-Chinese-Tools/tree/ae0e8ee740bdc0d44a8c172222130aee40164ded)
- 原游戏由 Nostalgames 开发。[Steam 商店](https://store.steampowered.com/app/950740/China_Maos_legacy/)
- 游戏和启动器使用同一份 Nostal UI SC 字体。字体许可及上游归属附在发行包的 `fonts` 目录。Mono.Cecil 的许可证随 NuGet 构建依赖提供。[Mono.Cecil](https://github.com/jbevain/cecil)
- 法国人物译名对照原版俄文人名表及法国国民议会档案。[雅克·夏邦-戴尔马](https://www.assemblee-nationale.fr/histoire/tables_archives/jacques-chaban-delmas.asp) · [米歇尔·波尼亚托夫斯基](https://www2.assemblee-nationale.fr/sycomore/fiche/6415)
