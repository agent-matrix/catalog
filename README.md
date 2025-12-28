<p align="center">
  <img src="https://github.com/agent-matrix/.github/blob/main/profile/logo.png" alt="Agent-Matrix Logo" width="200">
</p>

<h1 align="center">
  Agent-Matrix Catalog
</h1>

<p align="center">
  <a href="https://github.com/ruslanmv/agent-generator"><img src="https://img.shields.io/badge/Powered%20by-agent--generator-brightgreen" alt="Powered by agent-generator"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue" alt="License"></a>
</p>



## Overview

The **Agent-Matrix Catalog** is a production-ready, versioned registry of **MCP servers** (agents/tools) for MatrixHub.

### Key Features

- 🔄 **Automated Daily Sync**: Harvests from `modelcontextprotocol/servers` using `mcp_ingest`
- 🎯 **Deterministic Structure**: Stable folder mapping with deduplication
- ✅ **Schema Validation**: All manifests conform to `mcp_server` schema
- 📦 **Matrix Hub Ready**: Format designed for seamless DB population
- 🔗 **Discoverable**: Single `index.json` with all server metadata

### Architecture

This catalog is the **source of truth** for Matrix Hub's MCP server registry:

1. **Harvesting**: Uses `mcp_ingest.harvest_source()` to discover servers
2. **Processing**: Deterministic folder mapping via stable slugging
3. **Validation**: Schema + structure checks on every PR
4. **Ingestion**: Matrix Hub reads catalog to populate database


## Repository Layout

```
.
├── index.json                      # Top-level catalog (deterministic, sorted)
├── schema/
│   └── mcp_server.schema.json     # JSON Schema for validation
├── scripts/
│   ├── sync_mcp_servers.py        # Daily sync orchestrator
│   ├── validate_catalog_structure.py
│   └── validate_catalog_schemas.py
└── servers/                        # Auto-synced MCP servers (deterministic paths)
    ├── <owner>-<repo>/             # Group directory (e.g., modelcontextprotocol-servers)
    │   ├── index.json              # Group-level manifest list
    │   ├── <repo>__./              # Root server variant
    │   │   ├── manifest.json       # MCP server manifest
    │   │   ├── provenance.json     # Source + harvest metadata
    │   │   └── index.json          # Variant-level index
    │   └── <repo>__<subpath>/      # Nested server variant (e.g., servers__src__filesystem)
    │       ├── manifest.json
    │       ├── provenance.json
    │       └── index.json
    └── ...
```

### Structure Details

- **`index.json`**: Deterministic catalog with:
  - `items[]`: Full audit trail (active + deprecated servers)
  - `manifests[]`: **Active-only**, **relative paths** for Matrix Hub ingestion
- **`servers/<owner>-<repo>/`**: Stable group directory using slugified owner-repo
- **`servers/<owner>-<repo>/<repo>__<subpath>/`**: Deterministic variant directory
  - Root servers: `<repo>__.` (e.g., `servers__.`)
  - Nested servers: `<repo>__src__filesystem` (slashes become `__`)
- **`schema/`**: JSON Schema definitions for validation
- **`scripts/`**: Automation and validation tooling

## How It Works

### Daily Automated Sync

Every day at 02:15 UTC, a GitHub Action:

1. Runs `mcp_ingest.harvest_source()` against `modelcontextprotocol/servers`
2. Discovers base repo + README-linked repos
3. Generates deterministic folder structure: `servers/<owner>-<repo>/<repo>__<subpath>/`
4. Deduplicates by `(repo, path, transport)` — **stable, location-based identity**
5. Detects manifest ID collisions (prevents DB corruption)
6. Deprecates missing servers (preserves history, not deleted)
7. Rebuilds `index.json` with:
   - `items[]`: All servers (active + deprecated)
   - `manifests[]`: Active-only relative paths
8. Validates all manifests against schema
9. Opens PR if changes detected

### Index Format

Fetch the catalog:

```bash
curl -s https://raw.githubusercontent.com/agent-matrix/catalog/main/index.json
```

Example structure:

