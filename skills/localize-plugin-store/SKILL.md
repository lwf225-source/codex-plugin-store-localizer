---
name: localize-plugin-store
description: "安装、检查、启动或卸载 Codex 官方插件目录的 15 语言运行时注入器；用于用户明确要求本地化桌面应用内置插件商店时，不用于翻译普通文档。"
---

# Codex 插件商店本地化

需要查看当前远端目录缓存和本地词库的覆盖差距时，可运行只读报告：

```bash
/usr/bin/python3 ../../scripts/catalog_report.py --limit 20
```

报告不会联网、不会改动官方缓存，也不会自动生成或写入翻译。

需要更新全量词库时，使用 `generate_catalog_translations.py`。生成器以官方
目录全部 `LISTED` 项目为分母，使用稳定项目 ID 生成覆盖清单；运行时词库
按项目名和英文原文精确匹配。不得再使用固定精选项目列表作为全量依据。

使用插件根目录的 `scripts/manage.py` 管理独立启动器。启动器通过 Chromium 的私有 pipe 调试通道，将固定、本地可审计的词库注入最终渲染页面。简中使用全量词库 `assets/dom-translations.zh-Hans.json`；其他语言使用审计过的 `assets/locale-packs.json`，未收录的目录内容保留英文。

## 语言

支持 15 种语言：`zh-Hans`、`zh-Hant`、`en`、`ja`、`ko`、`es`、`fr`、`de`、`pt-BR`、`ru`、`ar`、`hi`、`id`、`tr`、`vi`。

查看当前选择和支持列表：

```bash
/usr/bin/python3 ../../scripts/manage.py locale
```

切换语言（下次从启动器打开时生效）：

```bash
/usr/bin/python3 ../../scripts/manage.py locale ja
```

也可设置进程环境变量 `CODEX_PLUGIN_STORE_LOCALE` 临时覆盖保存的选择。阿拉伯语会在插件目录页启用从右到左排版。

## 边界

- 不修改 macOS `ChatGPT.app`、Windows `.exe`、官方插件源码、公共目录响应或 Codex 目录缓存。
- 只处理 `app://` 渲染目标，且只在插件名称与英文原文都匹配时替换说明。
- 不开放 TCP 调试端口，不提供通用 JavaScript 执行接口，不上传 DOM 或会话内容。
- 英文原文或 DOM 结构变化时停止匹配并报告，不猜测替换。
- 全量词库使用索引和批量 DOM 扫描；注入异常时保留 Codex 正常运行并降级为英文。
- 普通方式启动没有注入效果；必须从安装后的“ChatGPT 插件商店汉化版”入口启动。macOS 入口是 `.app`，Windows 入口是 `%LOCALAPPDATA%\\Codex Plugin Helpers\\ChatGPT 插件商店汉化版.cmd`。

## 工作流

脚本路径相对于本 `SKILL.md` 所在目录。先运行只读检查：

```bash
/usr/bin/python3 ../../scripts/manage.py status
```

安装或更新稳定运行时目录和用户级启动入口（macOS `.app` / Windows `.cmd`）是外部写操作；必须有用户当前请求的明确授权：

```bash
/usr/bin/python3 ../../scripts/manage.py install
```

安装不会自动退出当前 ChatGPT。真实界面验证需要先保存当前任务，完全退出 ChatGPT，再从新入口启动。只有用户明确同意本次退出和重启时才可执行：

```bash
/usr/bin/python3 ../../scripts/manage.py restart
```

运行状态验证：

```bash
/usr/bin/python3 ../../scripts/manage.py status
```

只有 `launcher_running=true`、`state=active` 且 `translated_nodes>0` 时，才能说注入器已翻译过真实页面节点；最终仍应请用户在官方“插件”页确认可见文案。仅安装成功、词库匹配或启动器存在都不等于界面已汉化。

用户明确要求卸载时，先运行 `status`，再执行：

```bash
/usr/bin/python3 ../../scripts/manage.py uninstall
```

## 安全停止条件

- ChatGPT 仍在普通模式运行时，`restart` 之外的启动命令应拒绝启动第二个实例。
- macOS：ChatGPT 签名的 Identifier、TeamIdentifier 或完整性校验不通过时停止注入。Windows：`.exe` 的 Authenticode 签名无效时停止注入；若自动探测失败，要求用户设置 `CODEX_PLUGIN_STORE_ZH_APP_PATH` 为绝对 `.exe` 路径。
- 找不到 Python、私有 pipe 通道或 `app://` 页面时报告失败，不降级为 TCP 端口。Windows 使用 Chromium 的继承句柄和 `--remote-debugging-io-pipes`，不监听网络端口。
- 词库不允许携带 JavaScript；必须经 JSON 校验后使用 Base64 数据注入固定脚本。
- 日志只记录版本、PID、目标数和替换计数，不记录 DOM、URL 参数或会话内容。

扩充翻译时先运行 `scripts/generate_catalog_translations.py` 生成词库和
`assets/catalog-coverage.zh-Hans.json`。只有全量缺失数为 0、压力测试和插件
根目录测试全部通过后，才可执行 `install` 更新稳定运行时副本。
