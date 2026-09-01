#!/usr/bin/env python3
"""Shared validation and status helpers for the runtime plugin-store localizer."""

from __future__ import annotations

import json
import hashlib
import os
import platform
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


IS_WINDOWS = os.name == "nt"
EXPECTED_IDENTIFIER = "com.openai.codex"
EXPECTED_TEAM_IDENTIFIER = "2DC432GLL2"


def _windows_app_candidates() -> List[Path]:
    configured = os.environ.get("CODEX_PLUGIN_STORE_ZH_APP_PATH", "").strip()
    candidates: List[Path] = [Path(configured)] if configured else []
    local_app_data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    program_files = Path(os.environ.get("ProgramFiles") or Path("C:/Program Files"))
    for root, product, executable in (
        (local_app_data, "Programs/ChatGPT", "ChatGPT.exe"),
        (local_app_data, "ChatGPT", "ChatGPT.exe"),
        (local_app_data, "Programs/Codex", "Codex.exe"),
        (program_files, "ChatGPT", "ChatGPT.exe"),
        (program_files, "Codex", "Codex.exe"),
    ):
        candidates.append(root / product / executable)
    return candidates


def _resolve_app_binary() -> Path:
    if not IS_WINDOWS:
        return Path("/Applications/ChatGPT.app/Contents/MacOS/ChatGPT")
    for candidate in _windows_app_candidates():
        if candidate.is_file():
            return candidate
    configured = os.environ.get("CODEX_PLUGIN_STORE_ZH_APP_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path()


APP_BINARY = _resolve_app_binary()
APP_BUNDLE = APP_BINARY.parent.parent if not IS_WINDOWS else APP_BINARY.parent
RUNTIME_PARENT = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Codex Plugin Helpers"
    if IS_WINDOWS
    else Path.home() / "Library" / "Application Support" / "Codex Plugin Helpers"
)
RUNTIME_DIR = RUNTIME_PARENT / "codex-plugin-store-zh-runtime"
WRAPPER_APP = (
    RUNTIME_PARENT / "ChatGPT 插件商店汉化版.cmd"
    if IS_WINDOWS
    else Path.home() / "Applications" / "ChatGPT 插件商店汉化版.app"
)
STATUS_PATH = RUNTIME_DIR / "status.json"
LOCALE_SETTINGS_PATH = RUNTIME_PARENT / "locale.json"

# The launcher only accepts these audited, bundled locale packs.  Do not turn
# this into an arbitrary file path supplied by the environment: the injected
# payload must remain local, schema-validated data.
SUPPORTED_LOCALES = (
    "zh-Hans",
    "zh-Hant",
    "en",
    "ja",
    "ko",
    "es",
    "fr",
    "de",
    "pt-BR",
    "ru",
    "ar",
    "hi",
    "id",
    "tr",
    "vi",
)
DEFAULT_LOCALE = "zh-Hans"


