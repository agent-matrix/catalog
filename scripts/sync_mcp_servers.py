#!/usr/bin/env python3
"""
Production-ready sync script for agent-matrix/catalog.
Uses mcp_ingest.harvest.source to discover MCP servers, then deterministically
rebuilds the catalog structure with stable slugging and deduplication.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp_ingest.harvest.source import harvest_source
from mcp_ingest.utils.slug import slug_from_repo_and_path


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    """Read and parse JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    """Write object as formatted JSON with deterministic sorting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def norm_repo_full(repo_url: str) -> str:
    """
    Normalize GitHub repo URL to owner/repo format.

    Examples:
        https://github.com/owner/repo -> owner/repo
        https://github.com/owner/repo.git -> owner/repo
    """
    repo_url = repo_url.strip().rstrip("/")
    if "github.com/" in repo_url:
        repo_url = repo_url.split("github.com/", 1)[1]
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    return repo_url


@dataclass(frozen=True)
class CatalogItemKey:
    """Unique key for deduplication of catalog items."""
    repo: str
    path: str
    transport: str
    manifest_id: str


def extract_source_repo_path(manifest: dict[str, Any]) -> tuple[str, str]:
    """
    Extract repository and subpath from manifest provenance.

    mcp_ingest manifests may include source/provenance fields depending on harvesters.
    We try best-effort extraction. If missing, fall back to "unknown".

    Returns:
        tuple[str, str]: (normalized_repo, subpath)
    """
    prov = manifest.get("provenance") or {}
    repo_url = prov.get("repo_url") or prov.get("repo") or prov.get("source_repo") or ""
    subpath = prov.get("subpath") or prov.get("path") or prov.get("source_path") or ""
    return (norm_repo_full(str(repo_url)) if repo_url else "unknown/unknown", str(subpath or "").lstrip("/"))


def extract_transport(manifest: dict[str, Any]) -> str:
    """
    Extract transport type from MCP server manifest.

    Returns transport in uppercase: "SSE", "STDIO", "WS", or "UNKNOWN".
    """
    reg = manifest.get("mcp_registration") or {}
    server = reg.get("server") or {}
    transport = str(server.get("transport") or "").upper().strip()
    return transport or "UNKNOWN"


def build_catalog_folder(out_dir: Path, repo_full: str, subpath: str) -> Path:
    """
    Build deterministic catalog folder path using stable slugging.

    Structure: out_dir/github.com/owner/repo/stable-slug/

    Args:
        out_dir: Base output directory (e.g., mcp-servers)
        repo_full: Repository in owner/repo format
        subpath: Subpath within repository

    Returns:
        Path to catalog folder for this server
    """
    owner, repo = (repo_full.split("/", 1) + ["unknown"])[:2]
    stable = slug_from_repo_and_path(owner, repo, subpath or "")
    return out_dir / "github.com" / owner / repo / stable


def main() -> None:
    """Main sync orchestration."""
    ap = argparse.ArgumentParser(
        description="Sync MCP servers catalog using mcp_ingest harvester"
    )
    ap.add_argument(
        "--source-repo",
        required=True,
        help="Root repo to harvest (e.g., https://github.com/modelcontextprotocol/servers)"
    )
    ap.add_argument(
        "--catalog-root",
        required=True,
        help="Path to catalog root (usually '.')"
    )
    ap.add_argument(
        "--out-dir",
        required=True,
        help="Catalog output directory for MCP servers (e.g., mcp-servers)"
    )
    ap.add_argument(
        "--index-file",
        required=True,
        help="Top-level catalog index file (e.g., index.json)"
    )
    ap.add_argument(
        "--max-parallel",
        type=int,
        default=4,
        help="Maximum parallel harvesting operations"
    )
    args = ap.parse_args()

    catalog_root = Path(args.catalog_root).resolve()
    out_dir = (catalog_root / args.out_dir).resolve()
    index_file = (catalog_root / args.index_file).resolve()

    # Temp harvest output
    harvest_out = catalog_root / ".tmp" / "harvest"
    if harvest_out.exists():
        shutil.rmtree(harvest_out)
    harvest_out.mkdir(parents=True, exist_ok=True)

    print(f"Starting harvest of {args.source_repo}...")
    print(f"Output will be written to {out_dir}")

    # Run mcp_ingest harvester
    # GITHUB_TOKEN should be set via environment for better API limits
    summary = harvest_source(
        repo_url=args.source_repo,
        out_dir=harvest_out,
        yes=True,
        max_parallel=args.max_parallel,
        only_github=True,
        register=False,
        matrixhub=None,
        log_file=None,
    )

    # Read harvested index
    top_index_path = harvest_out / "index.json"
    if not top_index_path.exists():
        raise SystemExit(f"mcp_ingest did not produce merged index at {top_index_path}")

    harvested_index = read_json(top_index_path)
    manifest_paths = harvested_index.get("manifests") or harvested_index.get("manifest_paths") or []

    if not manifest_paths:
        raise SystemExit(f"No manifests found in {top_index_path}")

    print(f"Found {len(manifest_paths)} manifests from harvest")

    # Ensure output directory exists
    out_dir.mkdir(parents=True, exist_ok=True)

    # Process manifests with deduplication
    touched: list[Path] = []
    items_for_index: list[dict[str, Any]] = []
    seen: set[CatalogItemKey] = set()

    for mp in manifest_paths:
        src_path = Path(mp)
        if not src_path.is_absolute():
            src_path = (harvest_out / src_path).resolve()
        if not src_path.exists():
            # mcp_ingest sometimes returns absolute; sometimes relative
            # best-effort fallback: try joining harvest_out
            continue

        manifest = read_json(src_path)

        if manifest.get("type") != "mcp_server":
            # ignore non-mcp_server manifests (if any appear later)
            continue

        repo_full, subpath = extract_source_repo_path(manifest)
        transport = extract_transport(manifest)
        manifest_id = str(manifest.get("id") or "")

        # Deduplicate by key
        key = CatalogItemKey(repo=repo_full, path=subpath, transport=transport, manifest_id=manifest_id)
        if key in seen:
            continue
        seen.add(key)

        # Build deterministic destination folder
        dest_folder = build_catalog_folder(out_dir, repo_full, subpath)
        dest_manifest = dest_folder / "manifest.json"
        dest_folder.mkdir(parents=True, exist_ok=True)

        # Write manifest exactly as emitted by mcp_ingest
        write_json(dest_manifest, manifest)
        touched.append(dest_folder)

        # Write provenance sidecar for DB population later
        prov = manifest.get("provenance") or {}
        if not prov:
            prov = {
                "repo_url": f"https://github.com/{repo_full}",
                "subpath": subpath,
                "transport": transport,
                "harvested_from": args.source_repo,
                "harvested_at": now_iso(),
            }
        write_json(dest_folder / "provenance.json", prov)

        # Build index entry
        items_for_index.append(
            {
                "type": "mcp_server",
                "id": manifest_id,
                "name": manifest.get("name"),
                "transport": transport,
                "manifest_path": str(dest_manifest.relative_to(catalog_root)).replace("\\", "/"),
                "repo": f"https://github.com/{repo_full}",
                "subpath": subpath,
            }
        )

    # Build deterministic top-level index (sorted for stability)
    items_for_index.sort(key=lambda x: (str(x.get("id") or ""), str(x.get("manifest_path") or "")))

    top_index = {
        "generated_at": now_iso(),
        "source": {
            "harvester": "mcp_ingest.harvest_source",
            "root_repo": args.source_repo,
        },
        "counts": {
            "mcp_servers": len(items_for_index),
        },
        "items": items_for_index,
    }

    write_json(index_file, top_index)
    print(f"✓ Synced {len(items_for_index)} mcp_server manifests into {out_dir}")
    print(f"✓ Updated {index_file}")


if __name__ == "__main__":
    main()
