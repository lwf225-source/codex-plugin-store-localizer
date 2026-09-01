# Codex Plugin Store Localizer

> Localize the built-in Codex / ChatGPT plugin directory into 15 languages — without patching the desktop app or exposing a debug port.

[![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-111827?style=flat-square)](#platform-support)
[![Locales](https://img.shields.io/badge/locales-15-2563eb?style=flat-square)](#locales)
[![License](https://img.shields.io/badge/license-MIT-16a34a?style=flat-square)](LICENSE)

The official plugin directory is useful, but much of its UI and catalog content is English-only. This local-first launcher starts the desktop app with Chromium's private debugging pipe and replaces only exact, audited strings in the final `app://` rendering layer.

It is **not affiliated with OpenAI** and does not modify the app bundle, the Windows executable, official plugins, or official catalog responses.

## Why this project

- **Private by design** — uses a local inherited-pipe CDP connection; it never opens a TCP debugging port.
- **Fail closed** — translations apply only when both the plugin name and original English text match; unknown content stays unchanged.
- **Auditable data** — translation packs are JSON, schema-validated, and cannot carry JavaScript.
- **Cross-platform launcher** — macOS app wrapper and Windows `.cmd` wrapper.
- **No content upload** — no DOM, account data, or chat content leaves the machine at runtime.

## Locales

`zh-Hans` · `zh-Hant` · `en` · `ja` · `ko` · `es` · `fr` · `de` · `pt-BR` · `ru` · `ar` · `hi` · `id` · `tr` · `vi`

| Coverage | Locales |
| --- | --- |
| Full plugin-catalog pack | Simplified Chinese (`zh-Hans`) |
| Store framework + Popular cards | The other 14 locales |

The 14 starter packs localize the store shell and the Popular cards for Gmail, GitHub, Google Drive, Google Calendar, Notion, and Slack. Catalog items without an audited translation deliberately remain English.

## Quick start

```bash
git clone https://github.com/lwf225-source/codex-plugin-store-localizer.git
cd codex-plugin-store-localizer

# Optional: choose the locale used on the next launcher start.
python3 scripts/manage.py locale ja

# Install a user-level launcher. This never patches the official application.
python3 scripts/manage.py install
```

Save your work, fully quit the desktop app, then launch it from the newly installed **ChatGPT Plugin Store Localizer** entry. Run the following afterwards to verify actual page translation:

```bash
python3 scripts/manage.py status
```

Only `launcher_running=true`, `state=active`, and `translated_nodes>0` prove that a real page has been localized.

## Platform support

| Platform | Launcher | App integrity check |
| --- | --- | --- |
| macOS 13+ | User-level `.app` wrapper | Code signature identity and full integrity |
| Windows | `%LOCALAPPDATA%\\Codex Plugin Helpers\\ChatGPT Plugin Store Localizer.cmd` | Authenticode status |

If the app cannot pass its integrity check, the launcher refuses to inject. Reinstall the official desktop app rather than bypassing this guard.

## How it works

```text
User launcher
  → signed desktop app + private Chromium pipe
  → fixed injector + schema-validated local JSON pack
  → exact text replacement on app:// plugin-directory pages
```

The injector is intentionally narrow: it does not expose arbitrary JavaScript execution, call remote runtime services, or alter normal web pages.

## Development

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/test_injector.mjs
```

The full Simplified Chinese dictionary is checked against the cached public catalog. The catalog translation generator is a maintenance tool; it is not called by the runtime launcher.

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) before submitting changes, especially translation packs or launcher code.

## 中文说明

这是一个本地优先的 Codex / ChatGPT 插件目录本地化工具：不修改官方应用、不开放调试端口，只在最终 `app://` 渲染层对“插件名 + 英文原文”精确匹配后替换文字。

当前支持 15 种语言。简中为全量目录词库；其余语言覆盖商店框架和热门卡片，未审校的条目会保留英文。请勿绕过 macOS 代码签名或 Windows Authenticode 校验。

## License

MIT © Contributors
