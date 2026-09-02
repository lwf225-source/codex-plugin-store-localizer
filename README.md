# Codex Plugin Store Localizer — 15-Language Localization for macOS and Windows

> An open-source, local-first launcher that translates the built-in Codex / ChatGPT desktop plugin store into 15 locales—without modifying the official app or opening a TCP debug port.

[![Tests](https://github.com/lwf225-source/codex-plugin-store-localizer/actions/workflows/test.yml/badge.svg)](https://github.com/lwf225-source/codex-plugin-store-localizer/actions/workflows/test.yml)
[![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-111827?style=flat-square)](#platform-support)
[![Locales](https://img.shields.io/badge/locales-15-2563eb?style=flat-square)](#supported-languages-and-translation-coverage)
[![License](https://img.shields.io/badge/license-MIT-16a34a?style=flat-square)](LICENSE)

**Codex Plugin Store Localizer** makes the English-first plugin directory easier to use in Chinese, Japanese, Korean, Spanish, French, German, Portuguese, Arabic, Hindi, and other widely used languages. It launches the signed desktop app through Chromium's private debugging pipe, then replaces only exact, audited strings in the final `app://` plugin-store rendering layer.

This community project is **not affiliated with or endorsed by OpenAI**. It does not modify the macOS app bundle, the Windows executable, official plugins, or official catalog responses.

## At a glance

| Question | Answer |
| --- | --- |
| What does it localize? | The built-in Codex / ChatGPT desktop plugin directory |
| Which systems are supported? | macOS 13+ and Windows |
| How many locales are included? | 15 |
| Is the entire catalog translated? | Simplified Chinese: full pack; the other 14 locales: store shell + six Popular cards |
| Does it patch the official app? | No |
| Does it expose a remote debugging port? | No; it uses an inherited local pipe |
| Does it upload page or account data? | No |
| License | [MIT](LICENSE) |

## Why use this Codex plugin-store localizer?

- **Private by design** — uses a local inherited-pipe Chrome DevTools Protocol connection and never opens a TCP debugging port.
- **Fail closed** — a translation is applied only when both the plugin name and the original English text match; unknown content stays unchanged.
- **Auditable translations** — locale packs are schema-validated JSON and cannot carry JavaScript.
- **Cross-platform launcher** — installs a user-level macOS `.app` wrapper or Windows `.cmd` wrapper.
- **Official app integrity checks** — verifies macOS code-signing integrity or Windows Authenticode status before injection.
- **No runtime content upload** — DOM content, account data, and chat content remain on the machine.

## Supported languages and translation coverage

The project includes these 15 locale codes:

`zh-Hans` · `zh-Hant` · `en` · `ja` · `ko` · `es` · `fr` · `de` · `pt-BR` · `ru` · `ar` · `hi` · `id` · `tr` · `vi`

| Translation coverage | Locales |
| --- | --- |
| Full plugin-catalog pack | Simplified Chinese (`zh-Hans`) |
| Store shell + six Popular plugin cards | Traditional Chinese, English, Japanese, Korean, Spanish, French, German, Brazilian Portuguese, Russian, Arabic, Hindi, Indonesian, Turkish, and Vietnamese |

The 14 starter packs translate the plugin-store shell and the Popular cards for **Gmail, GitHub, Google Drive, Google Calendar, Notion, and Slack**. Items without an audited translation deliberately remain in English. “15 locales” therefore does **not** mean 15 full-catalog translations.

The Simplified Chinese pack currently contains 3,075 short-description pairs, 3,078 long-description pairs, and 12,487 plugin-text entries. Coverage is validated against the cached public catalog during testing.

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/lwf225-source/codex-plugin-store-localizer.git
cd codex-plugin-store-localizer

# Optional: choose the locale used on the next launcher start.
python3 scripts/manage.py locale ja

# Install a user-level launcher. This never patches the official application.
python3 scripts/manage.py install
```

### 2. Launch and verify the real page

Save your work, fully quit the desktop app, and open the newly installed **ChatGPT Plugin Store Localizer** launcher. Then run:

```bash
python3 scripts/manage.py status
```

Only `launcher_running=true`, `state=active`, and `translated_nodes>0` confirm that an actual plugin-store page has been localized. A successful installation alone is not proof that page translation is active.

### Useful commands

```bash
python3 scripts/manage.py locale zh-Hans  # Select a locale
python3 scripts/manage.py launch          # Start through the safe launcher
python3 scripts/manage.py verify          # Verify the installation
python3 scripts/manage.py status          # Inspect live translation state
python3 scripts/manage.py uninstall       # Remove the user-level launcher
```

## Platform support

| Platform | Installed launcher | Integrity requirement |
| --- | --- | --- |
| macOS 13+ | User-level `.app` wrapper | Valid code-signing identity and full bundle integrity |
| Windows | `%LOCALAPPDATA%\\Codex Plugin Helpers\\ChatGPT Plugin Store Localizer.cmd` | Valid Authenticode status |

If the official app fails its integrity check, the launcher refuses to inject. Reinstall the official desktop app instead of bypassing this guard.

## How it works

```text
User-level launcher
  → signed Codex / ChatGPT desktop app + private Chromium pipe
  → fixed injector + schema-validated local JSON locale pack
  → exact text replacement on app:// plugin-directory pages
```

The injector is intentionally narrow. It cannot load JavaScript from translation data, call remote runtime services, modify official catalog responses, or alter normal web pages.

## Security and privacy model

- No application patching or binary replacement
- No TCP remote-debugging port
- No arbitrary script payload in locale packs
- No upload of DOM, account, or conversation content
- Exact source-text matching instead of broad DOM rewriting
- Integrity verification before launch

Security reports should follow the private process in [SECURITY.md](SECURITY.md). Please do not publish suspected vulnerabilities in a public issue.

## Development and testing

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/test_injector.mjs
```

The catalog translation generator is a maintenance tool; the runtime launcher never calls it. Contribution requirements are documented in [CONTRIBUTING.md](CONTRIBUTING.md).

## Frequently asked questions

### How do I translate or localize the Codex plugin store?

Clone this repository, select one of the 15 locale codes with `python3 scripts/manage.py locale <code>`, run `python3 scripts/manage.py install`, and start Codex / ChatGPT from the installed localizer launcher. Use `python3 scripts/manage.py status` to verify that visible nodes were actually translated.

### Does the localizer modify `ChatGPT.app` or the Windows executable?

No. It creates a separate user-level launcher and leaves the official application files unchanged. It also checks the official application's integrity before injection.

### Does it work on Windows as well as macOS?

Yes. The repository includes a macOS app-wrapper flow and a Windows `.cmd` launcher flow. The Windows path uses Authenticode verification; the macOS path uses code-signature identity and full-integrity checks.

### Which languages have full plugin-catalog translation?

Simplified Chinese (`zh-Hans`) is the only full catalog pack today. The other 14 locales translate the store framework and six Popular plugin cards; untranslated catalog content stays in English.

### Does it open a debugging port or send data to a server?

No. Runtime communication uses Chromium's private inherited pipe, not a listening TCP port. The localizer does not upload plugin-page DOM, account information, or chat content.

### Is this an official OpenAI project?

No. This is an independent open-source community project and is not affiliated with or endorsed by OpenAI. Codex, ChatGPT, and plugin names belong to their respective owners.

## 中文说明

**Codex Plugin Store Localizer** 是一个支持 macOS 与 Windows 的开源插件商店汉化 / 多语言本地化启动器。它不修改官方应用、不开放 TCP 调试端口，而是在最终 `app://` 插件目录页面中对“插件名 + 英文原文”精确匹配后替换文字。

当前提供 15 个语言环境：简体中文为全量插件目录词库；其余 14 种语言覆盖商店框架和 Gmail、GitHub、Google Drive、Google Calendar、Notion、Slack 六个热门插件卡片。未审校内容会保留英文，不会被错误替换。

安装后必须通过 `python3 scripts/manage.py status` 检查真实页面状态；只有 `launcher_running=true`、`state=active`、`translated_nodes>0` 才能证明汉化已经在页面生效。

## Project links

- [Source code and releases](https://github.com/lwf225-source/codex-plugin-store-localizer)
- [Contribution guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [MIT license](LICENSE)

## License

MIT © Contributors
