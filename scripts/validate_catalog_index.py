#!/usr/bin/env python3
"""
Validate catalog index.json consistency.

Ensures:
- All manifest paths exist on disk
- All paths are relative (no URLs)
- No duplicate IDs
- Active manifests match lifecycle status
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    root = Path(".")
    index_path = root / "index.json"
    errors = 0

    if not index_path.exists():
        print("❌ index.json not found", file=sys.stderr)
        sys.exit(1)

    try:
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to parse index.json: {e}", file=sys.stderr)
        sys.exit(1)

    # Check required fields
    if "manifests" not in index_data:
        print("❌ index.json missing 'manifests' field", file=sys.stderr)
        errors += 1

    if "items" not in index_data:
        print("❌ index.json missing 'items' field", file=sys.stderr)
        errors += 1

    # Validate manifest paths
    manifest_paths = index_data.get("manifests", [])
    if not isinstance(manifest_paths, list):
        print("❌ index.json 'manifests' must be a list", file=sys.stderr)
        errors += 1
    else:
        for mp in manifest_paths:
            # Check not a URL
            if str(mp).startswith("http://") or str(mp).startswith("https://"):
                print(f"❌ manifests must be relative paths (found URL): {mp}", file=sys.stderr)
                errors += 1
                continue

            # Check file exists
            p = root / mp
            if not p.exists():
                print(f"❌ manifests path does not exist on disk: {mp}", file=sys.stderr)
                errors += 1

    # Validate items
    items = index_data.get("items", [])
    if not isinstance(items, list):
        print("❌ index.json 'items' must be a list", file=sys.stderr)
        errors += 1
    else:
        seen_ids: set[str] = set()
        active_paths: set[str] = set()

        for item in items:
            if not isinstance(item, dict):
                print(f"❌ item is not a dict: {item}", file=sys.stderr)
                errors += 1
                continue

            # Check required fields
            mid = item.get("id")
            if not mid:
                print(f"❌ item missing 'id': {item}", file=sys.stderr)
                errors += 1
                continue

            # Check for duplicate IDs
            if mid in seen_ids:
                print(f"❌ duplicate ID found: {mid}", file=sys.stderr)
                errors += 1
            seen_ids.add(mid)

            # Validate manifest_path
            mp = item.get("manifest_path")
            if not mp:
                print(f"❌ item missing 'manifest_path': {mid}", file=sys.stderr)
                errors += 1
                continue

            # Check path is relative
            if mp.startswith("http://") or mp.startswith("https://"):
                print(f"❌ item manifest_path is URL: {mid} → {mp}", file=sys.stderr)
                errors += 1

            # Track active manifests
            status = item.get("status", "")
            if status == "active":
                active_paths.add(mp)

        # Check that all active items are in manifests list
        manifest_paths_set = set(manifest_paths)
        for ap in active_paths:
            if ap not in manifest_paths_set:
                print(
                    f"❌ active manifest missing from index.json.manifests: {ap}", file=sys.stderr
                )
                errors += 1

        # Check that all manifests list entries are active
        for mp in manifest_paths:
            if mp not in active_paths:
                print(f"⚠️  manifest in index.json.manifests is not active: {mp}", file=sys.stderr)

    if errors:
        print(f"\n❌ Index validation failed with {errors} error(s)", file=sys.stderr)
        sys.exit(1)

    print("✓ Index validation passed")
    print(f"  - {len(manifest_paths)} manifests")
    print(f"  - {len(items)} total items")
    print(f"  - {len(seen_ids)} unique IDs")


if __name__ == "__main__":
    main()
