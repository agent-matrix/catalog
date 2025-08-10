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

The **Agent-Matrix Catalog** is a public, versioned registry of **MCP servers** (agents/tools) used by MatrixHub.  
It publishes one canonical `index.json` with **absolute RAW URLs** to each server’s `manifest.json`, plus per-server folders containing a `manifest.json` and a per-folder `index.json`.

- 🔗 **Top-level RAW index (main branch):**

This repo is designed for **high-volume**, **append-only** publishing: add new servers via Pull Request; CI refreshes the top index.


## Repository layout

```
.
├─ index.json                 # Top-level catalog of all manifests (absolute RAW URLs)
└─ servers/
├─ <server-folder-1>/
│  ├─ manifest.json       # MCP server manifest
│  └─ index.json          # Per-folder index (usually \["manifest.json"])
├─ <server-folder-2>/
│  ├─ manifest.json
│  └─ index.json
└─ ...
```

- **`index.json`** at the repo root contains **absolute** raw URLs to every manifest in `servers/**/manifest.json`.
- Each **`servers/<folder>/index.json`** lists the manifest(s) in that folder, typically:
  ```json
  { "manifests": ["manifest.json"] }

## How the index works

Fetch one file:

```bash
curl -s https://raw.githubusercontent.com/agent-matrix/catalog/refs/heads/main/index.json
```

You’ll get:

```json
{
  "manifests": [
    "https://raw.githubusercontent.com/agent-matrix/catalog/refs/heads/main/servers/<folder-a>/manifest.json",
    "https://raw.githubusercontent.com/agent-matrix/catalog/refs/heads/main/servers/<folder-b>/manifest.json"
  ]
}
```

Each URL is a complete MCP manifest and can be installed independently.

---


## Add a new server (Fork → PR)

**Standard GitHub flow**: fork, branch, commit, PR.

1. **Create a folder** under `servers/` with a concise slug:

```
servers/my-awesome-mcp/
```

2. **Add your manifest** to `servers/my-awesome-mcp/manifest.json`.
   Use the richer schema (example below).

3. **Add the per-folder index** `servers/my-awesome-mcp/index.json`:

```json
{ "manifests": ["manifest.json"] }
```

4. **Open a Pull Request**.
   A maintainer will review and merge. CI will update the top-level catalog index.

### Full manifest example (complete schema, SSE)

> You can adapt fields (IDs, names, URLs). This example follows the enriched pattern (with `schema_version`, `homepage`, `license`, `artifacts`, and a scaffolded `mcp_registration.tool`).

```json
{
  "schema_version": 1,
  "type": "mcp_server",
  "id": "repo-agent",
  "name": "Repo",
  "version": "0.1.0",

  "summary": "",
  "description": "",
  "homepage": "https://github.com/13rac1/videocapture-mcp",
  "license": "",

  "artifacts": [
    {
      "kind": "git",
      "spec": {
        "repo": "https://github.com/13rac1/videocapture-mcp.git",
        "ref": "f01c45036d626b71f29b530046ada52ce5e88e9a"
      }
    }
  ],

  "mcp_registration": {
    "resources": [],
    "prompts": [],
    "server": {
      "name": "repo",
      "description": "",
      "transport": "SSE",
      "url": "http://127.0.0.1:6288/sse",
      "associated_tools": [],
      "associated_resources": [],
      "associated_prompts": []
    },
    "tool": {
      "id": "repo-agent-tool",
      "name": "Repo",
      "description": "",
      "integration_type": "MCP",
      "url": "http://127.0.0.1:6288/sse",
      "input_schema": {
        "type": "object",
        "properties": {}
      }
    }
  }
}
```

**Notes**

* `schema_version`: recommended (currently `1`).
* `type/id/name/version`: required by consumers.
* `homepage`/`license`: recommended for provenance.
* `artifacts`: recommended; include a `git` spec with a stable `ref` (tag or commit SHA).
* `mcp_registration.server.url`: SSE endpoints typically end with `/sse`.
* `tool` block is optional but recommended; use an empty input schema if unknown.

---

## Generate/validate manifests with `mcp-ingest`

We recommend the **mcp-ingest** SDK + CLI to produce consistent manifests and indexes.

### Install

```bash
pip install mcp-ingest
```

### Describe/pack a local server (offline)

```bash
# Emits manifest.json + index.json
mcp-ingest pack ./path/to/server --out ./dist
```


## Credits

* **Lead developer:** *Ruslan Magana Vsevolodovna* — [https://ruslanmv.com](https://ruslanmv.com)
* **Model Context Protocol** community for the protocol and reference servers.
* Maintainers and contributors across the Agent-Matrix ecosystem.

“Powered by `agent-generator` and `mcp-ingest`.”

---

## License

This catalog is released under the **Apache License 2.0**.
See [LICENSE](./LICENSE) for details.


