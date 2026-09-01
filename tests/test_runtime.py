#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from launcher import (  # noqa: E402
    NulJSONDecoder,
    build_injection_expression,
    encode_cdp_message,
    spawn_with_debug_pipe,
    windows_debug_arguments,
)
import manage  # noqa: E402
import runtime_common  # noqa: E402
from runtime_common import (  # noqa: E402
    RuntimeLocalizerError,
    SUPPORTED_LOCALES,
    validate_locale_packs,
    validate_translation_data,
)


class NulJSONDecoderTests(unittest.TestCase):
    def test_split_and_multiple_frames(self) -> None:
        decoder = NulJSONDecoder()
        self.assertEqual(decoder.feed(b'{"id":1'), [])
        messages = decoder.feed(b'}\0{"method":"ready"}\0')
        self.assertEqual(messages, [{"id": 1}, {"method": "ready"}])

    def test_rejects_non_object_message(self) -> None:
        decoder = NulJSONDecoder()
        with self.assertRaises(RuntimeLocalizerError):
            decoder.feed(b"[]\0")


class DebugPipeSpawnTests(unittest.TestCase):
    def test_child_reads_fd3_and_writes_fd4(self) -> None:
        child_code = (
            "import json,os;"
            "raw=b'';"
            "\nwhile b'\\0' not in raw: raw+=os.read(3,4096)"
            "\nmsg=json.loads(raw.split(b'\\0',1)[0]);"
            "os.write(4,(json.dumps({'echo':msg['ping']})+'\\0').encode())"
        )
        process, write_fd, read_fd = spawn_with_debug_pipe([sys.executable, "-c", child_code])
        try:
            os.write(write_fd, encode_cdp_message({"ping": "pong"}))
            decoder = NulJSONDecoder()
            response = []
            while not response:
                chunk = os.read(read_fd, 4096)
                self.assertTrue(chunk)
                response.extend(decoder.feed(chunk))
            self.assertEqual(response, [{"echo": "pong"}])
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            for descriptor in (write_fd, read_fd):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    @unittest.skipIf(fcntl is None, "POSIX descriptor inheritance test")
    def test_child_does_not_inherit_unrelated_inheritable_fd(self) -> None:
        with tempfile.TemporaryFile() as handle:
            leaked_fd = fcntl.fcntl(handle.fileno(), fcntl.F_DUPFD, 50)
            os.set_inheritable(leaked_fd, True)
            child_code = (
                "import json,os;"
                f"\ntry: os.fstat({leaked_fd}); leaked=True"
                "\nexcept OSError: leaked=False"
                "\nraw=b''"
                "\nwhile b'\\0' not in raw: raw+=os.read(3,4096)"
                "\nos.write(4,(json.dumps({'leaked':leaked})+'\\0').encode())"
            )
            process, write_fd, read_fd = spawn_with_debug_pipe([sys.executable, "-c", child_code])
            try:
                os.write(write_fd, encode_cdp_message({"ping": "pong"}))
                decoder = NulJSONDecoder()
                response = []
                while not response:
                    response.extend(decoder.feed(os.read(read_fd, 4096)))
                self.assertEqual(response, [{"leaked": False}])
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                os.close(leaked_fd)
                for descriptor in (write_fd, read_fd):
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    def test_windows_uses_private_inherited_handle_switches(self) -> None:
        command = windows_debug_arguments(["Codex.exe"], 101, 202)
        self.assertEqual(
            command,
            [
                "Codex.exe",
                "--remote-debugging-pipe",
                "--remote-debugging-io-pipes=101,202",
            ],
        )
        with self.assertRaises(ValueError):
            windows_debug_arguments(["Codex.exe"], -1, 202)


