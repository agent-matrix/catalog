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


The goal is to create a rich ecosystem where developers can easily find servers to integrate into their projects and contributors can showcase their work.

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


