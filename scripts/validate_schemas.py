#!/usr/bin/env python3
"""
Validate manifests against JSON schema.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("❌ jsonschema package required: pip install jsonschema", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate manifests against schema")
    parser.add_argument("--catalog", required=True, help="Catalog directory")
    parser.add_argument("--schema", required=True, help="JSON schema file")
    args = parser.parse_args()

    catalog = Path(args.catalog)
    schema_path = Path(args.schema)

    if not schema_path.exists():
        print(f"❌ Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    # Load schema
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
    except Exception as e:
        print(f"❌ Invalid schema file: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate all manifests
    errors = 0
    validated = 0

    for manifest_path in sorted(catalog.rglob("manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ Cannot read {manifest_path}: {e}", file=sys.stderr)
            errors += 1
            continue

        # Validate against schema
        validation_errors = list(validator.iter_errors(data))
        if validation_errors:
            print(f"\n❌ Schema validation failed for {manifest_path}:", file=sys.stderr)
            for err in validation_errors:
                path = ".".join(str(p) for p in err.path) if err.path else "root"
                print(f"   - {path}: {err.message}", file=sys.stderr)
            errors += len(validation_errors)

        validated += 1

    print(f"📊 Validated {validated} manifests against schema")

    if errors > 0:
        print(f"\n❌ Schema validation failed with {errors} errors", file=sys.stderr)
        sys.exit(1)
    else:
        print("✅ Schema validation passed")


if __name__ == "__main__":
    main()
