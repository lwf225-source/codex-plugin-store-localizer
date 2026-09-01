#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from manage import _validate_source_tree  # noqa: E402


class FullCatalogCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest, cls.translations, cls.coverage, cls.locale_packs = _validate_source_tree()

    def test_all_declared_locale_packs_are_present(self) -> None:
        self.assertEqual(len(self.locale_packs), 14)
        self.assertEqual(set(self.locale_packs), {
            "zh-Hant", "en", "ja", "ko", "es", "fr", "de", "pt-BR", "ru", "ar", "hi", "id", "tr", "vi",
        })
        self.assertTrue(all(len(pack["plugin_descriptions"]) == 6 for pack in self.locale_packs.values()))

    def test_every_public_catalog_record_is_accounted_for(self) -> None:
        records = self.coverage["records"]
        counts = self.coverage["counts"]
        self.assertGreaterEqual(len(records), 3000)
        self.assertEqual(len(records), counts["public_records"])
        self.assertEqual(len({record["plugin_id"] for record in records}), len(records))
        self.assertEqual(counts["missing_required_pairs"], 0)

    def test_disabled_but_visible_records_are_included(self) -> None:
        statuses = self.coverage["selection"]["statuses"]
        self.assertGreater(statuses.get("DISABLED_BY_ADMIN", 0), 0)

    def test_all_catalog_categories_are_covered(self) -> None:
        categories = self.coverage["counts"]["categories"]
        self.assertGreaterEqual(len(categories), 14)
        self.assertIn("Education & Research", categories)
        self.assertIn("Scientific Research", categories)

    def test_card_and_detail_targets_are_chinese(self) -> None:
        cjk = re.compile(r"[\u3400-\u9fff]")
        missing = []
        for item in self.translations["plugin_descriptions"]:
            if not cjk.search(item["target_short"]):
                missing.append((item["display_name"], "card", item["target_short"]))
        for item in self.translations["plugin_details"]:
            if not cjk.search(item["target_long"]):
                missing.append((item["display_name"], "detail", item["target_long"][:100]))
        self.assertEqual(missing, [])

    def test_runtime_is_fail_open_and_never_rewrites_html(self) -> None:
        launcher = (PLUGIN_ROOT / "scripts" / "launcher.py").read_text(encoding="utf-8")
        injector = (PLUGIN_ROOT / "scripts" / "injector.js").read_text(encoding="utf-8")
        runtime = (PLUGIN_ROOT / "scripts" / "runtime_common.py").read_text(encoding="utf-8")
        self.assertIn('status["state"] = "degraded_untranslated"', launcher)
        self.assertNotIn("process.terminate()", launcher)
        self.assertNotIn("innerHTML", injector)
        self.assertIn("node.nodeValue =", injector)
        self.assertIn('"--verify", "--deep", "--strict"', runtime)


if __name__ == "__main__":
    unittest.main()