class RuntimeLocalizerError(RuntimeError):
    """Raised when a fail-closed precondition is not met."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeLocalizerError(f"无法读取 JSON {path}: {exc}") from exc


def validate_translation_data(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 3:
        raise RuntimeLocalizerError("词库 schema_version 必须为 3")
    allowed_top_level_keys = {
        "schema_version",
        "locale",
        "plugin_descriptions",
        "plugin_details",
        "plugin_texts",
        "host_strings",
    }
    if set(payload) != allowed_top_level_keys:
        raise RuntimeLocalizerError("词库顶层字段不符合固定结构")
    if payload.get("locale") not in SUPPORTED_LOCALES:
        raise RuntimeLocalizerError("词库 locale 不在受支持语言列表中")

    descriptions = payload.get("plugin_descriptions")
    if not isinstance(descriptions, list) or not descriptions:
        raise RuntimeLocalizerError("词库 plugin_descriptions 必须是非空数组")

    allowed_description_keys = {"display_name", "source_short", "target_short"}
    seen_pairs = set()
    for index, item in enumerate(descriptions, start=1):
        if not isinstance(item, dict) or set(item) != allowed_description_keys:
            raise RuntimeLocalizerError(f"第 {index} 个插件说明字段不符合固定结构")
        display_name = item.get("display_name")
        sources = item.get("source_short")
        target = item.get("target_short")
        if not isinstance(display_name, str) or not display_name.strip():
            raise RuntimeLocalizerError(f"第 {index} 个 display_name 必须是非空字符串")
        if not isinstance(target, str) or not target.strip():
            raise RuntimeLocalizerError(f"第 {index} 个 target_short 必须是非空字符串")
        if not isinstance(sources, list) or not sources:
            raise RuntimeLocalizerError(f"第 {index} 个 source_short 必须是非空数组")
        for source in sources:
            if not isinstance(source, str) or not source.strip():
                raise RuntimeLocalizerError(f"第 {index} 个英文原文必须是非空字符串")
            pair = (display_name, source)
            if pair in seen_pairs:
                raise RuntimeLocalizerError(f"词库存在重复匹配: {display_name} / {source}")
            seen_pairs.add(pair)

    details = payload.get("plugin_details")
    if not isinstance(details, list):
        raise RuntimeLocalizerError("词库 plugin_details 必须是数组")
    known_display_names = {item[0] for item in seen_pairs}
    seen_detail_pairs = set()
    allowed_detail_keys = {"display_name", "source_long", "target_long"}
    for index, item in enumerate(details, start=1):
        if not isinstance(item, dict) or set(item) != allowed_detail_keys:
            raise RuntimeLocalizerError(f"第 {index} 个插件详情字段不符合固定结构")
        display_name = item.get("display_name")
        sources = item.get("source_long")
        target = item.get("target_long")
        if not isinstance(display_name, str) or display_name not in known_display_names:
            raise RuntimeLocalizerError(f"第 {index} 个详情 display_name 必须已存在于卡片词库")
        if not isinstance(target, str) or not target.strip():
            raise RuntimeLocalizerError(f"第 {index} 个 target_long 必须是非空字符串")
        if not isinstance(sources, list) or not sources:
            raise RuntimeLocalizerError(f"第 {index} 个 source_long 必须是非空数组")
        for source in sources:
            if not isinstance(source, str) or not source.strip():
                raise RuntimeLocalizerError(f"第 {index} 个详情英文原文必须是非空字符串")
            pair = (display_name, source)
            if pair in seen_detail_pairs:
                raise RuntimeLocalizerError(f"词库存在重复详情匹配: {display_name} / {source}")
            seen_detail_pairs.add(pair)

    plugin_texts = payload.get("plugin_texts")
    if not isinstance(plugin_texts, list):
        raise RuntimeLocalizerError("词库 plugin_texts 必须是数组")
    allowed_plugin_text_keys = {"display_name", "kind", "source", "target"}
    allowed_plugin_text_kinds = {
        "detail_short",
        "prompt",
        "skill_name",
        "skill_description",
    }
    seen_plugin_text_pairs = set()
    for index, item in enumerate(plugin_texts, start=1):
        if not isinstance(item, dict) or set(item) != allowed_plugin_text_keys:
            raise RuntimeLocalizerError(f"第 {index} 个插件界面文案字段不符合固定结构")
        display_name = item.get("display_name")
        kind = item.get("kind")
        source = item.get("source")
        target = item.get("target")
        if not isinstance(display_name, str) or display_name not in known_display_names:
            raise RuntimeLocalizerError(f"第 {index} 个界面文案 display_name 必须已存在于卡片词库")
        if kind not in allowed_plugin_text_kinds:
            raise RuntimeLocalizerError(f"第 {index} 个界面文案 kind 不受支持")
        if not isinstance(source, str) or not source.strip():
            raise RuntimeLocalizerError(f"第 {index} 个界面文案英文原文必须是非空字符串")
        if not isinstance(target, str) or not target.strip():
            raise RuntimeLocalizerError(f"第 {index} 个界面文案中文必须是非空字符串")
        pair = (display_name, kind, source)
        if pair in seen_plugin_text_pairs:
            raise RuntimeLocalizerError(f"词库存在重复界面文案匹配: {display_name} / {kind} / {source}")
        seen_plugin_text_pairs.add(pair)

    host_strings = payload.get("host_strings")
    if not isinstance(host_strings, list):
        raise RuntimeLocalizerError("词库 host_strings 必须是数组")
    seen_host_sources = set()
    for index, item in enumerate(host_strings, start=1):
        if not isinstance(item, dict) or set(item) != {"source", "target"}:
            raise RuntimeLocalizerError(f"第 {index} 个宿主文案字段不符合固定结构")
        source = item.get("source")
        target = item.get("target")
        if not isinstance(source, str) or not source.strip():
            raise RuntimeLocalizerError(f"第 {index} 个宿主英文原文必须是非空字符串")
        if not isinstance(target, str) or not target.strip():
            raise RuntimeLocalizerError(f"第 {index} 个宿主中文必须是非空字符串")
        if source in seen_host_sources:
            raise RuntimeLocalizerError(f"宿主文案存在重复英文原文: {source}")
        seen_host_sources.add(source)

    return payload


def validate_locale_packs(payload: Any) -> Dict[str, Dict[str, Any]]:
    """Validate the compact, bundled packs used outside the full Chinese set."""

    if not isinstance(payload, dict) or set(payload) != {"schema_version", "locales"}:
        raise RuntimeLocalizerError("多语言词库顶层字段不符合固定结构")
    if payload.get("schema_version") != 1 or not isinstance(payload.get("locales"), dict):
        raise RuntimeLocalizerError("多语言词库 schema_version 必须为 1")
    locales = payload["locales"]
    expected = set(SUPPORTED_LOCALES) - {"zh-Hans"}
    if set(locales) != expected:
        raise RuntimeLocalizerError("多语言词库必须包含全部受支持的非简中语言")
    for locale, translation in locales.items():
        if not isinstance(translation, dict) or translation.get("locale") != locale:
            raise RuntimeLocalizerError(f"多语言词库 {locale} 的 locale 不一致")
        validate_translation_data(translation)
    return locales


def selected_locale() -> str:
    """Return an explicit user selection, defaulting safely to Simplified Chinese."""

    candidate = os.environ.get("CODEX_PLUGIN_STORE_LOCALE", "").strip()
    if not candidate and LOCALE_SETTINGS_PATH.is_file() and not LOCALE_SETTINGS_PATH.is_symlink():
        try:
            saved = read_json(LOCALE_SETTINGS_PATH)
            candidate = saved.get("locale", "") if isinstance(saved, dict) else ""
        except RuntimeLocalizerError:
            candidate = ""
    return candidate if candidate in SUPPORTED_LOCALES else DEFAULT_LOCALE


def dictionary_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_coverage_data(payload: Any, translations: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeLocalizerError("全量覆盖清单结构无效")
    if payload.get("locale") != "zh-Hans":
        raise RuntimeLocalizerError("全量覆盖清单 locale 必须为 zh-Hans")
    records = payload.get("records")
    counts = payload.get("counts")
    if not isinstance(records, list) or not records or not isinstance(counts, dict):
        raise RuntimeLocalizerError("全量覆盖清单缺少 records/counts")
    ids = [record.get("plugin_id") for record in records if isinstance(record, dict)]
    if len(ids) != len(records) or any(not isinstance(value, str) or not value for value in ids):
        raise RuntimeLocalizerError("全量覆盖清单包含无效项目 id")
    if len(set(ids)) != len(ids):
        raise RuntimeLocalizerError("全量覆盖清单包含重复项目 id")
    if counts.get("public_records") != len(records):
        raise RuntimeLocalizerError("全量覆盖清单项目计数不一致")
    if counts.get("missing_required_pairs") != 0:
        raise RuntimeLocalizerError("全量覆盖清单仍有缺失字段")
    expected_counts = {
        "plugin_descriptions": len(translations["plugin_descriptions"]),
        "plugin_details": len(translations["plugin_details"]),
        "plugin_texts": len(translations["plugin_texts"]),
        "host_strings": len(translations["host_strings"]),
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            raise RuntimeLocalizerError(f"全量覆盖清单 {key} 计数不一致")
    if payload.get("dictionary_sha256") != dictionary_sha256(translations):
        raise RuntimeLocalizerError("全量覆盖清单与词库哈希不一致")
    return payload


def atomic_write_json(path: Path, payload: Mapping[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        if not IS_WINDOWS:
            os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def pid_is_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def find_chatgpt_main_pids() -> List[int]:
    if IS_WINDOWS:
        if not APP_BINARY.is_file():
            return []
        try:
            output = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {APP_BINARY.name}"],
                text=True,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeLocalizerError(f"无法检查 ChatGPT 进程: {exc}") from exc
        pids: List[int] = []
        for line in output.splitlines():
            columns = [column.strip().strip('"') for column in line.split('","')]
            if len(columns) < 2 or columns[0].casefold() != APP_BINARY.name.casefold():
                continue
            try:
                pids.append(int(columns[1].replace(",", "")))
            except ValueError:
                continue
        return pids
    try:
        output = subprocess.check_output(
            ["/bin/ps", "-axo", "pid=,command="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeLocalizerError(f"无法检查 ChatGPT 进程: {exc}") from exc

    exact = str(APP_BINARY)
    pids: List[int] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if command == exact or command.startswith(exact + " "):
            try:
                pids.append(int(pid_text))
            except ValueError:
                continue
    return pids


def verify_chatgpt_signature(require_integrity: bool = True) -> Dict[str, Any]:
    if not APP_BINARY.is_file():
        if IS_WINDOWS:
            raise RuntimeLocalizerError(
                "未找到 Codex/ChatGPT Windows 可执行文件；请设置 "
                "CODEX_PLUGIN_STORE_ZH_APP_PATH 为其绝对 .exe 路径"
            )
        raise RuntimeLocalizerError(f"找不到 ChatGPT 可执行文件: {APP_BINARY}")
    if IS_WINDOWS:
        command = (
            "$signature=Get-AuthenticodeSignature -LiteralPath $args[0];"
            "[pscustomobject]@{status=[string]$signature.Status;subject=[string]$signature.SignerCertificate.Subject;"
            "thumbprint=[string]$signature.SignerCertificate.Thumbprint}|ConvertTo-Json -Compress"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command, str(APP_BINARY)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
            )
            payload = json.loads(completed.stdout) if completed.returncode == 0 else None
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeLocalizerError(f"无法校验 Windows 应用签名: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("status") != "Valid":
            raise RuntimeLocalizerError("Windows 应用签名无效，拒绝启动注入器")
        return {
            "platform": platform.system(),
            "subject": payload.get("subject", ""),
            "thumbprint": payload.get("thumbprint", ""),
            "integrity_verified": True,
            "publisher_pinned": False,
        }
    try:
        result = subprocess.run(
            ["/usr/bin/codesign", "-dv", "--verbose=4", str(APP_BUNDLE)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise RuntimeLocalizerError(f"无法校验 ChatGPT 签名: {exc}") from exc
    output = f"{result.stdout}\n{result.stderr}"
    identifier = ""
    team_identifier = ""
    for line in output.splitlines():
        if line.startswith("Identifier="):
            identifier = line.split("=", 1)[1].strip()
        elif line.startswith("TeamIdentifier="):
            team_identifier = line.split("=", 1)[1].strip()
    if result.returncode != 0:
        raise RuntimeLocalizerError("ChatGPT 代码签名校验失败")
    if identifier != EXPECTED_IDENTIFIER or team_identifier != EXPECTED_TEAM_IDENTIFIER:
        raise RuntimeLocalizerError(
            "ChatGPT 签名身份不匹配: "
            f"Identifier={identifier!r}, TeamIdentifier={team_identifier!r}"
        )
    if require_integrity:
        try:
            verification = subprocess.run(
                ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(APP_BUNDLE)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise RuntimeLocalizerError(f"无法执行 ChatGPT 完整性校验: {exc}") from exc
        if verification.returncode != 0:
            detail = (verification.stderr or verification.stdout).strip()
            raise RuntimeLocalizerError(f"ChatGPT 完整签名校验失败，拒绝注入: {detail}")
    return {
        "identifier": identifier,
        "team_identifier": team_identifier,
        "integrity_verified": require_integrity,
    }


def apply_private_modes(root: Path, executable_names: Iterable[str] = ()) -> None:
    if IS_WINDOWS:
        return
    executable_set = set(executable_names)
    for current_root, directories, files in os.walk(root):
        current = Path(current_root)
        os.chmod(current, 0o700)
        for directory in directories:
            os.chmod(current / directory, 0o700)
        for filename in files:
            mode = 0o700 if filename in executable_set else 0o600
            os.chmod(current / filename, mode)
