# Catalog Dashboard

A live dashboard for the **MatrixHub catalog** — counts of indexed MCP
servers, agents, and tools, recent additions, and the highest-quality picks.

## Where to view it

- **Live:** <https://agent-matrix.github.io/catalog/>
- **Source:** `docs/index.html` in this repo

## How it works

The page is a single static HTML file. It fetches counts from the public
MatrixHub API on load and refreshes every 60 seconds:

- `GET https://api.matrixhub.io/catalog?type=mcp_server&limit=1` — server count
- `GET https://api.matrixhub.io/catalog?type=agent&limit=1` — agent count
- `GET https://api.matrixhub.io/catalog?type=tool&limit=1` — tool count
- `GET https://api.matrixhub.io/catalog?type=mcp_server&limit=10&sort=updated_at` — recent additions
- `GET https://api.matrixhub.io/catalog?type=mcp_server&limit=10&sort=quality` — top picks

If the API is unreachable, the dashboard degrades gracefully and displays `—`
in place of metrics.

