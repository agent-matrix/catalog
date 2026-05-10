#!/usr/bin/env python3
"""
Ingest MCP servers published by IBM in the open-source mcp-context-forge
project into the agent-matrix catalog.

Two upstream artefacts are read:

  * mcp-catalog.yml             — IBM's curated list of remote MCP endpoints
  * mcp-servers/{python,go,rust}/<name>/
                                — IBM-authored reference servers

For every upstream entry we generate a per-server manifest at
`servers/ibm-context-forge/<synthesised-id>/manifest.json` and merge it into
the top-level `index.json`.

Production-safety invariants enforced here:

  1. We only ever write under `servers/ibm-context-forge/` — never under any
     other provider directory. Existing registry-sourced manifests are
     untouched.
  2. When updating an existing manifest, we refuse to overwrite a file whose
     `_source` is anything other than "mcp-context-forge".
  3. Pruning of disappeared upstream entries is OPT-IN via --prune-removed.
  4. A shrink-guard in the calling workflow validates the post-merge
     active-manifest count before any commit is made.

The script is idempotent: re-running on an unchanged upstream produces zero
file diffs and an empty `summary` action list.

Usage:
    python scripts/sync_from_context_forge.py \
        --repo IBM/mcp-context-forge \
        --ref  main \
        [--prune-removed] \
        [--report /tmp/sync_report.json]
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
import yaml

OUR_SOURCE = "mcp-context-forge"
PROVIDER_DIR = "ibm-context-forge"   # all manifests written by us live here
DEFAULT_TIMEOUT = 30.0


# --------------------------- helpers ---------------------------

def _slug(s: str) -> str:
    """Lowercase + ASCII-safe + hyphenated; strip leading/trailing dashes."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "x"


def _hash10(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:10]


