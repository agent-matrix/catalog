#!/usr/bin/env python3
"""
Validate catalog structure and manifest requirements.

Ensures:
- index.json exists and is valid
- All mcp-servers manifests parse correctly
- Required fields are present for Matrix Hub ingestion and DB population
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    """Run structure validation checks."""
    root = Path(".")
    errors = 0

    # Check for required top-level index
    index_path = root / "index.json"
    if not index_path.exists():
        print("❌ Missing required file: index.json", file=sys.stderr)
        errors += 1
    else:
        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            print(f"✓ index.json is valid JSON")

            # Validate index structure
            if "items" not in index_data:
                print("⚠️  index.json missing 'items' field", file=sys.stderr)
        except Exception as e:
            print(f"❌ Invalid JSON in index.json: {e}", file=sys.stderr)
            errors += 1

    # Validate all mcp-servers manifests
    manifest_count = 0
    for mf in root.glob("mcp-servers/**/manifest.json"):
        manifest_count += 1

        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ Invalid JSON {mf}: {e}", file=sys.stderr)
            errors += 1
            continue

        # Check type
        if data.get("type") != "mcp_server":
            print(f"❌ Unexpected type in {mf}: {data.get('type')} (expected 'mcp_server')", file=sys.stderr)
            errors += 1

        # Minimum viable keys for Matrix Hub & DB population
        required_fields = ["id", "name", "mcp_registration"]
        for field in required_fields:
            if field not in data:
                print(f"❌ Missing required field '{field}' in {mf}", file=sys.stderr)
                errors += 1

        # Check mcp_registration structure
        reg = data.get("mcp_registration") or {}
        server = reg.get("server") or {}

        if "transport" not in server:
            print(f"❌ Missing mcp_registration.server.transport in {mf}", file=sys.stderr)
            errors += 1
        else:
            transport = server.get("transport")
            if transport not in ["SSE", "STDIO", "WS"]:
                print(f"⚠️  Unexpected transport '{transport}' in {mf} (expected SSE, STDIO, or WS)", file=sys.stderr)

            # Validate transport-specific requirements
            if transport == "SSE" or transport == "WS":
                if "url" not in server or not server.get("url"):
                    print(f"❌ Missing server.url for {transport} transport in {mf}", file=sys.stderr)
                    errors += 1
            elif transport == "STDIO":
                if "exec" not in server or not server.get("exec"):
                    print(f"❌ Missing server.exec for STDIO transport in {mf}", file=sys.stderr)
                    errors += 1

    if manifest_count == 0:
        print("⚠️  No manifests found in mcp-servers/", file=sys.stderr)
    else:
        print(f"✓ Validated {manifest_count} manifests")

    if errors:
        print(f"\n❌ Validation failed with {errors} error(s)", file=sys.stderr)
        sys.exit(1)

    print("\n✓ Catalog structure validation passed")


if __name__ == "__main__":
    main()
