#!/usr/bin/env python3
"""
Validate index.json integrity and safety.

Ensures:
- manifests[] contains only relative paths (no URLs)
- All paths in manifests[] exist on disk
- All manifests are valid JSON with type="mcp_server"
- Only active manifests are in manifests[]
- All items[] manifest_path entries exist
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    root = Path(".")
    idx_path = root / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8"))

    errors = 0

    manifests = idx.get("manifests") or []
    if not isinstance(manifests, list):
        print("❌ index.json.manifests must be a list", file=sys.stderr)
        sys.exit(1)

    # 1) Ensure all manifests paths are relative, exist, and point to valid JSON
    for rel in manifests:
        if not isinstance(rel, str):
            print(f"❌ manifests entry is not a string: {rel}", file=sys.stderr)
            errors += 1
            continue
        if rel.startswith("http://") or rel.startswith("https://"):
            print(f"❌ manifests must be relative paths (found URL): {rel}", file=sys.stderr)
            errors += 1
            continue
        if "..." in rel:
            print(f"❌ manifests path contains '...': {rel}", file=sys.stderr)
            errors += 1
            continue

        p = root / rel
        if not p.exists():
            print(f"❌ manifests path does not exist on disk: {rel}", file=sys.stderr)
            errors += 1
            continue

        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ manifest is not valid JSON: {rel} ({e})", file=sys.stderr)
            errors += 1
            continue

        if m.get("type") != "mcp_server":
            print(f"❌ manifest type must be mcp_server: {rel}", file=sys.stderr)
            errors += 1

        status = (m.get("lifecycle") or {}).get("status", "active")
        if status != "active":
            print(f"❌ non-active manifest included in manifests[]: {rel} (status={status})", file=sys.stderr)
            errors += 1

    # 2) Ensure items[] manifest_path entries exist (if items[] is present)
    items = idx.get("items") or []
    if items:
        for it in items:
            rel = it.get("manifest_path")
            if not rel or not isinstance(rel, str):
                print(f"❌ item missing manifest_path: {it}", file=sys.stderr)
                errors += 1
                continue
            if "..." in rel:
                print(f"❌ item manifest_path contains '...': {rel}", file=sys.stderr)
                errors += 1
                continue
            if not (root / rel).exists():
                print(f"❌ item manifest_path not found on disk: {rel}", file=sys.stderr)
                errors += 1

    if errors:
        print(f"\n❌ Index integrity validation failed with {errors} error(s)", file=sys.stderr)
        sys.exit(1)

    print("✓ Index integrity validation passed")


if __name__ == "__main__":
    main()
