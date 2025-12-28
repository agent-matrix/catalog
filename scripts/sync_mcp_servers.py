#!/usr/bin/env python3
"""
Daily sync for agent-matrix/catalog using mcp_ingest, writing to servers/** only.

Outputs:
- servers/<owner>-<repo>/index.json
- servers/<owner>-<repo>/<repo>__<subpath>/manifest.json
- servers/<owner>-<repo>/<repo>__<subpath>/index.json
- servers/<owner>-<repo>/<repo>__<subpath>/provenance.json
- top-level index.json

Key goals:
- Deterministic paths (no churn)
- Deprecation instead of deletion
- Active-only manifests[] in top-level index.json (prevents ingesting deprecated)
- Collision detection on manifest.id (prevents DB clobber)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mcp_ingest.harvest.source import harvest_source


# ---------------------------
# Small utilities
# ---------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def norm_repo_full(repo_url: str) -> str:
    """
    Normalize GitHub repo URL to owner/repo
    """
    s = (repo_url or "").strip().rstrip("/")
    if "github.com/" in s:
        s = s.split("github.com/", 1)[1]
    if s.endswith(".git"):
        s = s[:-4]
    # In case someone passes owner/repo already:
    s = s.strip("/")
    return s

def safe_slug(s: str) -> str:
    """
    Lowercase + replace non [a-z0-9]+ with single '-' and strip.
    """
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "unknown"

def subpath_to_variant(repo: str, subpath: str) -> str:
    """
    Build the per-server "variant directory" name:
      <repo>__<subpath>  with '/' -> '__'
    Root is represented as '.' (so folder becomes '<repo>__.') which matches your current repo.
    """
    sp = (subpath or "").lstrip("/").strip()
    if not sp:
        sp = "."
    sp = sp.replace("\\", "/")
    sp = sp.replace("/", "__")
    return f"{repo}__{sp}"

def resolve_manifest_path(harvest_out: Path, mp: str) -> Optional[Path]:
    """
    Resolve manifest path from mcp_ingest harvested index.
    """
    p = Path(mp)
    if p.is_absolute() and p.exists():
        return p

    p2 = (harvest_out / p).resolve()
    if p2.exists():
        return p2

    # last resort: filename search
    matches = list(harvest_out.rglob(p.name))
    if len(matches) == 1:
        return matches[0]
    return None


# ---------------------------
# Identity + lifecycle
# ---------------------------

@dataclass(frozen=True)
class CatalogKey:
    repo_full: str      # owner/repo
    subpath: str        # '' or 'src/...'
    transport: str      # SSE/STDIO/WS/UNKNOWN

def extract_source_repo_path(manifest: Dict[str, Any]) -> Tuple[str, str]:
    prov = manifest.get("provenance") or {}
    repo_url = prov.get("repo_url") or prov.get("repo") or prov.get("source_repo") or ""
    subpath = prov.get("subpath") or prov.get("path") or prov.get("source_path") or ""
    repo_full = norm_repo_full(str(repo_url)) if repo_url else "unknown/unknown"
    return repo_full, str(subpath or "").lstrip("/")

def extract_transport(manifest: Dict[str, Any]) -> str:
    reg = manifest.get("mcp_registration") or {}
    server = reg.get("server") or {}
    t = str(server.get("transport") or "").upper().strip()
    return t or "UNKNOWN"

def mark_active_seen(manifest: Dict[str, Any]) -> Dict[str, Any]:
    ts = now_iso()

    lifecycle = manifest.get("lifecycle") or {}
    if lifecycle.get("status") == "deprecated":
        lifecycle["status"] = "active"
        lifecycle["reactivated_at"] = ts
    lifecycle.setdefault("status", "active")
    manifest["lifecycle"] = lifecycle

    harvest = manifest.get("harvest") or {}
    harvest["seen_in_latest_run"] = True
    harvest["last_seen_at"] = ts
    manifest["harvest"] = harvest
    return manifest

def mark_deprecated(manifest: Dict[str, Any], reason: str) -> Dict[str, Any]:
    ts = now_iso()

    lifecycle = manifest.get("lifecycle") or {}
    if lifecycle.get("status") != "disabled":
        lifecycle["status"] = "deprecated"
    lifecycle.setdefault("deprecated_at", ts)
    lifecycle["reason"] = reason
    lifecycle.setdefault("replaced_by", None)
    manifest["lifecycle"] = lifecycle

    harvest = manifest.get("harvest") or {}
    harvest["seen_in_latest_run"] = False
    harvest.setdefault("last_seen_at", ts)
    manifest["harvest"] = harvest
    return manifest


# ---------------------------
# Catalog scanning (existing)
# ---------------------------

def iter_existing_manifests(servers_dir: Path) -> Iterable[Path]:
    yield from servers_dir.glob("**/manifest.json")

def load_existing_by_key(servers_dir: Path) -> Dict[CatalogKey, Path]:
    """
    Map stable key -> manifest.json path.
    This is used to deprecate "missing" entries without relying on manifest.id.
    """
    out: Dict[CatalogKey, Path] = {}
    for mf in iter_existing_manifests(servers_dir):
        try:
            m = read_json(mf)
        except Exception:
            continue
        if m.get("type") != "mcp_server":
            continue
        repo_full, subpath = extract_source_repo_path(m)
        transport = extract_transport(m)
        key = CatalogKey(repo_full=repo_full, subpath=subpath, transport=transport)
        out[key] = mf
    return out


# ---------------------------
# Path building (servers/**)
# ---------------------------

def build_group_dir(servers_dir: Path, repo_full: str) -> Path:
    """
    servers/<owner>-<repo>
    """
    owner, repo = (repo_full.split("/", 1) + ["unknown"])[:2]
    group = f"{safe_slug(owner)}-{safe_slug(repo)}"
    return servers_dir / group

def build_variant_dir(group_dir: Path, repo_full: str, subpath: str) -> Path:
    """
    servers/<owner>-<repo>/<repo>__<subpath>
    """
    _, repo = (repo_full.split("/", 1) + ["unknown"])[:2]
    variant = subpath_to_variant(safe_slug(repo), subpath)
    return group_dir / variant


# ---------------------------
# Main
# ---------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Sync MCP servers into servers/** using mcp_ingest")
    ap.add_argument("--source-repo", required=True, help="Root repo to harvest (e.g., https://github.com/modelcontextprotocol/servers)")
    ap.add_argument("--catalog-root", default=".", help="Path to catalog root")
    ap.add_argument("--servers-dir", default="servers", help="Output directory (must be servers)")
    ap.add_argument("--index-file", default="index.json", help="Top-level index.json path")
    ap.add_argument("--max-parallel", type=int, default=4)
    args = ap.parse_args()

    catalog_root = Path(args.catalog_root).resolve()
    servers_dir = (catalog_root / args.servers_dir).resolve()
    index_file = (catalog_root / args.index_file).resolve()

    # Temp harvest output
    harvest_out = catalog_root / ".tmp" / "harvest"
    if harvest_out.exists():
        shutil.rmtree(harvest_out)
    harvest_out.mkdir(parents=True, exist_ok=True)

    servers_dir.mkdir(parents=True, exist_ok=True)

    # Load existing by stable key for deprecation tracking
    existing_by_key = load_existing_by_key(servers_dir)
    seen_keys: set[CatalogKey] = set()

    # Run harvest
    harvest_source(
        repo_url=args.source_repo,
        out_dir=harvest_out,
        yes=True,
        max_parallel=args.max_parallel,
        only_github=True,
        register=False,
        matrixhub=None,
        log_file=None,
    )

    top_index_path = harvest_out / "index.json"
    if not top_index_path.exists():
        raise SystemExit(f"mcp_ingest did not produce merged index at {top_index_path}")

    harvested_index = read_json(top_index_path)
    manifest_paths = harvested_index.get("manifests") or harvested_index.get("manifest_paths") or []
    if not manifest_paths:
        raise SystemExit(f"No manifests found in {top_index_path}")

    # Collision detection on manifest.id
    id_to_key: Dict[str, CatalogKey] = {}

    # Collect output indexes
    top_items: List[Dict[str, Any]] = []
    active_manifest_relpaths: List[str] = []

    # Per-group manifest listing
    group_to_relpaths: Dict[Path, List[str]] = {}

    for mp in manifest_paths:
        src_path = resolve_manifest_path(harvest_out, mp)
        if not src_path:
            print(f"⚠️  Could not resolve manifest path: {mp}")
            continue

        manifest = read_json(src_path)
        if manifest.get("type") != "mcp_server":
            continue

        repo_full, subpath = extract_source_repo_path(manifest)
        transport = extract_transport(manifest)
        key = CatalogKey(repo_full=repo_full, subpath=subpath, transport=transport)

        # Mark active/seen in this run
        manifest = mark_active_seen(manifest)

        # Validate/track ID collisions
        mid = str(manifest.get("id") or "").strip()
        if not mid:
            # Fail hard: empty ids are too risky for DB alignment
            raise SystemExit(f"Manifest missing 'id' (repo={repo_full} subpath={subpath})")

        if mid in id_to_key and id_to_key[mid] != key:
            raise SystemExit(
                "Manifest id collision detected:\n"
                f"  id: {mid}\n"
                f"  key1: {id_to_key[mid]}\n"
                f"  key2: {key}\n"
                "This will break DB upserts. Fix upstream ids or implement a deterministic id policy."
            )
        id_to_key[mid] = key

        # Write into servers/**
        group_dir = build_group_dir(servers_dir, repo_full)
        variant_dir = build_variant_dir(group_dir, repo_full, subpath)
        variant_dir.mkdir(parents=True, exist_ok=True)

        dest_manifest = variant_dir / "manifest.json"
        write_json(dest_manifest, manifest)

        # provenance.json (helpful later for MatrixHub/DB)
        prov = manifest.get("provenance") or {}
        if not prov:
            prov = {
                "repo_url": f"https://github.com/{repo_full}",
                "subpath": subpath,
                "transport": transport,
                "harvested_from": args.source_repo,
                "harvested_at": now_iso(),
            }
        write_json(variant_dir / "provenance.json", prov)

        # Variant-level index.json
        write_json(variant_dir / "index.json", {"manifests": ["./manifest.json"]})

        # Track relpath for top-level + group-level indexes
        rel_manifest = str(dest_manifest.relative_to(catalog_root)).replace("\\", "/")
        rel_variant_manifest = str(dest_manifest.relative_to(group_dir)).replace("\\", "/")

        group_to_relpaths.setdefault(group_dir, []).append(rel_variant_manifest)

        seen_keys.add(key)

        status = (manifest.get("lifecycle") or {}).get("status", "active")

        top_items.append(
            {
                "type": "mcp_server",
                "id": mid,
                "name": manifest.get("name"),
                "transport": transport,
                "status": status,
                "manifest_path": rel_manifest,
                "repo": f"https://github.com/{repo_full}",
                "subpath": subpath,
            }
        )

        # Active-only manifests list for ingestion
        if status == "active":
            active_manifest_relpaths.append(rel_manifest)

    # Deprecate anything not seen in this run
    deprecated_added = 0
    for key, mf_path in existing_by_key.items():
        if key in seen_keys:
            continue
        try:
            m = read_json(mf_path)
        except Exception:
            continue
        if m.get("type") != "mcp_server":
            continue

        m = mark_deprecated(m, reason=f"Not found in latest harvest from {args.source_repo}")
        write_json(mf_path, m)
        deprecated_added += 1

        repo_full, subpath = extract_source_repo_path(m)
        transport = extract_transport(m)
        mid = str(m.get("id") or "").strip()

        rel_manifest = str(mf_path.relative_to(catalog_root)).replace("\\", "/")

        top_items.append(
            {
                "type": "mcp_server",
                "id": mid,
                "name": m.get("name"),
                "transport": transport,
                "status": "deprecated",
                "manifest_path": rel_manifest,
                "repo": f"https://github.com/{repo_full}",
                "subpath": subpath,
            }
        )

    # Write group-level index.json files (active + deprecated paths are okay here,
    # but we keep it simple and list everything present under the group)
    for group_dir, relpaths in group_to_relpaths.items():
        relpaths_sorted = sorted(set(relpaths))
        write_json(group_dir / "index.json", {"manifests": relpaths_sorted})

    # Deterministic sort
    top_items.sort(key=lambda x: (str(x.get("id") or ""), str(x.get("manifest_path") or "")))
    active_manifest_relpaths = sorted(set(active_manifest_relpaths))

    top_index = {
        "generated_at": now_iso(),
        "source": {
            "harvester": "mcp_ingest.harvest_source",
            "root_repo": args.source_repo,
        },
        "counts": {
            "total_items": len(top_items),
            "active_manifests": len(active_manifest_relpaths),
            "deprecated_added_this_run": deprecated_added,
        },
        # full audit trail:
        "items": top_items,
        # ingestion contract (ACTIVE ONLY, RELATIVE PATHS):
        "manifests": active_manifest_relpaths,
    }

    write_json(index_file, top_index)
    print(f"✓ Wrote top-level index: {index_file}")
    print(f"✓ Active manifests: {len(active_manifest_relpaths)}")
    print(f"✓ Deprecated newly marked: {deprecated_added}")


if __name__ == "__main__":
    main()
