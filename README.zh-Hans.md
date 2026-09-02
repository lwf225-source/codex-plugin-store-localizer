# ChatGPT 插件商店汉化 / Codex 插件目录本地化启动器

[English](README.md) · [简体中文](README.zh-Hans.md) · [项目网站](https://lwf225-source.github.io/codex-plugin-store-localizer/zh-Hans/) · [下载 v0.3.0](https://github.com/lwf225-source/codex-plugin-store-localizer/releases/tag/v0.3.0)

**Codex Plugin Store Localizer** 是一个本地运行的开源启动器，为兼容的 Codex / ChatGPT 桌面应用插件商店提供中文化和 15 个语言环境。它不修改官方应用文件，不开放 TCP 调试端口，只替换“插件名＋英文原文”精确匹配的界面文字。

这是独立社区项目，**不是 OpenAI 官方项目，也不是浏览器扩展或聊天翻译工具**。Windows 已有启动器实现和自动化测试，实机界面验收仍待完成。

## 真实截图：GitHub 详情页汉化前后

![ChatGPT 插件商店汉化真实截图：GitHub 详情页英文与简体中文对照](docs/assets/before-after.png)

以下为用户于 **2026 年 9 月 2 日**提供的真实截图。GitHub 简介、推荐提示词和详情正文已显示中文；下方连接器说明仍保留英文。原图像素未修改，仅按比例排版。这证明图中可见区域的效果，不代表全部文案、所有版本或 Windows 已通过验收；截图未附操作系统和应用版本。[英文原图](docs/assets/github-detail-english.png) · [中文原图](docs/assets/github-detail-chinese.png) · [截图来源与边界](docs/coverage.md)。

<details>
<summary>查看更多目录实拍</summary>

**英文目录：热门与新品推荐**

![Codex 插件目录真实截图：热门与新品推荐中的英文说明](docs/assets/catalog-english.png)

**中文目录：效率与创意**

![Codex 插件商店中文化真实截图：Granola、Plaud、Canva 和 Figma 等插件说明](docs/assets/catalog-chinese.png)

这两张来自不同目录区域，不作为同一区域的前后对照。

</details>

## 当前版本与覆盖范围

版本：**v0.3.0**。统计时间：**2026 年 9 月**；词库快照时间以[覆盖依据](docs/coverage.md)为准。

| 内容 | 覆盖情况 |
| --- | --- |
| 简体中文 `zh-Hans` | 3,075 组卡片短说明、3,078 组详情长说明、12,487 条插件文案 |
| 其余 14 个语言环境 | 商店框架和 Gmail、GitHub、Google Drive、Google Calendar、Notion、Slack 六个热门卡片 |
| 未收录或已变更的原文 | 保持英文，不做猜测性替换 |
| macOS | 启动器检查目标应用身份及完整性；兼容性依赖具体应用构建 |
| Windows | 实验性 `.cmd` 启动器；实机验收待完成 |

15 个语言代码：`zh-Hans`、`zh-Hant`、`en`、`ja`、`ko`、`es`、`fr`、`de`、`pt-BR`、`ru`、`ar`、`hi`、`id`、`tr`、`vi`。其中 `en` 是英文语言环境。“15 个语言环境”不代表 15 种语言均覆盖整个目录，也不等于覆盖 80% 国家。条目数不是独立插件数，不承诺自动覆盖未来新增插件。

## ChatGPT 插件商店怎么设置成中文？

### macOS

准备 Python 3.11（CI 测试版本）、Git 和可通过校验的官方桌面应用；macOS 启动器还要求 `/usr/bin/python3` 可用。也可以从 Release 下载源码 ZIP，解压后进入目录，不需要 Git。

```bash
git clone https://github.com/lwf225-source/codex-plugin-store-localizer.git
cd codex-plugin-store-localizer
python3 scripts/manage.py locale zh-Hans
python3 scripts/manage.py install
```

保存工作，完全退出桌面应用，然后打开 `~/Applications/ChatGPT 插件商店汉化版.app`。进入插件商店后检查：

```bash
python3 scripts/manage.py status
```

需要同时看到 `launcher_running=true`、`state=active`、`translated_nodes>0`，并核对实际页面文字。**安装成功不等于汉化生效。**

当前 macOS 实现定位 `/Applications/ChatGPT.app`，并要求 bundle ID 为 `com.openai.codex`。不是所有名为 ChatGPT/Codex 的应用构建都兼容；不要通过重签名或关闭检查绕过失败。

### Windows（实验性）

安装 Python 3.11 后，在项目目录的 PowerShell 中执行：

```powershell
py -3.11 scripts/manage.py locale zh-Hans
py -3.11 scripts/manage.py install
```

如果自动检测不到应用，先设置官方可执行文件的真实绝对路径，再重新安装及启动。下面路径是格式示例，必须替换成你的实际安装位置：

```powershell
$env:CODEX_PLUGIN_STORE_ZH_APP_PATH = 'C:\Path\To\Official\Codex.exe'
py -3.11 scripts/manage.py install
py -3.11 scripts/manage.py launch
py -3.11 scripts/manage.py status
```

启动器位于 `%LOCALAPPDATA%\Codex Plugin Helpers\ChatGPT 插件商店汉化版.cmd`。启动前需完全退出应用。Windows 仅检查 Authenticode 状态为 `Valid`，目前**没有固定发布者证书**，请只指定可信的官方应用。

## 为什么系统设置中文，插件说明还是英文？

系统语言、应用框架文字和插件目录内容是不同层次。应用菜单已显示中文，不代表服务端目录也提供了中文说明。本项目在最终 `app://` 页面渲染层替换已收录的原文，不修改官方目录响应，也不翻译你的聊天内容。

| 方案 | 官方应用文件 | 能否影响桌面插件目录 | 注意事项 |
| --- | --- | --- | --- |
| 本项目启动器 | 不修改 | 兼容构建且原文精确匹配时可以 | 每次通过启动器打开，词库按快照维护 |
| 直接补丁修改应用 | 修改 | 取决于补丁实现 | 更新与签名检查可能导致补丁失效 |
| 普通浏览器扩展 | 不修改 | 一般仅作用于浏览器标签页 | 不会自动控制独立桌面应用的 `app://` 页面 |
| 系统或应用语言设置 | 不修改 | 取决于应用及目录是否提供翻译 | 中文菜单不保证目录文案全中文 |

## Windows 上不生效怎么办？

依次核对官方 `.exe` 路径、签名状态、启动前是否完全退出、是否进入插件目录，再查看 `status` 中的 `last_error`、`launcher_running` 与 `translated_nodes`。若签名无效，请重新安装官方应用，不要关闭校验。没有 Windows 实机验收证据前，不把自动化测试称为全面兼容。

提问可使用 [GitHub Discussions](https://github.com/lwf225-source/codex-plugin-store-localizer/discussions)，附操作系统、应用版本和已脱敏错误。请勿上传聊天记录、账户信息、令牌或含私人内容的截图。疑似漏洞按[安全政策](SECURITY.md)私下报告。

## 切换语言、验证与卸载

```bash
python3 scripts/manage.py locale ja       # 下次启动切换为日语
python3 scripts/manage.py verify          # 词库与官方应用完整性校验
python3 scripts/manage.py status          # 实际运行状态
python3 scripts/manage.py uninstall       # 退出应用后移除用户级启动器
```

Windows 将 `python3` 替换为 `py -3.11`。卸载针对本项目启动器和运行目录，不移除官方应用。

## 开发与贡献

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/test_injector.mjs
```

维护者测试环境为 Python 3.11 / Node.js 22；普通使用不需要 Node.js。欢迎根据[贡献指南](CONTRIBUTING.md)提交译文审校、脱敏复现与实机验证。当前翻译质量并不等于逐条母语人工验收。

[版本记录](CHANGELOG.md) · [覆盖依据](docs/coverage.md) · [MIT 许可证](LICENSE)
