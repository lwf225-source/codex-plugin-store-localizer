#!/usr/bin/env python3
"""Launch ChatGPT with a private CDP pipe and inject exact plugin-store translations."""

from __future__ import annotations

import base64
import gzip
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from runtime_common import (
    APP_BINARY,
    IS_WINDOWS,
    RUNTIME_DIR,
    STATUS_PATH,
    selected_locale,
    RuntimeLocalizerError,
    atomic_write_json,
    find_chatgpt_main_pids,
    pid_is_alive,
    read_json,
    utc_now,
    validate_translation_data,
    validate_locale_packs,
    validate_coverage_data,
    verify_chatgpt_signature,
)


BINDING_NAME = "__codexPluginStoreZhReport"


class NulJSONDecoder:
    """Decode the NUL-delimited JSON framing used by remote-debugging-pipe."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> List[Dict[str, Any]]:
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("chunk must be bytes")
        self._buffer.extend(chunk)
        messages: List[Dict[str, Any]] = []
        while True:
            try:
                boundary = self._buffer.index(0)
            except ValueError:
                break
            raw = bytes(self._buffer[:boundary])
            del self._buffer[: boundary + 1]
            if not raw:
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeLocalizerError(f"CDP pipe 返回无效 JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise RuntimeLocalizerError("CDP pipe 消息必须是 JSON 对象")
            messages.append(payload)
        return messages


def encode_cdp_message(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\0"


def spawn_with_debug_pipe(argv: Sequence[str]) -> Tuple[subprocess.Popen, int, int]:
    """Spawn a process with Chromium's private cross-platform CDP pipes."""

    if not argv:
        raise ValueError("argv must not be empty")
    if IS_WINDOWS:
        return _spawn_windows_debug_pipe(argv)
    to_child_read, to_child_write = os.pipe()
    from_child_read, from_child_write = os.pipe()
    # Duplicate the child-facing ends above FD4 so dup2 remains correct even if
    # the original pipe descriptors happen to occupy FD3 or FD4 in a different
    # order.
    child_read_source = os.dup(to_child_read)
    child_write_source = os.dup(from_child_write)
    for descriptor in (child_read_source, child_write_source):
        os.set_inheritable(descriptor, True)

    child_descriptors = {
        to_child_read,
        to_child_write,
        from_child_read,
        from_child_write,
        child_read_source,
        child_write_source,
    }

    def configure_child() -> None:
        os.dup2(child_read_source, 3)
        os.dup2(child_write_source, 4)
        for descriptor in child_descriptors:
            if descriptor not in (3, 4):
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            # Keep the destination descriptors through CPython's post-preexec
            # close sweep; configure_child has already replaced them with the
            # two private pipe ends by then.
            pass_fds=(3, 4, child_read_source, child_write_source),
            preexec_fn=configure_child,
        )
    except Exception:
        for descriptor in child_descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise

    os.close(to_child_read)
    os.close(from_child_write)
    os.close(child_read_source)
    os.close(child_write_source)
    return process, to_child_write, from_child_read


def _spawn_windows_debug_pipe(argv: Sequence[str]) -> Tuple[subprocess.Popen, int, int]:
    """Use inherited Win32 handles required by remote-debugging-io-pipes.

    Chromium's Windows driver passes the child read/write HANDLE values through
    --remote-debugging-io-pipes while retaining them via CreateProcess handle
    inheritance. Python exposes the same primitive through a STARTUPINFO handle
    list; the parent uses ordinary CRT descriptors for its two pipe ends.
    """
    if os.name != "nt":
        raise RuntimeLocalizerError("Windows CDP pipe 只能在 Windows 上启动")
    import msvcrt

    to_child_read, to_child_write = os.pipe()
    from_child_read, from_child_write = os.pipe()
    child_descriptors = (to_child_read, from_child_write)
    for descriptor in child_descriptors:
        os.set_inheritable(descriptor, True)
    child_read_handle = msvcrt.get_osfhandle(to_child_read)
    child_write_handle = msvcrt.get_osfhandle(from_child_write)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.lpAttributeList = {"handle_list": [child_read_handle, child_write_handle]}
    command = windows_debug_arguments(argv, child_read_handle, child_write_handle)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            startupinfo=startupinfo,
        )
    except Exception:
        for descriptor in (to_child_read, to_child_write, from_child_read, from_child_write):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    os.close(to_child_read)
    os.close(from_child_write)
    return process, to_child_write, from_child_read


