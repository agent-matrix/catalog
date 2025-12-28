#!/usr/bin/env python3
"""
Validate catalog structure and manifest requirements (servers/**).

Ensures:
- index.json exists and is valid
- All servers/** manifests parse correctly
- Required fields are present for Matrix Hub ingestion and DB population
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
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
            print("✓ index.json is valid JSON")

            if "manifests" not in index_data:
                print("❌ index.json missing 'manifests' field", file=sys.stderr)
                errors += 1
            if "items" not in index_data:
                print("⚠️  index.json missing 'items' field (recommended for auditing)", file=sys.stderr)

            if "manifests" in index_data and not isinstance(index_data["manifests"], list):
                print("❌ index.json 'manifests' must be a list", file=sys.stderr)
                errors += 1

        except Exception as e:
            print(f"❌ Invalid JSON in index.json: {e}", file=sys.stderr)
            errors += 1

    # Validate all servers/** manifests
    manifest_count = 0
    for mf in root.glob("servers/**/manifest.json"):
        manifest_count += 1

        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ Invalid JSON {mf}: {e}", file=sys.stderr)
            errors += 1
            continue

        if data.get("type") != "mcp_server":
            print(f"❌ Unexpected type in {mf}: {data.get('type')} (expected 'mcp_server')", file=sys.stderr)
            errors += 1

        # Minimum viable keys for Matrix Hub & DB population
        for field in ["id", "name", "mcp_registration"]:
            if field not in data or data.get(field) in (None, ""):
                print(f"❌ Missing required field '{field}' in {mf}", file=sys.stderr)
                errors += 1

        reg = data.get("mcp_registration") or {}
        server = reg.get("server") or {}

        transport = server.get("transport")
        if not transport:
            print(f"❌ Missing mcp_registration.server.transport in {mf}", file=sys.stderr)
            errors += 1
        else:
            if transport not in ["SSE", "STDIO", "WS"]:
                print(f"⚠️  Unexpected transport '{transport}' in {mf} (expected SSE, STDIO, or WS)", file=sys.stderr)

            if transport in ["SSE", "WS"]:
                if not server.get("url"):
                    print(f"❌ Missing server.url for {transport} transport in {mf}", file=sys.stderr)
                    errors += 1
            elif transport == "STDIO":
                if not server.get("exec"):
                    print(f"❌ Missing server.exec for STDIO transport in {mf}", file=sys.stderr)
                    errors += 1

    if manifest_count == 0:
        print("❌ No manifests found in servers/** (sync likely misconfigured)", file=sys.stderr)
        errors += 1
    else:
        print(f"✓ Validated {manifest_count} manifests under servers/**")

    if errors:
        print(f"\n❌ Validation failed with {errors} error(s)", file=sys.stderr)
        sys.exit(1)

    print("\n✓ Catalog structure validation passed")


if __name__ == "__main__":
    main()
