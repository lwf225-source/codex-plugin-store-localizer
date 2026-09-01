#!/usr/bin/env python3
"""Install and manage the user-level ChatGPT plugin-store localization launcher."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from runtime_common import (
    APP_BUNDLE,
    IS_WINDOWS,
    RUNTIME_DIR,
    RUNTIME_PARENT,
    LOCALE_SETTINGS_PATH,
    STATUS_PATH,
    WRAPPER_APP,
    RuntimeLocalizerError,
    apply_private_modes,
    atomic_write_json,
    find_chatgpt_main_pids,
    pid_is_alive,
    read_json,
    utc_now,
    SUPPORTED_LOCALES,
    validate_translation_data,
    validate_coverage_data,
    validate_locale_packs,
    verify_chatgpt_signature,
)


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
TRANSLATIONS_PATH = PLUGIN_ROOT / "assets" / "dom-translations.zh-Hans.json"
COVERAGE_PATH = PLUGIN_ROOT / "assets" / "catalog-coverage.zh-Hans.json"
LOCALE_PACKS_PATH = PLUGIN_ROOT / "assets" / "locale-packs.json"
INJECTOR_PATH = PLUGIN_ROOT / "scripts" / "injector.js"


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _assert_safe_user_path(path: Path) -> None:
    home = Path.home().resolve()
    resolved_parent = path.parent.resolve()
    try:
        resolved_parent.relative_to(home)
    except ValueError as exc:
        raise RuntimeLocalizerError(f"拒绝写入用户目录以外的路径: {path}") from exc
    current = path
    while current != home and current != current.parent:
        if current.exists() and current.is_symlink():
            raise RuntimeLocalizerError(f"拒绝使用符号链接目标: {current}")
        current = current.parent


def _validate_source_tree() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Dict[str, Any]]]:
    manifest = read_json(MANIFEST_PATH)
    if not isinstance(manifest, dict) or manifest.get("name") != "codex-plugin-store-zh":
        raise RuntimeLocalizerError("插件 manifest 名称无效")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeLocalizerError("插件 manifest 缺少版本")
    translations = validate_translation_data(read_json(TRANSLATIONS_PATH))
    coverage = validate_coverage_data(read_json(COVERAGE_PATH), translations)
    locale_packs = validate_locale_packs(read_json(LOCALE_PACKS_PATH))
    required_files = [
        INJECTOR_PATH,
        PLUGIN_ROOT / "scripts" / "launcher.py",
        PLUGIN_ROOT / "scripts" / "runtime_common.py",
    ]
    for path in required_files:
        if not path.is_file() or path.is_symlink():
            raise RuntimeLocalizerError(f"插件运行时文件缺失或为符号链接: {path}")
    for source_root in (PLUGIN_ROOT / "assets", PLUGIN_ROOT / "scripts"):
        for path in source_root.rglob("*"):
            if path.is_symlink():
                raise RuntimeLocalizerError(f"插件源目录包含符号链接: {path}")
    return manifest, translations, coverage, locale_packs


def _wrapper_installed() -> bool:
    return (
        WRAPPER_APP.is_file() and not WRAPPER_APP.is_symlink()
        if IS_WINDOWS
        else WRAPPER_APP.is_dir() and not WRAPPER_APP.is_symlink()
    )


def _remove_owned_path(path: Path, expect_directory: bool) -> None:
    if not path.exists():
        return
    if path.is_symlink() or path.is_dir() != expect_directory:
        raise RuntimeLocalizerError(f"拒绝删除符号链接或异常路径: {path}")
    if expect_directory:
        shutil.rmtree(path)
    else:
        path.unlink()


def _write_wrapper_app(destination: Path) -> None:
    if IS_WINDOWS:
        runtime_variable = "%LOCALAPPDATA%\\Codex Plugin Helpers\\codex-plugin-store-zh-runtime"
        destination.write_text(
            "@echo off\r\n"
            "setlocal\r\n"
            f"set \"CODEX_PLUGIN_STORE_ZH_RUNTIME={runtime_variable}\"\r\n"
            "where py >nul 2>nul\r\n"
            "if not errorlevel 1 (\r\n"
            "  py -3 \"%CODEX_PLUGIN_STORE_ZH_RUNTIME%\\scripts\\launcher.py\"\r\n"
            "  exit /b %ERRORLEVEL%\r\n"
            ")\r\n"
            "python \"%CODEX_PLUGIN_STORE_ZH_RUNTIME%\\scripts\\launcher.py\"\r\n",
            encoding="utf-8",
        )
        return
    contents = destination / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True, mode=0o700)
    resources.mkdir(parents=True, mode=0o700)

    executable = macos / "codex-plugin-store-zh"
    launcher_path = RUNTIME_DIR / "scripts" / "launcher.py"
    executable.write_text(
        "#!/bin/zsh\nexec /usr/bin/python3 " + shlex.quote(str(launcher_path)) + "\n",
        encoding="utf-8",
    )
    os.chmod(executable, 0o755)

    info = {
        "CFBundleDevelopmentRegion": "zh_CN",
        "CFBundleDisplayName": "ChatGPT 插件商店汉化版",
        "CFBundleExecutable": "codex-plugin-store-zh",
        "CFBundleIconFile": "icon-chatgpt.icns",
        "CFBundleIdentifier": "local.codex.plugin-store-zh",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "ChatGPT 插件商店汉化版",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    }
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle, sort_keys=True)
    os.chmod(contents / "Info.plist", 0o600)

    source_icon = APP_BUNDLE / "Contents" / "Resources" / "icon-chatgpt.icns"
    if source_icon.is_file():
        shutil.copy2(source_icon, resources / "icon-chatgpt.icns")
        os.chmod(resources / "icon-chatgpt.icns", 0o600)

    result = subprocess.run(
        ["/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none", str(destination)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeLocalizerError(f"无法对用户级启动器进行本地签名: {result.stderr.strip()}")


def _swap_path(temporary: Path, destination: Path, expect_directory: bool) -> Optional[Path]:
    backup = destination.parent / f".{destination.name}.previous-{os.getpid()}"
    if backup.exists():
        raise RuntimeLocalizerError(f"检测到未清理的安装暂存目录: {backup}")
    displaced = False
    if destination.exists():
        if destination.is_symlink() or destination.is_dir() != expect_directory:
            raise RuntimeLocalizerError(f"拒绝覆盖符号链接或异常路径: {destination}")
        os.replace(destination, backup)
        displaced = True
    try:
        os.replace(temporary, destination)
    except Exception:
        if displaced and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    return backup if backup.exists() else None


def install() -> Dict[str, Any]:
    manifest, translations, coverage, locale_packs = _validate_source_tree()
    # Installation only copies this personal plugin into user-owned helper
    # paths. Full app integrity is enforced immediately before every launch.
    verify_chatgpt_signature(require_integrity=False)
    _assert_safe_user_path(RUNTIME_DIR)
    _assert_safe_user_path(WRAPPER_APP)
    RUNTIME_PARENT.mkdir(parents=True, exist_ok=True, mode=0o700)
    WRAPPER_APP.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if RUNTIME_PARENT.is_symlink() or WRAPPER_APP.parent.is_symlink():
        raise RuntimeLocalizerError("拒绝使用符号链接安装父目录")

    runtime_temp = Path(tempfile.mkdtemp(prefix=".codex-plugin-store-zh-install-", dir=str(RUNTIME_PARENT)))
    wrapper_temp = WRAPPER_APP.parent / f".{WRAPPER_APP.name}.install-{os.getpid()}"
    runtime_backup: Optional[Path] = None
    wrapper_backup: Optional[Path] = None
    runtime_committed = False
    wrapper_committed = False
    try:
        runtime_assets = runtime_temp / "assets"
        runtime_assets.mkdir(mode=0o700)
        shutil.copy2(TRANSLATIONS_PATH, runtime_assets / TRANSLATIONS_PATH.name)
        shutil.copy2(COVERAGE_PATH, runtime_assets / COVERAGE_PATH.name)
        shutil.copy2(LOCALE_PACKS_PATH, runtime_assets / LOCALE_PACKS_PATH.name)
        shutil.copytree(
            PLUGIN_ROOT / "scripts",
            runtime_temp / "scripts",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        atomic_write_json(
            runtime_temp / "installation.json",
            {
                "schema_version": 1,
                "plugin_name": manifest["name"],
                "plugin_version": manifest["version"],
                "installed_at": utc_now(),
                "translation_entries": len(translations["plugin_descriptions"]),
                "plugin_text_entries": len(translations["plugin_texts"]),
                "public_catalog_records": coverage["counts"]["public_records"],
                "catalog_fetched_at": coverage.get("catalog_fetched_at"),
                "supported_locales": list(SUPPORTED_LOCALES),
            },
        )
        apply_private_modes(runtime_temp, executable_names={"launcher.py", "manage.py"})

        if wrapper_temp.exists():
            _remove_owned_path(wrapper_temp, expect_directory=not IS_WINDOWS)
        _write_wrapper_app(wrapper_temp)

        runtime_backup = _swap_path(runtime_temp, RUNTIME_DIR, expect_directory=True)
        runtime_committed = True
        wrapper_backup = _swap_path(wrapper_temp, WRAPPER_APP, expect_directory=not IS_WINDOWS)
        wrapper_committed = True

        status = {
            "schema_version": 1,
            "state": "installed_not_running",
            "plugin_version": manifest["version"],
            "launcher_pid": None,
            "app_pid": None,
            "attached_targets": 0,
            "translated_nodes": 0,
            "unmatched_sources": 0,
            "unmatched_detail_sources": 0,
            "unmatched_plugin_text_sources": 0,
            "last_report_at": None,
            "last_error": None,
            "updated_at": utc_now(),
        }
        atomic_write_json(STATUS_PATH, status)
        cleanup_warnings = []
        for backup in (runtime_backup, wrapper_backup):
            if backup is None:
                continue
            try:
                shutil.rmtree(backup)
            except OSError as exc:
                # The new runtime and wrapper are already installed and their
                # status is durable. A stale hidden backup is safer than
                # rolling back a successful install after its peer backup was
                # already removed.
                cleanup_warnings.append(f"未清理旧备份 {backup}: {exc}")
        return {
            "ok": True,
            "plugin_version": manifest["version"],
            "translation_entries": len(translations["plugin_descriptions"]),
            "detail_entries": len(translations["plugin_details"]),
            "plugin_text_entries": len(translations["plugin_texts"]),
            "public_catalog_records": coverage["counts"]["public_records"],
            "supported_locales": list(SUPPORTED_LOCALES),
            "runtime_dir": str(RUNTIME_DIR),
            "wrapper_app": str(WRAPPER_APP),
            "chatgpt_restarted": False,
            "cleanup_warnings": cleanup_warnings,
        }
    except Exception:
        if wrapper_committed and WRAPPER_APP.exists():
            _remove_owned_path(WRAPPER_APP, expect_directory=not IS_WINDOWS)
        if wrapper_backup is not None and wrapper_backup.exists():
            os.replace(wrapper_backup, WRAPPER_APP)
        if runtime_committed and RUNTIME_DIR.exists():
            shutil.rmtree(RUNTIME_DIR)
        if runtime_backup is not None and runtime_backup.exists():
            os.replace(runtime_backup, RUNTIME_DIR)
        raise
    finally:
        if runtime_temp.exists():
            shutil.rmtree(runtime_temp)
        if wrapper_temp.exists():
            _remove_owned_path(wrapper_temp, expect_directory=not IS_WINDOWS)


def status() -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "runtime_installed": RUNTIME_DIR.is_dir() and not RUNTIME_DIR.is_symlink(),
        "wrapper_installed": _wrapper_installed(),
        "runtime_dir": str(RUNTIME_DIR),
        "wrapper_app": str(WRAPPER_APP),
    }
    try:
        payload["chatgpt_main_pids"] = find_chatgpt_main_pids()
    except RuntimeLocalizerError as exc:
        # Sandboxed Codex tasks may not be allowed to enumerate processes. The
        # recorded launcher PID remains independently checkable with kill(0).
        payload["chatgpt_main_pids"] = None
        payload["process_check_error"] = str(exc)
    if STATUS_PATH.is_file() and not STATUS_PATH.is_symlink():
        try:
            recorded = read_json(STATUS_PATH)
            if isinstance(recorded, dict):
                payload.update(recorded)
        except RuntimeLocalizerError as exc:
            payload["status_error"] = str(exc)
    payload["launcher_running"] = pid_is_alive(payload.get("launcher_pid"))
    payload["supported_locales"] = list(SUPPORTED_LOCALES)
    if LOCALE_SETTINGS_PATH.is_file() and not LOCALE_SETTINGS_PATH.is_symlink():
        try:
            preference = read_json(LOCALE_SETTINGS_PATH)
            if isinstance(preference, dict) and preference.get("locale") in SUPPORTED_LOCALES:
                payload["selected_locale"] = preference["locale"]
        except RuntimeLocalizerError:
            pass
    return payload


def locale(value: Optional[str] = None) -> Dict[str, Any]:
    """Read or set the persisted locale used by the next launcher start."""

    if value is None:
        current = status().get("selected_locale", "zh-Hans")
        return {"ok": True, "locale": current, "supported_locales": list(SUPPORTED_LOCALES)}
    if value not in SUPPORTED_LOCALES:
        raise RuntimeLocalizerError("不支持的语言代码；请先运行 locale 查看可选项")
    _assert_safe_user_path(LOCALE_SETTINGS_PATH)
    RUNTIME_PARENT.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write_json(LOCALE_SETTINGS_PATH, {"schema_version": 1, "locale": value, "updated_at": utc_now()})
    return {"ok": True, "locale": value, "takes_effect": "下次从汉化启动器启动时"}


def launch() -> Dict[str, Any]:
    if not _wrapper_installed():
        raise RuntimeLocalizerError("尚未安装汉化版启动器")
    pids = find_chatgpt_main_pids()
    if pids:
        raise RuntimeLocalizerError("ChatGPT 已在运行；请先完全退出，或在明确同意后使用 restart")
    _open_wrapper()
    return {"ok": True, "launched": True, "wrapper_app": str(WRAPPER_APP)}


def _open_wrapper() -> None:
    if IS_WINDOWS:
        try:
            subprocess.Popen(
                ["cmd.exe", "/d", "/s", "/c", str(WRAPPER_APP)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            raise RuntimeLocalizerError(f"无法打开 Windows 汉化启动器: {exc}") from exc
        return
    result = subprocess.run(
        ["/usr/bin/open", str(WRAPPER_APP)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeLocalizerError(f"无法打开汉化版启动器: {result.stderr.strip()}")


def _request_graceful_quit() -> None:
    if not IS_WINDOWS:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", 'tell application id "com.openai.codex" to quit'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            raise RuntimeLocalizerError("ChatGPT 正常退出请求失败")
        return
    pids = find_chatgpt_main_pids()
    if not pids:
        return
    script = "foreach ($id in $args) { $p=Get-Process -Id $id -ErrorAction SilentlyContinue; if ($p) { [void]$p.CloseMainWindow() } }"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script, *[str(pid) for pid in pids]],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise RuntimeLocalizerError("Windows Codex 正常退出请求失败")


def _restart_worker() -> int:
    try:
        _request_graceful_quit()
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if not find_chatgpt_main_pids():
                break
            time.sleep(0.5)
        if find_chatgpt_main_pids():
            raise RuntimeLocalizerError("ChatGPT 在 45 秒内未完全退出；未强制结束进程")
        time.sleep(1.0)
        _open_wrapper()
        return 0
    except Exception as exc:
        try:
            atomic_write_json(
                STATUS_PATH,
                {
                    "schema_version": 1,
                    "state": "error",
                    "launcher_pid": None,
                    "app_pid": None,
                    "last_error": str(exc),
                    "updated_at": utc_now(),
                },
            )
        except Exception:
            pass
        return 1


def restart() -> Dict[str, Any]:
    if not _wrapper_installed():
        raise RuntimeLocalizerError("尚未安装汉化版启动器")
    verify_chatgpt_signature()
    worker = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_restart_worker"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return {
        "ok": True,
        "restart_scheduled": True,
        "worker_pid": worker.pid,
        "force_kill_allowed": False,
    }


def uninstall() -> Dict[str, Any]:
    current = status()
    if current.get("launcher_running"):
        raise RuntimeLocalizerError("汉化启动器仍在运行；请先退出 ChatGPT 再卸载")
    removed = []
    for path in (WRAPPER_APP, RUNTIME_DIR):
        _assert_safe_user_path(path)
        if path.exists():
            _remove_owned_path(path, expect_directory=path == RUNTIME_DIR)
            removed.append(str(path))
    return {"ok": True, "removed": removed}


def verify() -> Dict[str, Any]:
    manifest, translations, coverage, locale_packs = _validate_source_tree()
    signature = verify_chatgpt_signature()
    return {
        "ok": True,
        "plugin_version": manifest["version"],
        "translation_entries": len(translations["plugin_descriptions"]),
        "detail_entries": len(translations["plugin_details"]),
        "plugin_text_entries": len(translations["plugin_texts"]),
        "host_strings": len(translations["host_strings"]),
        "public_catalog_records": coverage["counts"]["public_records"],
        "catalog_fetched_at": coverage.get("catalog_fetched_at"),
        "supported_locales": list(SUPPORTED_LOCALES),
        "starter_locale_packs": len(locale_packs),
        "signature": signature,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("install", "status", "locale", "launch", "restart", "uninstall", "verify", "_restart_worker"),
    )
    parser.add_argument("locale", nargs="?", help="语言代码；仅 locale 命令使用")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.command == "_restart_worker":
        return _restart_worker()
    commands = {
        "install": install,
        "status": status,
        "launch": launch,
        "restart": restart,
        "uninstall": uninstall,
        "verify": verify,
    }
    try:
        result = locale(args.locale) if args.command == "locale" else commands[args.command]()
        _print_json(result)
        return 0
    except RuntimeLocalizerError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 2
    except Exception as exc:
        _print_json({"ok": False, "error": f"未预期错误: {exc}"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