```json
{
  "generated_at": "2025-12-28T02:15:00Z",
  "source": {
    "harvester": "mcp_ingest.harvest_source",
    "root_repo": "https://github.com/modelcontextprotocol/servers"
  },
  "counts": {
    "total_items": 150,
    "active_manifests": 145,
    "deprecated_added_this_run": 0
  },
  "items": [
    {
      "type": "mcp_server",
      "id": "filesystem",
      "name": "Filesystem MCP Server",
      "transport": "STDIO",
      "status": "active",
      "manifest_path": "servers/modelcontextprotocol-servers/servers__src__filesystem/manifest.json",
      "repo": "https://github.com/modelcontextprotocol/servers",
      "subpath": "src/filesystem"
    },
    {
      "type": "mcp_server",
      "id": "old-server",
      "name": "Deprecated Server",
      "transport": "SSE",
      "status": "deprecated",
      "manifest_path": "servers/example-owner/example__./manifest.json",
      "repo": "https://github.com/example/owner",
      "subpath": ""
    }
  ],
  "manifests": [
    "servers/modelcontextprotocol-servers/servers__src__filesystem/manifest.json"
  ]
}
```

**Key Points**:
- `manifests[]`: **Active-only**, **relative paths** — safe for Matrix Hub ingestion
- `items[]`: Full audit trail including deprecated servers with `status` field
- Counts track total items, active manifests, and newly deprecated in this run

### Manifest Format

Each manifest follows the `mcp_ingest` standard with `type: "mcp_server"`:

```json
{
  "type": "mcp_server",
  "id": "filesystem",
  "name": "Filesystem MCP Server",
  "description": "Access local filesystem",
  "mcp_registration": {
    "server": {
      "transport": "STDIO",
      "exec": {
        "cmd": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path"]
      }
    }
  },
  "provenance": {
    "repo_url": "https://github.com/modelcontextprotocol/servers",
    "subpath": "src/filesystem",
    "harvested_at": "2025-12-28T02:15:00Z"
  }
}
```

## Validation & CI

### Automated Checks

All PRs are validated via GitHub Actions:

- **Structure validation**: Ensures manifests have required fields
- **Schema validation**: All manifests conform to `mcp_server.schema.json`
- **Linting**: Scripts are checked with `ruff`

### Local Development

Run sync and validation locally:

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install jsonschema ruff

# Install mcp_ingest (assumes sibling directory)
pip install -e ../mcp_ingest

# Run sync
python scripts/sync_mcp_servers.py \
  --source-repo "https://github.com/modelcontextprotocol/servers" \
  --catalog-root "." \
  --servers-dir "servers" \
  --index-file "index.json"

# Validate
python scripts/validate_catalog_structure.py
python scripts/validate_catalog_schemas.py
```

## How to create new servers ➡️
You can create a new simply  server by using our templates ready to use.

[https://github.com/agent-matrix/mcp-template](https://github.com/agent-matrix/mcp-template)


## How to Add Your Server (The Easy Way) ✨

We've created a fully automated, bot-powered submission process that doesn't require you to fork the repository or use Git. All you need to do is fill out a form!

1. **Prepare Your Information**: Before you start, make sure you have the following details handy:

   * A unique **ID** and **Folder Slug** for your server (e.g., `my-awesome-agent`).

   * The **Server Name** and **Version** number.

   * The **Transport** type:

     * `SSE`: For servers that are hosted online and accessible via a URL.

     * `STDIO`: For servers that are run from a Git repository.

   * A **URL** (if using SSE).

   * A **Git Repo URL** and **Ref** (tag or commit hash) (if using STDIO).

   * A short **Summary** and a longer **Description** for your server.

2. **Open a Submission Issue**: Click the link below to open our "Add MCP Server" issue form. It will guide you through providing all the necessary information.

   ➡️ [**Click Here to Add Your MCP Server**](https://www.google.com/search?q=https://github.com/YOUR_USERNAME/YOUR_REPOSITORY/issues/new%3Fassignees%3D%26labels%3Dadd-server%26template%3Dadd_mcp_server.yml%26title%3D%255BServer%255D%253A%2BADD_YOUR_SERVER_NAME_HERE)
   *(Note: Please replace YOUR_USERNAME/YOUR_REPOSITORY in the link above with the actual path to your repository if you are hosting this project.)*

3. **Submit the Form**: Once you've filled out all the fields, just click "Submit new issue."

### What Happens Next? ⚙️

Once you submit the issue, our friendly GitHub bot takes over:

1. **Validation**: The bot reads your submission and validates the information provided.

2. **PR Creation**: It automatically creates a new branch, generates the required `manifest.json` and `index.json` files, and opens a Pull Request (PR) on your behalf. A comment will be posted on your issue with a link to the new PR.

3. **Automated Checks**: The PR triggers another workflow that validates the JSON schema and structure of the new files to ensure they meet the catalog's standards.

4. **Review & Merge**: A project maintainer will review the automated PR. If all checks pass and the submission looks good, they will merge it.

5. **Done!** 🎉 Your server is now officially part of the Matrix Hub catalog and will appear on the website.

## Advanced Method: Submitting a Manual Pull Request

If you're comfortable with Git and prefer to submit your entry manually, you can follow these steps.

1. **Fork & Clone**: Fork this repository and clone it to your local machine.

2. **Create a New Branch**: `git checkout -b add-server/your-server-name`

3. **Create a Directory**: Create a new directory for your server under the `servers/` folder. The name should be your unique server slug.




## Matrix Hub Integration

This catalog serves as the **source of truth** for Matrix Hub's MCP server database.

### Ingestion Flow

1. **Catalog sync** (daily): Auto-updates catalog via PR
2. **Matrix Hub polling**: Reads `index.json` on schedule or webhook
3. **DB population**: Upserts servers using manifest data
4. **User discovery**: Matrix Hub UI surfaces servers for installation

### Manifest → Database Mapping

Each manifest provides DB-ready data:

- **Identity**: `id`, `name`, `version`
- **Connection**: `mcp_registration.server.{transport, url, exec}`
- **Metadata**: `description`, `tags`, `license`, `homepage`
- **Provenance**: `repo_url`, `subpath`, `ref`, `harvested_at`

### For Matrix Hub Developers

**Recommended ingestion strategy** (use `manifests[]` for active-only):

```python
import requests

