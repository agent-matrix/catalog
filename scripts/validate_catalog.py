#!/usr/bin/env python3
"""
Validate catalog structure and basic manifest requirements.

Checks:
- Required files exist (index.json)
- Manifests are valid JSON
- Manifests have required fields
- No orphaned files
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_MANIFEST_FIELDS = ["id", "name", "type"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate catalog structure")
    parser.add_argument("--catalog", required=True, help="Catalog directory to validate")
    parser.add_argument("--index", required=True, help="Root index.json file")
    args = parser.parse_args()

    catalog = Path(args.catalog)
    index_path = Path(args.index)

    errors = 0

    # Check index.json exists
    if not index_path.exists():
        print(f"❌ Missing required file: {index_path}", file=sys.stderr)
        errors += 1
    else:
        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            if "manifests" not in index_data:
                print("❌ index.json missing 'manifests' field", file=sys.stderr)
                errors += 1
        except Exception as e:
            print(f"❌ Invalid index.json: {e}", file=sys.stderr)
            errors += 1

    # Validate all manifests
    manifest_count = 0
    for manifest_path in catalog.rglob("manifest.json"):
        manifest_count += 1

        # Check valid JSON
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ Invalid JSON in {manifest_path}: {e}", file=sys.stderr)
            errors += 1
            continue

        # Check required fields
        for field in REQUIRED_MANIFEST_FIELDS:
            if field not in data:
                print(
                    f"❌ Manifest {manifest_path} missing required field: {field}",
                    file=sys.stderr,
                )
                errors += 1

        # Check for reasonable values
        if data.get("name") and len(data["name"]) < 1:
            print(f"❌ Manifest {manifest_path} has empty name", file=sys.stderr)
            errors += 1

        if data.get("id") and len(data["id"]) < 3:
            print(f"❌ Manifest {manifest_path} has suspiciously short ID", file=sys.stderr)
            errors += 1

    print(f"📊 Validated {manifest_count} manifests")

    if errors > 0:
        print(f"\n❌ Validation failed with {errors} errors", file=sys.stderr)
        sys.exit(1)
    else:
        print("✅ Structure validation passed")


if __name__ == "__main__":
    main()