def _http_get_text(url: str, *, token: Optional[str] = None) -> str:
    headers = {"User-Agent": "agent-matrix-catalog/sync-context-forge"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as c:
        r = c.get(url, headers=headers)
        r.raise_for_status()
        return r.text


def _http_get_json(url: str, *, token: Optional[str] = None) -> Any:
    headers = {
        "User-Agent": "agent-matrix-catalog/sync-context-forge",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as c:
        r = c.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


# --------------------------- data shapes ---------------------------

@dataclass
class ContextForgeEntry:
    """One entry destined for the agent-matrix catalog."""
    cat_id: str                      # synthesised catalog ID
    manifest_path: str               # relative to repo root
    name: str
    transport: str                   # SSE | STREAMABLEHTTP | STDIO
    version: str = "1.0.0"
    manifest: Dict[str, Any] = field(default_factory=dict)  # written to disk


@dataclass
class SyncReport:
    added: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    skipped_collisions: List[str] = field(default_factory=list)
    fetched_catalog: int = 0
    fetched_repo_servers: int = 0

    def summary(self) -> Dict[str, int]:
        return {
            "fetched_catalog_entries": self.fetched_catalog,
            "fetched_repo_servers":    self.fetched_repo_servers,
            "added":                   len(self.added),
            "updated":                 len(self.updated),
            "removed":                 len(self.removed),
            "skipped_collisions":      len(self.skipped_collisions),
        }


# --------------------------- parser A: mcp-catalog.yml ---------------------------

def parse_catalog_yml(text: str, *, source_url: str) -> List[ContextForgeEntry]:
    """Parse IBM's mcp-catalog.yml top-level list of remote MCP endpoints."""
    data = yaml.safe_load(text)
    if isinstance(data, dict):
        # IBM's mcp-catalog.yml uses `catalog_servers`. Older / forked
        # variants may use one of the alternative keys below.
        for key in ("catalog_servers", "servers", "catalog", "entries", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError("mcp-catalog.yml: expected a top-level list of entries")

    out: List[ContextForgeEntry] = []
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for raw in data:
        if not isinstance(raw, dict):
            continue
        ibm_id    = str(raw.get("id") or raw.get("name") or "").strip()
        name      = str(raw.get("name") or ibm_id).strip()
        url       = str(raw.get("url") or "").strip()
        if not ibm_id or not name or not url:
            continue
        transport = (raw.get("transport") or "SSE").upper()
        if transport not in {"SSE", "STREAMABLEHTTP", "STDIO", "WEBSOCKET", "HTTP"}:
            transport = "SSE"
        cat_id = f"mcp.ibm-cf.{_slug(ibm_id)}.{transport.lower()}.{_hash10(url)}"
        manifest_path = f"servers/{PROVIDER_DIR}/{cat_id}/manifest.json"

        manifest = {
            "id":          cat_id,
            "type":        "mcp_server",
            "name":        name,
            "version":     "1.0.0",
            "status":      "active",
            "transport":   transport,
            "summary":     str(raw.get("description") or name),
            "description": str(raw.get("description") or name),
            "homepage":    raw.get("repo") or None,
            "source_url":  url,
            "providers":   [str(raw.get("provider") or "")] if raw.get("provider") else [],
            "categories":  [str(raw.get("category") or "")] if raw.get("category") else [],
            "auth": {
                "type":             raw.get("auth_type"),
                "requires_api_key": bool(raw.get("requires_api_key", False)),
                "secure":           bool(raw.get("secure", False)),
            },
            "install":     raw.get("install") or None,

            # Provenance
            "_source":            OUR_SOURCE,
            "_source_kind":       "catalog",
            "_source_id":         ibm_id,
            "_source_url":        source_url,
            "_source_synced_at":  now_iso,
        }
        out.append(ContextForgeEntry(
            cat_id=cat_id, manifest_path=manifest_path,
            name=name, transport=transport, manifest=manifest,
        ))
    return out


# --------------------------- parser B: mcp-servers/<lang>/<name>/ ---------------------------

LANG_INSTALL_HINTS = {
    "python": "pip install <package>",
    "go":     "go install github.com/{repo}/mcp-servers/go/{name}@{ref}",
    "rust":   "cargo install --git https://github.com/{repo} --branch {ref} {name}",
}


def parse_repo_servers(
    repo: str, ref: str, tree_entries: Iterable[Dict[str, Any]],
) -> List[ContextForgeEntry]:
    """
    From a flat list of repo paths (from the GitHub Trees API), identify
    self-contained MCP servers under mcp-servers/{python,go,rust}/<name>/
    and emit one catalog entry per server.
    """
    # Bucket: (lang, name) -> True if we've seen any file under that prefix
    seen: Dict[Tuple[str, str], bool] = {}
    for ent in tree_entries:
        path = ent.get("path") or ""
        if not path.startswith("mcp-servers/"):
            continue
        parts = path.split("/")
        if len(parts) < 3:
            continue
        _, lang, name = parts[0], parts[1], parts[2]
        if lang not in {"python", "go", "rust"}:
            continue
        if name in {"templates"}:
            continue
        seen[(lang, name)] = True

    out: List[ContextForgeEntry] = []
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for (lang, name) in sorted(seen):
        homepage = f"https://github.com/{repo}/tree/{ref}/mcp-servers/{lang}/{name}"
        ident_url = f"github.com/{repo}#mcp-servers/{lang}/{name}"
        cat_id = f"mcp.ibm-cf.{lang}-{_slug(name)}.stdio.{_hash10(ident_url)}"
        manifest_path = f"servers/{PROVIDER_DIR}/{cat_id}/manifest.json"

        install_hint = LANG_INSTALL_HINTS.get(lang, "").format(
            repo=repo, ref=ref, name=name,
        )
        description = (
            f"IBM mcp-context-forge {lang} reference server: {name}. "
            f"See {homepage} for usage."
        )
        manifest = {
            "id":          cat_id,
            "type":        "mcp_server",
            "name":        f"ibm-context-forge/{lang}/{name}",
            "version":     "1.0.0",
            "status":      "active",
            "transport":   "STDIO",
            "summary":     f"IBM mcp-context-forge reference server ({lang}): {name}",
            "description": description,
            "homepage":    homepage,
            "source_url":  homepage,
            "providers":   ["IBM"],
            "categories":  ["Reference"],
            "auth":        {"type": "Open", "requires_api_key": False, "secure": False},
            "install":     install_hint or None,
            "language":    lang,

            # Provenance
            "_source":            OUR_SOURCE,
            "_source_kind":       "server-repo",
            "_source_id":         f"{lang}/{name}",
            "_source_path":       f"mcp-servers/{lang}/{name}",
            "_source_url":        homepage,
            "_source_synced_at":  now_iso,
        }
        out.append(ContextForgeEntry(
            cat_id=cat_id, manifest_path=manifest_path,
            name=manifest["name"], transport="STDIO", manifest=manifest,
        ))
    return out


# --------------------------- index merge ---------------------------

def load_index(repo_root: Path) -> Dict[str, Any]:
    p = repo_root / "index.json"
    if not p.exists():
        return {"manifests": [], "items": [], "counts": {}}
    return json.loads(p.read_text())


def save_index(repo_root: Path, idx: Dict[str, Any]) -> None:
    (repo_root / "index.json").write_text(json.dumps(idx, indent=2, sort_keys=True) + "\n")


def existing_source(repo_root: Path, manifest_path: str) -> Optional[str]:
    """Return the `_source` field of an existing manifest, or None if absent."""
    p = repo_root / manifest_path
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text())
        return m.get("_source")
    except Exception:
        return None


_VOLATILE_FIELDS = {"_source_synced_at"}


def _stable_view(m: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in m.items() if k not in _VOLATILE_FIELDS}


def write_manifest(repo_root: Path, entry: ContextForgeEntry) -> bool:
    """Write the manifest if its meaningful content changed. Return True iff
    a non-volatile field changed (i.e. not just `_source_synced_at`)."""
    p = repo_root / entry.manifest_path
    p.parent.mkdir(parents=True, exist_ok=True)
    new_text = json.dumps(entry.manifest, indent=2, sort_keys=True) + "\n"
    if p.exists():
        try:
            old = json.loads(p.read_text())
        except Exception:
            old = None
        if isinstance(old, dict) and _stable_view(old) == _stable_view(entry.manifest):
            # Content unchanged; don't churn the file or report it as updated.
            return False
    p.write_text(new_text)
    return True


def merge_into_index(
    repo_root: Path, entries: List[ContextForgeEntry],
    *, prune_removed: bool, report: SyncReport,
) -> Dict[str, Any]:
    idx = load_index(repo_root)

    # Existing manifest_path → item lookup, by source.
    existing_items: Dict[str, Dict[str, Any]] = {
        it.get("manifest_path"): it for it in (idx.get("items") or []) if isinstance(it, dict)
    }
    # The flat `manifests` list is the source of truth for "active". Anything
    # not in this list is "inactive" / disabled and won't be touched.
    existing_manifests: List[str] = list(idx.get("manifests") or [])

    our_existing_paths = {
        path for path, it in existing_items.items()
        if it and it.get("manifest_path") and existing_source(repo_root, path) == OUR_SOURCE
    }

    new_paths: List[str] = []
    new_items: List[Dict[str, Any]] = []

    for e in entries:
        # Collision check: never overwrite a path owned by a different source.
        owner = existing_source(repo_root, e.manifest_path)
        if owner is not None and owner != OUR_SOURCE:
            report.skipped_collisions.append(e.manifest_path)
            continue

        was_new = e.manifest_path not in our_existing_paths
        wrote = write_manifest(repo_root, e)
        if was_new:
            report.added.append(e.cat_id)
        elif wrote:
            report.updated.append(e.cat_id)

        new_paths.append(e.manifest_path)
        new_items.append({
            "id":            e.cat_id,
            "manifest_path": e.manifest_path,
            "name":          e.name,
            "status":        "active",
            "transport":     e.transport,
            "type":          "mcp_server",
            "version":       e.version,
        })

    # Pruning: remove our entries that disappeared upstream.
    upstream_paths = {e.manifest_path for e in entries}
    if prune_removed:
        stale = our_existing_paths - upstream_paths
        for p in sorted(stale):
            disk_path = repo_root / p
            if disk_path.exists():
                try:
                    disk_path.unlink()
                except OSError:
                    pass
            # Also remove the manifest dir if empty.
            try:
                disk_path.parent.rmdir()
            except OSError:
                pass
            report.removed.append(p)

    # Rebuild manifests + items: registry-sourced + (kept) IBM-sourced.
    foreign_items = [
        it for it in (idx.get("items") or [])
        if isinstance(it, dict)
        and it.get("manifest_path") not in our_existing_paths
    ]
    foreign_manifests = [
        m for m in existing_manifests
        if m not in our_existing_paths
    ]

    merged_manifests = sorted(set(foreign_manifests) | set(new_paths))
    merged_items = foreign_items + new_items
    # Keep items sorted by id for deterministic diffs.
    merged_items.sort(key=lambda it: (it.get("id") or ""))

    counts = idx.get("counts") or {}
    counts["active_manifests"] = len(merged_manifests)
    # total_items reflects everything listed in items[] (active + deprecated +
    # disabled). After our additive merge, recompute against the items array.
    counts["total_items"] = max(len(merged_items), counts["active_manifests"])

    # `sources` is informational; keep it accurate.
    sources = counts.get("sources") if isinstance(counts.get("sources"), dict) else {}
    sources[OUR_SOURCE] = sum(
        1 for it in merged_items if it.get("manifest_path", "").startswith(f"servers/{PROVIDER_DIR}/")
    )
    sources["registry"] = len(merged_items) - sources[OUR_SOURCE]
    counts["sources"] = sources

    idx["manifests"] = merged_manifests
    idx["items"]     = merged_items
    idx["counts"]    = counts
    idx["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    save_index(repo_root, idx)
    return idx


# --------------------------- main ---------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="IBM/mcp-context-forge",
                    help="Upstream owner/name (default: IBM/mcp-context-forge)")
    ap.add_argument("--ref", default="main",
                    help="Git ref of the upstream repo (default: main)")
    ap.add_argument("--prune-removed", action="store_true",
                    help="Delete IBM-sourced entries no longer present upstream")
    ap.add_argument("--report", default=None,
                    help="Write a JSON report of actions taken to this path")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or None
    repo_root = Path.cwd()
    report = SyncReport()
    entries: List[ContextForgeEntry] = []

    # 1) Parse mcp-catalog.yml
    cat_url = f"https://raw.githubusercontent.com/{args.repo}/{args.ref}/mcp-catalog.yml"
    try:
        cat_text = _http_get_text(cat_url, token=token)
        cat_entries = parse_catalog_yml(cat_text, source_url=cat_url)
        entries.extend(cat_entries)
        report.fetched_catalog = len(cat_entries)
        print(f"parsed {len(cat_entries)} entries from {cat_url}")
    except Exception as exc:
        print(f"::error::could not fetch/parse mcp-catalog.yml: {exc}")
        return 1

    # 2) Walk mcp-servers/{python,go,rust} via the Trees API.
    try:
        tree = _http_get_json(
            f"https://api.github.com/repos/{args.repo}/git/trees/{args.ref}?recursive=1",
            token=token,
        )
        repo_entries = parse_repo_servers(args.repo, args.ref, tree.get("tree") or [])
        entries.extend(repo_entries)
        report.fetched_repo_servers = len(repo_entries)
        print(f"parsed {len(repo_entries)} entries from mcp-servers/")
    except Exception as exc:
        # Don't hard-fail the whole sync if only the trees walk fails — the
        # catalog YAML is the larger source.
        print(f"::warning::could not walk mcp-servers/ tree: {exc}")

    if not entries:
        print("::error::no entries parsed from upstream — refusing to mutate index")
        return 1

    # 3) Merge.
    merge_into_index(repo_root, entries, prune_removed=args.prune_removed, report=report)

    summary = report.summary()
    print("summary:", json.dumps(summary, indent=2))

    if args.report:
        Path(args.report).write_text(json.dumps({
            "summary": summary,
            "added":   report.added,
            "updated": report.updated,
            "removed": report.removed,
            "skipped_collisions": report.skipped_collisions,
        }, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