class WindowsLauncherMetadataTests(unittest.TestCase):
    def test_windows_candidate_honors_explicit_executable(self) -> None:
        previous = os.environ.get("CODEX_PLUGIN_STORE_ZH_APP_PATH")
        os.environ["CODEX_PLUGIN_STORE_ZH_APP_PATH"] = r"C:\\Codex\\Codex.exe"
        try:
            self.assertEqual(runtime_common._windows_app_candidates()[0], Path(r"C:\\Codex\\Codex.exe"))
        finally:
            if previous is None:
                del os.environ["CODEX_PLUGIN_STORE_ZH_APP_PATH"]
            else:
                os.environ["CODEX_PLUGIN_STORE_ZH_APP_PATH"] = previous

    def test_windows_wrapper_uses_only_local_runtime_and_python(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "launcher.cmd"
            original_flag = manage.IS_WINDOWS
            try:
                manage.IS_WINDOWS = True
                manage._write_wrapper_app(destination)
            finally:
                manage.IS_WINDOWS = original_flag
            content = destination.read_text(encoding="utf-8")
            self.assertIn("CODEX_PLUGIN_STORE_ZH_RUNTIME", content)
            self.assertIn("py -3", content)
            self.assertNotIn("http://", content)
            self.assertNotIn("https://", content)


class TranslationDataTests(unittest.TestCase):
    def valid_payload(self):
        return {
            "schema_version": 3,
            "locale": "zh-Hans",
            "plugin_descriptions": [
                {
                    "display_name": "Gmail",
                    "source_short": ["Read and manage Gmail"],
                    "target_short": "读取和管理 Gmail",
                }
            ],
            "plugin_details": [
                {
                    "display_name": "Gmail",
                    "source_long": ["Use Gmail to summarize inbox activity."],
                    "target_long": "使用 Gmail 汇总收件箱动态。",
                }
            ],
            "plugin_texts": [
                {
                    "display_name": "Gmail",
                    "kind": "prompt",
                    "source": "Help me get started",
                    "target": "帮助我开始使用",
                }
            ],
            "host_strings": [{"source": "Popular", "target": "热门"}],
        }

    def test_validates_fixed_schema(self) -> None:
        payload = self.valid_payload()
        self.assertIs(validate_translation_data(payload), payload)

    def test_accepts_each_bundled_supported_locale(self) -> None:
        for language in SUPPORTED_LOCALES:
            payload = self.valid_payload()
            payload["locale"] = language
            self.assertIs(validate_translation_data(payload), payload)

    def test_validates_all_non_chinese_locale_packs(self) -> None:
        packs = {}
        for language in SUPPORTED_LOCALES:
            if language == "zh-Hans":
                continue
            payload = self.valid_payload()
            payload["locale"] = language
            packs[language] = payload
        self.assertEqual(validate_locale_packs({"schema_version": 1, "locales": packs}), packs)

    def test_rejects_missing_locale_pack(self) -> None:
        packs = {}
        for language in SUPPORTED_LOCALES:
            if language == "zh-Hans":
                continue
            payload = self.valid_payload()
            payload["locale"] = language
            packs[language] = payload
        packs.pop("vi")
        with self.assertRaises(RuntimeLocalizerError):
            validate_locale_packs({"schema_version": 1, "locales": packs})

    def test_rejects_extra_javascript_field(self) -> None:
        payload = self.valid_payload()
        payload["plugin_descriptions"][0]["javascript"] = "alert(1)"
        with self.assertRaises(RuntimeLocalizerError):
            validate_translation_data(payload)

    def test_rejects_extra_top_level_field(self) -> None:
        payload = self.valid_payload()
        payload["javascript"] = "alert(1)"
        with self.assertRaises(RuntimeLocalizerError):
            validate_translation_data(payload)

    def test_rejects_detail_for_unknown_plugin(self) -> None:
        payload = self.valid_payload()
        payload["plugin_details"][0]["display_name"] = "Unknown"
        with self.assertRaises(RuntimeLocalizerError):
            validate_translation_data(payload)

    def test_rejects_plugin_text_for_unknown_plugin(self) -> None:
        payload = self.valid_payload()
        payload["plugin_texts"][0]["display_name"] = "Unknown"
        with self.assertRaises(RuntimeLocalizerError):
            validate_translation_data(payload)

    def test_rejects_unknown_plugin_text_kind(self) -> None:
        payload = self.valid_payload()
        payload["plugin_texts"][0]["kind"] = "javascript"
        with self.assertRaises(RuntimeLocalizerError):
            validate_translation_data(payload)

    def test_expression_encodes_data_instead_of_interpolating_source(self) -> None:
        payload = self.valid_payload()
        payload["plugin_descriptions"][0]["source_short"] = ["');globalThis.pwned=true;//"]
        validate_translation_data(payload)
        expression = build_injection_expression(payload, "globalThis.injectorLoaded=true;")
        self.assertNotIn("globalThis.pwned=true", expression)
        self.assertIn("globalThis.injectorLoaded=true", expression)
        self.assertIn("DecompressionStream('gzip')", expression)

    def test_expression_compresses_large_dictionary(self) -> None:
        payload = self.valid_payload()
        payload["plugin_details"][0]["source_long"] = ["Repeated catalog text. " * 5000]
        payload["plugin_details"][0]["target_long"] = "重复的目录文字。" * 5000
        validate_translation_data(payload)
        raw_size = len(json.dumps(payload, ensure_ascii=False))
        expression = build_injection_expression(payload, "globalThis.injectorLoaded=true;")
        self.assertLess(len(expression), raw_size // 5)


if __name__ == "__main__":
    unittest.main()
