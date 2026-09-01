#!/usr/bin/env python3
"""Generate complete zh-Hans storefront translations from the local catalog.

Every public (LISTED) catalog record is included, including entries that are
visible but disabled by an administrator. Only public catalog strings missing
from the local machine-translation cache are sent to the translation endpoint.
The resulting catalog is queried locally by the native plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from runtime_common import RuntimeLocalizerError, read_json, validate_translation_data


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_PATH = PLUGIN_ROOT / "assets" / "dom-translations.zh-Hans.json"
CACHE_PATH = PLUGIN_ROOT / "assets" / "catalog-machine-cache.zh-Hans.json"
COVERAGE_PATH = PLUGIN_ROOT / "assets" / "catalog-coverage.zh-Hans.json"
CATALOG_DIR = Path.home() / ".codex" / "cache" / "remote_plugin_catalog"
ENDPOINT = "https://clients5.google.com/translate_a/t"
CJK_RE = re.compile(r"[\u3400-\u9fff]")

HOST_TRANSLATIONS = {
    "Popular": "热门",
    "New & Noteworthy": "新品与精选",
    "Productivity": "效率",
    "Creative": "创意",
    "Creativity": "创意",
    "Communication": "沟通",
    "Developer Tools": "开发工具",
    "Data & Analytics": "数据与分析",
    "Business & Operations": "业务与运营",
    "Finance": "金融",
    "Travel": "旅行",
    "Education & Research": "教育与研究",
    "Scientific Research": "科学研究",
    "Entertainment": "娱乐",
    "Healthcare": "医疗健康",
    "Security": "安全",
    "Other": "其他",
    "Interactive": "交互式",
    "Read": "读取",
    "Write": "写入",
}


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _catalog_path(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_absolute():
            raise RuntimeLocalizerError("--catalog 必须是绝对路径")
        candidates = [candidate]
    else:
        candidates = sorted(CATALOG_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if not candidate.is_file() or candidate.is_symlink():
            continue
        payload = read_json(candidate)
        if isinstance(payload, dict) and isinstance(payload.get("plugins"), list) and payload["plugins"]:
            return candidate
    raise RuntimeLocalizerError("未找到可读取的远端插件目录缓存")


def _listed_records(catalog: Mapping[str, Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen_ids = set()
    for position, item in enumerate(catalog.get("plugins", [])):
        if not isinstance(item, dict) or item.get("discoverability") != "LISTED":
            continue
        release = item.get("release")
        interface = release.get("interface") if isinstance(release, dict) else None
        plugin_id = item.get("id")
        name = release.get("display_name") if isinstance(release, dict) else None
        if not isinstance(plugin_id, str) or not plugin_id:
            raise RuntimeLocalizerError(f"第 {position + 1} 个公开项目缺少稳定 id")
        if plugin_id in seen_ids:
            raise RuntimeLocalizerError(f"目录存在重复项目 id: {plugin_id}")
        if not isinstance(interface, dict) or not isinstance(name, str) or not name.strip():
            raise RuntimeLocalizerError(f"公开项目 {plugin_id} 缺少 release/interface/display_name")
        short = interface.get("short_description")
        long = interface.get("long_description")
        if not isinstance(short, str) or not short.strip():
            raise RuntimeLocalizerError(f"公开项目 {plugin_id} 缺少 short_description")
        if not isinstance(long, str) or not long.strip():
            raise RuntimeLocalizerError(f"公开项目 {plugin_id} 缺少 long_description")
        seen_ids.add(plugin_id)
        result.append({
            "plugin_id": plugin_id,
            "display_name": name.strip(),
            "status": item.get("status"),
            "category": interface.get("category") or "Other",
            "release": release,
        })
    if not result:
        raise RuntimeLocalizerError("目录没有公开项目")
    return sorted(result, key=lambda record: record["plugin_id"])


def _unique_strings(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _prompts(interface: Mapping[str, Any]) -> List[str]:
    result: List[str] = []
    value = interface.get("default_prompt")
    if isinstance(value, str) and value.strip():
        result.append(value.strip())
    values = interface.get("default_prompts")
    if isinstance(values, list):
        result.extend(value.strip() for value in values if isinstance(value, str) and value.strip())
    return _unique_strings(result)


def _record_fields(record: Mapping[str, Any]) -> List[Tuple[str, str]]:
    release = record["release"]
    interface = release["interface"]
    name = record["display_name"]
    result = [
        ("card_short", interface["short_description"].strip()),
        ("detail_long", interface["long_description"].strip()),
    ]
    result.extend(("prompt", prompt) for prompt in _prompts(interface))
    for skill in release.get("skills") or []:
        skill_interface = skill.get("interface") if isinstance(skill, dict) else None
        if not isinstance(skill_interface, dict):
            continue
        skill_name = skill_interface.get("display_name")
        skill_short = skill_interface.get("short_description")
        if isinstance(skill_name, str) and skill_name.strip() and skill_name.strip() != name:
            result.append(("skill_name", skill_name.strip()))
        if isinstance(skill_short, str) and skill_short.strip():
            result.append(("skill_description", skill_short.strip()))
        result.extend(("prompt", prompt) for prompt in _prompts(skill_interface))
    return result


def _load_machine_cache() -> Dict[str, str]:
    if not CACHE_PATH.exists():
        return {}
    payload = read_json(CACHE_PATH)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeLocalizerError("机器翻译缓存结构无效")
    translations = payload.get("translations")
    if not isinstance(translations, dict):
        raise RuntimeLocalizerError("机器翻译缓存 translations 必须是对象")
    return {
        source: target.strip()
        for source, target in translations.items()
        if isinstance(source, str) and source and isinstance(target, str) and target.strip()
    }


def _decode_response(raw: bytes, expected_count: int) -> List[str]:
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, list) or len(payload) != expected_count:
        raise RuntimeLocalizerError("翻译服务返回结构异常")
    result = []
    for item in payload:
        value = item if isinstance(item, str) else item[0] if isinstance(item, list) and item else None
        if isinstance(value, str):
            result.append(value.strip())
    if len(result) != expected_count or any(not item for item in result):
        raise RuntimeLocalizerError("翻译服务返回空文本")
    return result


def _request_translations(texts: Sequence[str], source_language: str = "en") -> List[str]:
    command = [
        "/usr/bin/curl", "-sS", "-f", "--get", ENDPOINT,
        "--data-urlencode", "client=dict-chrome-ex",
        "--data-urlencode", f"sl={source_language}",
        "--data-urlencode", "tl=zh-CN",
    ]
    for source in texts:
        command.extend(("--data-urlencode", f"q={source}"))
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
            if completed.returncode != 0:
                raise RuntimeLocalizerError(completed.stderr.decode("utf-8", "replace").strip())
            return _decode_response(completed.stdout, len(texts))
        except (OSError, subprocess.SubprocessError, RuntimeLocalizerError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeLocalizerError(f"翻译请求失败: {last_error}")


def _batches(pending: Sequence[str], max_chars: int) -> List[List[str]]:
    result: List[List[str]] = []
    current: List[str] = []
    current_chars = 0
    for source in pending:
        cost = len(source) + 16
        if current and current_chars + cost > max_chars:
            result.append(current)
            current = []
            current_chars = 0
        current.append(source)
        current_chars += cost
    if current:
        result.append(current)
    return result


def _fill_machine_cache(
    sources: Iterable[str],
    cache: Dict[str, str],
    catalog_path: Path,
    max_chars: int,
    delay: float,
    offline: bool,
) -> None:
    pending = sorted({source for source in sources if source and source not in cache})
    if not pending:
        print(f"translation_cache_complete={len(cache)}", flush=True)
        return
    if offline:
        raise RuntimeLocalizerError(f"离线模式仍缺少 {len(pending)} 条翻译")
    batches = _batches(pending, max_chars)
    for number, batch in enumerate(batches, start=1):
        targets = _request_translations(batch)
        cache.update(zip(batch, targets))
        _atomic_write(CACHE_PATH, {
            "schema_version": 1,
            "locale": "zh-Hans",
            "source_catalog": str(catalog_path),
            "translations": dict(sorted(cache.items())),
        })
        print(
            f"translated_batch={number}/{len(batches)} batch_strings={len(batch)} cached_strings={len(cache)}",
            flush=True,
        )
        if delay:
            time.sleep(delay)


def _repair_non_chinese_descriptions(
    sources: Iterable[str],
    cache: Dict[str, str],
    catalog_path: Path,
    max_chars: int,
    delay: float,
    offline: bool,
) -> None:
    pending = sorted({
        source for source in sources
        if source and not CJK_RE.search(cache.get(source, ""))
    })
    if not pending:
        return
    if offline:
        raise RuntimeLocalizerError(f"离线模式仍有 {len(pending)} 条卡片或详情不是中文")
    batches = _batches(pending, min(max_chars, 1800))
    for number, batch in enumerate(batches, start=1):
        targets = _request_translations(batch, source_language="auto")
        cache.update(zip(batch, targets))
        _atomic_write(CACHE_PATH, {
            "schema_version": 1,
            "locale": "zh-Hans",
            "source_catalog": str(catalog_path),
            "translations": dict(sorted(cache.items())),
        })
        print(
            f"repaired_multilingual_batch={number}/{len(batches)} batch_strings={len(batch)}",
            flush=True,
        )
        if delay:
            time.sleep(delay)


def _existing_targets(payload: Mapping[str, Any]) -> Tuple[Dict[Tuple[str, str], str], Dict[Tuple[str, str], str], Dict[Tuple[str, str, str], str]]:
    descriptions: Dict[Tuple[str, str], str] = {}
    for item in payload["plugin_descriptions"]:
        for source in item["source_short"]:
            descriptions[(item["display_name"], source)] = item["target_short"]
    details: Dict[Tuple[str, str], str] = {}
    for item in payload["plugin_details"]:
        for source in item["source_long"]:
            details[(item["display_name"], source)] = item["target_long"]
    texts = {
        (item["display_name"], item["kind"], item["source"]): item["target"]
        for item in payload["plugin_texts"]
    }
    return descriptions, details, texts


def build_dictionary(
    catalog_path: Path,
    max_chars: int,
    delay: float,
    offline: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    catalog = read_json(catalog_path)
    if not isinstance(catalog, dict):
        raise RuntimeLocalizerError("远端插件目录必须是对象")
    catalog_sha256 = _sha256_file(catalog_path)
    records = _listed_records(catalog)
    existing = validate_translation_data(read_json(TRANSLATIONS_PATH))
    old_descriptions, old_details, old_texts = _existing_targets(existing)

    all_sources = _unique_strings(source for record in records for _, source in _record_fields(record))
    machine_cache = _load_machine_cache()
    _fill_machine_cache(all_sources, machine_cache, catalog_path, max_chars, delay, offline)
    description_sources = {
        source
        for record in records
        for kind, source in _record_fields(record)
        if kind in {"card_short", "detail_long"}
    }
    _repair_non_chinese_descriptions(
        description_sources, machine_cache, catalog_path, max_chars, delay, offline
    )

    descriptions: Dict[Tuple[str, str], Dict[str, Any]] = {}
    details: Dict[Tuple[str, str], Dict[str, Any]] = {}
    texts: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for record in records:
        name = record["display_name"]
        interface = record["release"]["interface"]
        short = interface["short_description"].strip()
        long = interface["long_description"].strip()
        reviewed_short = old_descriptions.get((name, short))
        short_target = reviewed_short if reviewed_short and CJK_RE.search(reviewed_short) else machine_cache[short]
        descriptions.setdefault((name, short), {
            "display_name": name,
            "source_short": [short],
            "target_short": short_target,
        })
        reviewed_long = old_details.get((name, long))
        details.setdefault((name, long), {
            "display_name": name,
            "source_long": [long],
            "target_long": reviewed_long if reviewed_long and CJK_RE.search(reviewed_long) else machine_cache[long],
        })

        def add_text(kind: str, source: str, fallback: str | None = None) -> None:
            key = (name, kind, source)
            texts.setdefault(key, {
                "display_name": name,
                "kind": kind,
                "source": source,
                "target": old_texts.get(key, fallback if fallback is not None else machine_cache[source]),
            })

        add_text("detail_short", short, short_target)
        for prompt in _prompts(interface):
            add_text("prompt", prompt)
        for skill in record["release"].get("skills") or []:
            skill_interface = skill.get("interface") if isinstance(skill, dict) else None
            if not isinstance(skill_interface, dict):
                continue
            skill_name = skill_interface.get("display_name")
            skill_short = skill_interface.get("short_description")
            if isinstance(skill_name, str) and skill_name.strip() and skill_name.strip() != name:
                add_text("skill_name", skill_name.strip())
            if isinstance(skill_short, str) and skill_short.strip():
                add_text("skill_description", skill_short.strip())
            for prompt in _prompts(skill_interface):
                add_text("prompt", prompt)

    existing_hosts = {item["source"]: item["target"] for item in existing["host_strings"]}
    host_strings = [
        {"source": source, "target": target}
        for source, target in sorted({**HOST_TRANSLATIONS, **existing_hosts}.items())
    ]
    payload = {
        "schema_version": 3,
        "locale": "zh-Hans",
        "plugin_descriptions": sorted(descriptions.values(), key=lambda item: (item["display_name"], item["source_short"][0])),
        "plugin_details": sorted(details.values(), key=lambda item: (item["display_name"], item["source_long"][0])),
        "plugin_texts": sorted(texts.values(), key=lambda item: (item["display_name"], item["kind"], item["source"])),
        "host_strings": host_strings,
    }
    validate_translation_data(payload)

    expected_descriptions = {(record["display_name"], record["release"]["interface"]["short_description"].strip()) for record in records}
    expected_details = {(record["display_name"], record["release"]["interface"]["long_description"].strip()) for record in records}
    missing = [
        *[f"card:{name}:{source}" for name, source in sorted(expected_descriptions - set(descriptions))],
        *[f"detail:{name}:{source}" for name, source in sorted(expected_details - set(details))],
    ]
    if missing:
        raise RuntimeLocalizerError(f"全量覆盖校验失败，缺少 {len(missing)} 项")

    names = Counter(record["display_name"] for record in records)
    categories = Counter(str(record["category"]) for record in records)
    statuses = Counter(str(record["status"]) for record in records)
    manifest_records = []
    for record in records:
        fields = _record_fields(record)
        manifest_records.append({
            "plugin_id": record["plugin_id"],
            "display_name": record["display_name"],
            "status": record["status"],
            "category": record["category"],
            "name_policy": "preserve_official_brand_or_product_name",
            "source_sha256": _sha256_json(fields),
            "field_count": len(set(fields)),
        })
    coverage = {
        "schema_version": 1,
        "locale": "zh-Hans",
        "source_catalog": str(catalog_path),
        "source_catalog_sha256": catalog_sha256,
        "catalog_fetched_at": catalog.get("fetched_at"),
        "selection": {"discoverability": "LISTED", "statuses": dict(sorted(statuses.items()))},
        "records": manifest_records,
        "counts": {
            "public_records": len(records),
            "unique_display_names": len(names),
            "duplicate_display_name_groups": sum(1 for count in names.values() if count > 1),
            "categories": dict(sorted(categories.items())),
            "unique_source_strings": len(all_sources),
            "source_characters": sum(map(len, all_sources)),
            "plugin_descriptions": len(payload["plugin_descriptions"]),
            "plugin_details": len(payload["plugin_details"]),
            "plugin_texts": len(payload["plugin_texts"]),
            "host_strings": len(payload["host_strings"]),
            "missing_required_pairs": 0,
        },
        "dictionary_sha256": _sha256_json(payload),
    }
    return payload, coverage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", help="现有官方目录缓存的绝对路径")
    parser.add_argument("--batch-chars", type=int, default=4500, help="每个翻译请求的近似英文字符上限")
    parser.add_argument("--delay", type=float, default=0.05, help="翻译请求间隔秒数")
    parser.add_argument("--offline", action="store_true", help="禁止联网；缺少缓存时失败")
    args = parser.parse_args()
    if not 500 <= args.batch_chars <= 6000:
        parser.error("--batch-chars 必须介于 500 和 6000")
    if not 0 <= args.delay <= 5:
        parser.error("--delay 必须介于 0 和 5 秒")
    try:
        catalog_path = _catalog_path(args.catalog)
        payload, coverage = build_dictionary(catalog_path, args.batch_chars, args.delay, args.offline)
        _atomic_write(TRANSLATIONS_PATH, payload)
        _atomic_write(COVERAGE_PATH, coverage)
        print(json.dumps({
            "ok": True,
            "catalog": str(catalog_path),
            **coverage["counts"],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