def windows_debug_arguments(
    argv: Sequence[str], child_read_handle: int, child_write_handle: int
) -> List[str]:
    if child_read_handle < 0 or child_write_handle < 0:
        raise ValueError("Windows CDP handles must be non-negative")
    return list(argv) + [
        "--remote-debugging-pipe",
        f"--remote-debugging-io-pipes={child_read_handle},{child_write_handle}",
    ]


class CDPPipe:
    def __init__(self, write_fd: int, read_fd: int) -> None:
        self._write_fd = write_fd
        self._read_fd = read_fd
        self._decoder = NulJSONDecoder()
        self._events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._pending: Dict[int, "queue.Queue[Dict[str, Any]]"] = {}
        self._lock = threading.Lock()
        self._next_id = 1
        self._closed = False
        self._reader = threading.Thread(target=self._read_loop, name="codex-store-zh-cdp", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            while True:
                chunk = os.read(self._read_fd, 65536)
                if not chunk:
                    break
                for message in self._decoder.feed(chunk):
                    message_id = message.get("id")
                    target_queue = None
                    if isinstance(message_id, int):
                        with self._lock:
                            target_queue = self._pending.pop(message_id, None)
                    if target_queue is not None:
                        target_queue.put(message)
                    else:
                        self._events.put(message)
        except Exception as exc:
            self._events.put({"method": "__pipe_error__", "params": {"error": str(exc)}})
        finally:
            self._closed = True
            self._events.put({"method": "__pipe_closed__", "params": {}})

    def request(
        self,
        method: str,
        params: Optional[Mapping[str, Any]] = None,
        session_id: Optional[str] = None,
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        if self._closed:
            raise RuntimeLocalizerError("CDP pipe 已关闭")
        response_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1)
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            self._pending[request_id] = response_queue
        message: Dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = dict(params)
        if session_id is not None:
            message["sessionId"] = session_id
        payload = encode_cdp_message(message)
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(self._write_fd, payload[offset:])
                if written <= 0:
                    raise RuntimeLocalizerError("无法写入 CDP pipe")
                offset += written
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise RuntimeLocalizerError(f"CDP 请求超时: {method}") from exc
        if "error" in response:
            error = response.get("error")
            raise RuntimeLocalizerError(f"CDP 请求失败 {method}: {error}")
        result = response.get("result", {})
        return result if isinstance(result, dict) else {}

    def next_event(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        for descriptor in (self._write_fd, self._read_fd):
            try:
                os.close(descriptor)
            except OSError:
                pass
        self._closed = True


def build_injection_expression(data: Mapping[str, Any], injector_source: str) -> str:
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(compact, compresslevel=9, mtime=0)
    encoded = base64.b64encode(compressed).decode("ascii")
    data_loader = (
        "const compressed=Uint8Array.from(atob('"
        + encoded
        + "'),c=>c.charCodeAt(0));"
        "const stream=new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));"
        "globalThis.__CODEX_PLUGIN_STORE_ZH_DATA__=JSON.parse(await new Response(stream).text());\n"
    )
    return "(async()=>{\n" + data_loader + injector_source + "\n})()\n//# sourceURL=codex-plugin-store-zh-injector.js\n"


class InjectorController:
    def __init__(
        self,
        cdp: CDPPipe,
        expression: str,
        status: Dict[str, Any],
    ) -> None:
        self.cdp = cdp
        self.expression = expression
        self.status = status
        self.attaching: Set[str] = set()
        self.target_sessions: Dict[str, str] = {}
        self.session_counts: Dict[str, Dict[str, int]] = {}

    @staticmethod
    def _allowed_target(info: Any) -> bool:
        return (
            isinstance(info, dict)
            and info.get("type") == "page"
            and isinstance(info.get("url"), str)
            and info["url"].startswith("app://")
        )

    def start(self) -> None:
        self.cdp.request("Target.setDiscoverTargets", {"discover": True})
        result = self.cdp.request("Target.getTargets")
        target_infos = result.get("targetInfos", [])
        if isinstance(target_infos, list):
            for info in target_infos:
                if self._allowed_target(info):
                    self._attach(info["targetId"])

    def _attach(self, target_id: str) -> None:
        if target_id in self.attaching or target_id in self.target_sessions:
            return
        self.attaching.add(target_id)
        try:
            result = self.cdp.request(
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
            )
            session_id = result.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                raise RuntimeLocalizerError("Target.attachToTarget 未返回 sessionId")
            self.target_sessions[target_id] = session_id
            self.cdp.request("Page.enable", session_id=session_id)
            self.cdp.request("Runtime.enable", session_id=session_id)
            self.cdp.request(
                "Runtime.addBinding",
                {"name": BINDING_NAME},
                session_id=session_id,
            )
            self.cdp.request(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": self.expression},
                session_id=session_id,
            )
            evaluation = self.cdp.request(
                "Runtime.evaluate",
                {
                    "expression": self.expression,
                    "awaitPromise": True,
                    "returnByValue": True,
                },
                session_id=session_id,
            )
            if evaluation.get("exceptionDetails"):
                raise RuntimeLocalizerError("当前 app:// 文档注入脚本执行失败")
            self.status["state"] = "active"
            self.status["attached_targets"] = len(self.target_sessions)
            self.status["last_error"] = None
            self._write_status()
        finally:
            self.attaching.discard(target_id)

    def _write_status(self) -> None:
        self.status["updated_at"] = utc_now()
        atomic_write_json(STATUS_PATH, self.status)

    def _handle_report(self, message: Mapping[str, Any]) -> None:
        params = message.get("params")
        session_id = message.get("sessionId")
        if not isinstance(params, dict) or not isinstance(session_id, str):
            return
        if params.get("name") != BINDING_NAME:
            return
        payload_text = params.get("payload")
        if not isinstance(payload_text, str) or len(payload_text) > 1000:
            return
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict) or payload.get("version") != 3:
            return
        translated = payload.get("translated_nodes")
        unmatched = payload.get("unmatched_sources")
        unmatched_details = payload.get("unmatched_detail_sources")
        unmatched_plugin_texts = payload.get("unmatched_plugin_text_sources")
        scanned_text_nodes = payload.get("scanned_text_nodes", 0)
        scan_batches = payload.get("scan_batches", 0)
        if not isinstance(translated, int) or translated < 0:
            return
        if not isinstance(unmatched, int) or unmatched < 0:
            return
        if not isinstance(unmatched_details, int) or unmatched_details < 0:
            return
        if not isinstance(unmatched_plugin_texts, int) or unmatched_plugin_texts < 0:
            return
        if not isinstance(scanned_text_nodes, int) or scanned_text_nodes < 0:
            return
        if not isinstance(scan_batches, int) or scan_batches < 0:
            return
        self.session_counts[session_id] = {
            "translated_nodes": translated,
            "unmatched_sources": unmatched,
            "unmatched_detail_sources": unmatched_details,
            "unmatched_plugin_text_sources": unmatched_plugin_texts,
            "scanned_text_nodes": scanned_text_nodes,
            "scan_batches": scan_batches,
        }
        self.status["translated_nodes"] = sum(
            entry["translated_nodes"] for entry in self.session_counts.values()
        )
        self.status["unmatched_sources"] = sum(
            entry["unmatched_sources"] for entry in self.session_counts.values()
        )
        self.status["unmatched_detail_sources"] = sum(
            entry["unmatched_detail_sources"] for entry in self.session_counts.values()
        )
        self.status["unmatched_plugin_text_sources"] = sum(
            entry["unmatched_plugin_text_sources"] for entry in self.session_counts.values()
        )
        self.status["scanned_text_nodes"] = sum(
            entry["scanned_text_nodes"] for entry in self.session_counts.values()
        )
        self.status["scan_batches"] = sum(
            entry["scan_batches"] for entry in self.session_counts.values()
        )
        self.status["last_report_at"] = utc_now()
        self._write_status()

    def handle_event(self, message: Mapping[str, Any]) -> bool:
        method = message.get("method")
        if method == "Target.targetCreated" or method == "Target.targetInfoChanged":
            params = message.get("params")
            info = params.get("targetInfo") if isinstance(params, dict) else None
            if self._allowed_target(info):
                self._attach(info["targetId"])
        elif method == "Target.targetDestroyed":
            params = message.get("params")
            target_id = params.get("targetId") if isinstance(params, dict) else None
            if isinstance(target_id, str):
                session_id = self.target_sessions.pop(target_id, None)
                if session_id:
                    self.session_counts.pop(session_id, None)
                self.status["attached_targets"] = len(self.target_sessions)
                self._write_status()
        elif method == "Target.detachedFromTarget":
            params = message.get("params")
            session_id = params.get("sessionId") if isinstance(params, dict) else None
            if isinstance(session_id, str):
                for target_id, known_session in list(self.target_sessions.items()):
                    if known_session == session_id:
                        del self.target_sessions[target_id]
                self.session_counts.pop(session_id, None)
                self.status["attached_targets"] = len(self.target_sessions)
                self._write_status()
        elif method == "Runtime.bindingCalled":
            self._handle_report(message)
        elif method == "__pipe_error__":
            params = message.get("params")
            error = params.get("error") if isinstance(params, dict) else "unknown"
            raise RuntimeLocalizerError(f"CDP pipe 读取失败: {error}")
        elif method == "__pipe_closed__":
            return False
        return True


def load_runtime_inputs() -> Tuple[Dict[str, Any], str, Dict[str, Any], str]:
    installation_path = RUNTIME_DIR / "installation.json"
    locale = selected_locale()
    translation_path = RUNTIME_DIR / "assets" / "dom-translations.zh-Hans.json"
    locale_packs_path = RUNTIME_DIR / "assets" / "locale-packs.json"
    coverage_path = RUNTIME_DIR / "assets" / "catalog-coverage.zh-Hans.json"
    injector_path = RUNTIME_DIR / "scripts" / "injector.js"
    installation = read_json(installation_path)
    if not isinstance(installation, dict) or installation.get("schema_version") != 1:
        raise RuntimeLocalizerError("运行时 installation.json 无效，请重新安装")
    chinese_translations = validate_translation_data(read_json(translation_path))
    validate_coverage_data(read_json(coverage_path), chinese_translations)
    translations = (
        chinese_translations
        if locale == "zh-Hans"
        else validate_locale_packs(read_json(locale_packs_path))[locale]
    )
    try:
        injector_source = injector_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeLocalizerError(f"无法读取固定注入器: {exc}") from exc
    if "eval(" in injector_source or "new Function" in injector_source:
        raise RuntimeLocalizerError("固定注入器包含禁止的动态代码执行")
    return translations, injector_source, installation, locale


def run() -> int:
    translations, injector_source, installation, locale = load_runtime_inputs()
    signature = verify_chatgpt_signature()
    existing_pids = find_chatgpt_main_pids()
    if existing_pids:
        raise RuntimeLocalizerError(
            "ChatGPT 已在运行；请完全退出后从“ChatGPT 插件商店汉化版”重新打开"
        )

    status: Dict[str, Any] = {
        "schema_version": 1,
        "state": "starting",
        "plugin_version": installation.get("plugin_version"),
        "locale": locale,
        "launcher_pid": os.getpid(),
        "app_pid": None,
        "signature": signature,
        "attached_targets": 0,
        "translated_nodes": 0,
        "unmatched_sources": 0,
        "unmatched_detail_sources": 0,
        "unmatched_plugin_text_sources": 0,
        "scanned_text_nodes": 0,
        "scan_batches": 0,
        "last_report_at": None,
        "last_error": None,
        "started_at": utc_now(),
        "updated_at": utc_now(),
    }
    atomic_write_json(STATUS_PATH, status)

    process: Optional[subprocess.Popen] = None
    cdp: Optional[CDPPipe] = None
    try:
        process, write_fd, read_fd = spawn_with_debug_pipe(
            [str(APP_BINARY), "--remote-debugging-pipe"]
        )
        status["app_pid"] = process.pid
        status["state"] = "waiting_for_app_page"
        status["updated_at"] = utc_now()
        atomic_write_json(STATUS_PATH, status)
        cdp = CDPPipe(write_fd, read_fd)
        expression = build_injection_expression(translations, injector_source)
        controller = InjectorController(cdp, expression, status)
        controller.start()

        while process.poll() is None:
            event = cdp.next_event(timeout=1.0)
            if event is not None and not controller.handle_event(event):
                raise RuntimeLocalizerError("CDP pipe 在 ChatGPT 仍运行时意外关闭")

        status["state"] = "stopped"
        status["updated_at"] = utc_now()
        atomic_write_json(STATUS_PATH, status)
        return int(process.returncode or 0)
    except Exception as exc:
        if process is None or process.poll() is not None:
            raise
        # Once the official app has started, localization failure must not take
        # Codex down with it. Keep the private pipe open and leave the app fully
        # usable in English until the user exits it normally.
        status["state"] = "degraded_untranslated"
        status["last_error"] = str(exc)
        status["updated_at"] = utc_now()
        atomic_write_json(STATUS_PATH, status)
        while process.poll() is None:
            time.sleep(1.0)
        return int(process.returncode or 0)
    finally:
        if cdp is not None:
            cdp.close()


def main() -> int:
    try:
        return run()
    except Exception as exc:
        payload: Dict[str, Any] = {
            "schema_version": 1,
            "state": "error",
            "launcher_pid": os.getpid(),
            "launcher_running": pid_is_alive(os.getpid()),
            "unmatched_detail_sources": 0,
            "unmatched_plugin_text_sources": 0,
            "last_error": str(exc),
            "updated_at": utc_now(),
        }
        try:
            atomic_write_json(STATUS_PATH, payload)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
