#!/usr/bin/env python3
"""
Validate catalog manifests against JSON schemas.

Validates all mcp-servers manifests against the official mcp_server schema,
ensuring consistency with mcp_ingest output format.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


def load_validator(schema_path: Path) -> Draft202012Validator:
    """Load JSON schema and create validator."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def main() -> None:
    """Run schema validation for all manifests."""
    root = Path(".")
    schema_path = root / "schema" / "mcp_server.schema.json"

    if not schema_path.exists():
        print(f"❌ Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    try:
        validator = load_validator(schema_path)
        print(f"✓ Loaded schema from {schema_path}")
    except Exception as e:
        print(f"❌ Failed to load schema: {e}", file=sys.stderr)
        sys.exit(1)

    errors = 0
    manifest_count = 0

    for mf in root.glob("mcp-servers/**/manifest.json"):
        manifest_count += 1

        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ Failed to parse {mf}: {e}", file=sys.stderr)
            errors += 1
            continue

        # Validate against schema
        validation_errors = list(validator.iter_errors(data))
        if validation_errors:
            print(f"\n❌ Schema validation failed for {mf}:")
            for err in sorted(validation_errors, key=str):
                path = " -> ".join(str(p) for p in err.path) if err.path else "root"
                print(f"   {path}: {err.message}", file=sys.stderr)
            errors += len(validation_errors)

    if manifest_count == 0:
        print("⚠️  No manifests found to validate", file=sys.stderr)
    else:
        print(f"✓ Validated {manifest_count} manifests against schema")

    if errors:
        print(f"\n❌ Schema validation failed with {errors} error(s)", file=sys.stderr)
        sys.exit(1)

    print("\n✓ All manifests conform to schema")


if __name__ == "__main__":
    main()
