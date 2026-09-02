#!/usr/bin/env python3
"""Build a reproducible source ZIP from a clean, tracked Git tree."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main() -> None:
    if git("status", "--porcelain").strip():
        raise SystemExit("Commit or preserve pending work before packaging; a clean tree is required.")
    version = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Release version must be a stable major.minor.patch value.")
    tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    entries = git("ls-tree", "-r", "-z", "HEAD").split(b"\0")
    prefix = f"codex-plugin-store-localizer-v{version}"
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    archive = destination / f"{prefix}.zip"
    if archive.exists():
        raise SystemExit(f"Refusing to overwrite existing release artifact: {archive}")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for entry in entries:
            if not entry:
                continue
            meta, raw_path = entry.split(b"\t", 1)
            mode, kind, sha = meta.decode().split()
            path = raw_path.decode()
            if kind != "blob" or mode not in ("100644", "100755"):
                raise SystemExit(f"Unsupported release entry: {path}")
            if path.startswith(("/", "dist/", "backups/", ".git/")) or ".." in Path(path).parts:
                raise SystemExit(f"Unsafe release path: {path}")
            if "machine-cache" in path or path.endswith((".pyc", ".env")):
                raise SystemExit(f"Local-only data in tracked tree: {path}")
            info = zipfile.ZipInfo(f"{prefix}/{path}", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = int(mode, 8) << 16
            bundle.writestr(info, git("cat-file", "blob", sha))
        provenance = json.dumps({"version": version, "git_tree": tree, "format": "source-bundle"}, indent=2) + "\n"
        bundle.writestr(zipfile.ZipInfo(f"{prefix}/RELEASE_SOURCE.json", (1980, 1, 1, 0, 0, 0)), provenance)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise SystemExit("ZIP integrity check failed")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksums = destination / "SHA256SUMS.txt"
    checksums.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive), "sha256": digest, "source_tree": tree, "checksums": str(checksums)}, indent=2))


if __name__ == "__main__":
    main()