# Fetch catalog
catalog = requests.get(
    "https://raw.githubusercontent.com/agent-matrix/catalog/main/index.json"
).json()

# Ingest ACTIVE-ONLY servers using manifests[] (relative paths)
base_url = "https://raw.githubusercontent.com/agent-matrix/catalog/main"

for manifest_path in catalog["manifests"]:
    manifest_url = f"{base_url}/{manifest_path}"
    manifest = requests.get(manifest_url).json()

    # Upsert to database
    upsert_server(
        server_id=manifest["id"],
        name=manifest["name"],
        transport=manifest["mcp_registration"]["server"]["transport"],
        status="active",  # All items in manifests[] are active
        lifecycle=manifest.get("lifecycle"),
        provenance=manifest.get("provenance"),
        # ... other fields
    )
```

**Alternative: Use `items[]` for full control** (includes deprecated):

```python
# For audit trail or deprecated server management
for item in catalog["items"]:
    if item["status"] == "active":
        # Process active servers
        manifest_url = f"{base_url}/{item['manifest_path']}"
        manifest = requests.get(manifest_url).json()
        upsert_server(manifest, status="active")
    elif item["status"] == "deprecated":
        # Mark as deprecated in DB (don't delete, preserve history)
        update_server_status(item["id"], "deprecated")
```

**Key principles**:
- **Use `manifests[]`**: Simple, active-only ingestion (recommended)
- **Use `items[]`**: Full audit trail with status filtering
- **Never delete**: Mark as deprecated to preserve history
- **Filter by status**: UI shows active by default, deprecated with warning

## Working with mcp_ingest

This catalog uses **mcp_ingest** for harvesting and manifest generation.

### For Server Authors

Create manifests for your servers:

```bash
pip install mcp-ingest

# Generate manifest from local server
mcp-ingest pack ./path/to/server --out ./dist
```

### For Catalog Maintainers

The sync script already uses `mcp_ingest.harvest_source()` to discover servers automatically.

See [mcp_ingest documentation](https://github.com/agent-matrix/mcp_ingest) for details.

## Credits

* **Lead developer:** *Ruslan Magana Vsevolodovna* — [https://ruslanmv.com](https://ruslanmv.com)
* **Model Context Protocol** community for the protocol and reference servers.
* Maintainers and contributors across the Agent-Matrix ecosystem.

“Powered by `agent-generator` and `mcp-ingest`.”

---

## License

This catalog is released under the **Apache License 2.0**.
See [LICENSE](./LICENSE) for details.


