#!/usr/bin/env python3
"""Read the cached remote plugin catalog and report local translation coverage.

This tool is intentionally read-only: it neither fetches the catalog nor writes
to it. The denominator is every public (LISTED) record, including visible
entries disabled by an administrator.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Set, Tuple

from runtime_common import RuntimeLocalizerError, read_json, validate_translation_data


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_PATH = PLUGIN_ROOT / "assets" / "dom-translations.zh-Hans.json"
CATALOG_DIR = Path.home() / ".codex" / "cache" / "remote_plugin_catalog"


def _catalog_path(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            raise RuntimeLocalizerError("--catalog 必须是绝对路径")
        candidates = [path]
    else:
        candidates = sorted(CATALOG_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in candidates:
        if not path.is_file() or path.is_symlink():
            continue
        try:
            payload = read_json(path)
        except RuntimeLocalizerError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("plugins"), list) and payload["plugins"]:
            return path
    raise RuntimeLocalizerError("未找到可读取的远端插件目录缓存")


def _catalog_entries(catalog: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    plugins = catalog.get("plugins")
    if not isinstance(plugins, list):
        raise RuntimeLocalizerError("远端插件目录 plugins 必须是数组")
    for item in plugins:
        if not isinstance(item, dict):
            continue
        release = item.get("release")
        interface = release.get("interface") if isinstance(release, dict) else None
        if not isinstance(release, dict) or not isinstance(interface, dict):
            continue
        name = release.get("display_name")
        short = interface.get("short_description")
        long = interface.get("long_description")
        if not isinstance(name, str) or not name.strip():
            continue
        yield {
            "name": name,
            "short": short if isinstance(short, str) and short.strip() else None,
            "long": long if isinstance(long, str) and long.strip() else None,
            "listed": item.get("discoverability") == "LISTED",
            "available": item.get("status") == "AVAILABLE",
        }


def _source_pairs(items: Sequence[Mapping[str, Any]], source_key: str) -> Set[Tuple[str, str]]:
    pairs: Set[Tuple[str, str]] = set()
    for item in items:
        name = item.get("display_name")
        sources = item.get(source_key)
        if not isinstance(name, str) or not isinstance(sources, list):
            continue
        for source in sources:
            if isinstance(source, str):
                pairs.add((name, source))
    return pairs


def build_report(catalog_path: Path, limit: int) -> Dict[str, Any]:
    translations = validate_translation_data(read_json(TRANSLATIONS_PATH))
    catalog = read_json(catalog_path)
    if not isinstance(catalog, dict):
        raise RuntimeLocalizerError("远端插件目录必须是 JSON 对象")
    entries = list(_catalog_entries(catalog))
    listed = [entry for entry in entries if entry["listed"]]
    listed_available = [entry for entry in listed if entry["available"]]
    catalog_short = {(entry["name"], entry["short"]) for entry in entries if entry["short"]}
    catalog_long = {(entry["name"], entry["long"]) for entry in entries if entry["long"]}
    listed_short = {(entry["name"], entry["short"]) for entry in listed if entry["short"]}
    listed_long = {(entry["name"], entry["long"]) for entry in listed if entry["long"]}
    local_short = _source_pairs(translations["plugin_descriptions"], "source_short")
    local_long = _source_pairs(translations["plugin_details"], "source_long")
    missing_short = sorted(name for name, source in listed_short if (name, source) not in local_short)
    missing_long = sorted(name for name, source in listed_long if (name, source) not in local_long)
    return {
        "schema_version": 1,
        "mode": "read_only",
        "catalog_path": str(catalog_path),
        "catalog_fetched_at": catalog.get("fetched_at"),
        "catalog_records": len(entries),
        "listed_records": len(listed),
        "listed_available_records": len(listed_available),
        "listed_disabled_records": len(listed) - len(listed_available),
        "short_descriptions": {
            "local_pairs": len(local_short),
            "matching_catalog_pairs": len(local_short & catalog_short),
            "matching_listed_pairs": len(local_short & listed_short),
            "untranslated_listed_pairs": len(listed_short - local_short),
            "sample_untranslated_plugins": missing_short[:limit],
        },
        "long_descriptions": {
            "local_pairs": len(local_long),
            "matching_catalog_pairs": len(local_long & catalog_long),
            "matching_listed_pairs": len(local_long & listed_long),
            "untranslated_listed_pairs": len(listed_long - local_long),
            "sample_untranslated_plugins": missing_long[:limit],
        },
        "host_strings": len(translations["host_strings"]),
        "plugin_text_entries": len(translations["plugin_texts"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", help="absolute path to an existing local catalog cache")
    parser.add_argument("--limit", type=int, default=20, help="number of untranslated names to show (1-200)")
    args = parser.parse_args()
    if not 1 <= args.limit <= 200:
        parser.error("--limit 必须介于 1 和 200")
    try:
        report = build_report(_catalog_path(args.catalog), args.limit)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except RuntimeLocalizerError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
