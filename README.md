# BSL MCP Analyzer

**English** · [Русский](README.ru.md)

MCP server for analyzing 1C/BSL code: project-wide diagnostics and per-method
cyclomatic/cognitive complexity with a ranked refactor triage. Built on the pure-Python
[`onec-hbk-bsl`](https://github.com/mussolene/1c_hbk_bsl) engine — **no Java, no LSP bridge**.
Served over Streamable HTTP behind nginx with bearer-token auth, one service per project.

## Why

`onec-hbk-bsl` already ships a full BSL analyzer, a formatter, an index, and its own MCP
server. This project reuses all of it and adds the pieces that were missing for day-to-day
work on large 1C configurations:

- **`complexity`** — raw cyclomatic + cognitive complexity for every method
  (upstream exposes these only as threshold warnings with no numbers).
- **`module_health`** — complexity merged with security/performance/SQL diagnostics,
  attributed per method and ranked by refactor priority ("what to fix first").
- **`workspace_diagnostics`** — whole-project lint with aggregation by rule/severity/file.

Plus small-model-friendly titles and descriptions for all 25 tools, and a ready Docker
Compose + nginx deployment.

## Features

- **Diagnostics**: 180+ BSL/1C rules (onec-hbk-bsl registry), inline `noqa`/`bsl-disable`
  suppressions, `select`/`ignore`, whole-project aggregation.
- **Complexity**: per-method McCabe and cognitive metrics, configurable thresholds
  (defaults 20 / 15), over-threshold flags.
- **Refactor triage**: `module_health` scores security ×10, performance/sql ×4 plus
  complexity overage, and returns a sorted `top_targets` list.
- **Full navigation toolbox** inherited from onec-hbk-bsl: symbols, definitions,
  references, callers/callees, hover, search, rename, format, fix, 1C metadata.
- **Multi-project**: one container per project, `1:1` host↔container path mounts.
- **Agent-friendly**: every tool has an explicit what/when/args/returns/example block.

## Architecture

```
MCP agents ──HTTP──> nginx (/bsl/<proj>/mcp, Bearer) ──> bsl-<proj>:8051/mcp
                                                          └── <project> (mounted 1:1)
                                                             onec-hbk-bsl engine (Python)
```

```
src/bsl_mcp/entrypoint.py            bootstrap env → onec-hbk-bsl FastMCP app → +3 tools → HTTP
src/bsl_mcp/lsp_facade.py            single adapter to onec-hbk-bsl internals
src/bsl_mcp/tool_docs.py             titles/descriptions/instructions for all tools
src/bsl_mcp/tools/complexity.py      complexity tool
src/bsl_mcp/tools/module_health.py   module_health tool
src/bsl_mcp/tools/workspace_diagnostics.py  workspace_diagnostics tool
docker-compose.yml                   bsl-<proj> services + nginx
nginx/templates/default.conf.template  routing + bearer + SSE-friendly proxy
```

## Requirements

- Linux host with Docker Engine 24+ and Compose v2.
- 2 GB RAM / ~2 CPU per project (indexing large configurations is CPU-disk heavy).
- A free port for nginx (default `8080`).

## Quick start

```bash
cp .env.example .env
# edit .env: BSL_MCP_TOKEN and PROJ_A_PATH/PROJ_B_PATH/PROJ_C_PATH
docker compose up -d --build
docker compose ps
```

Verify (expect `200`; without the header — `401`):

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/bsl/proj-a/mcp \
  -X POST -H 'Authorization: Bearer <TOKEN>' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

### Connect an agent

opencode (`opencode.json`):

```json
{
  "mcp": {
    "bsl-trade": {
      "type": "remote",
      "url": "http://HOST:8080/bsl/proj-a/mcp",
      "headers": { "Authorization": "Bearer <TOKEN>" },
      "enabled": true
    }
  }
}
```

Cursor / Claude and other `mcpServers` clients:

```json
{
  "mcpServers": {
    "bsl-trade": {
      "type": "streamable-http",
      "url": "http://HOST:8080/bsl/proj-a/mcp",
      "headers": { "Authorization": "Bearer <TOKEN>" }
    }
  }
}
```

## Tools

Added by this project:

| Tool | Purpose |
|---|---|
| `complexity(file)` | Cyclomatic + cognitive complexity per method, thresholds and flags |
| `module_health(file)` | Complexity + security/performance/SQL diagnostics, ranked `top_targets` |
| `workspace_diagnostics(path, min_severity, select, ignore, top_n)` | Project-wide lint aggregated by rule/severity/file |

Inherited from onec-hbk-bsl (22 tools): `bsl_status`, `bsl_find_symbol`,
`bsl_file_symbols`, `bsl_definition`, `bsl_hover`, `bsl_callers`, `bsl_callees`,
`bsl_references`, `bsl_read_file`, `bsl_search`, `bsl_diagnostics`, `bsl_check_file`,
`bsl_list_rules`, `bsl_index_file`, `bsl_format`, `bsl_rename`, `bsl_fix`,
`bsl_workspace_scan`, `bsl_meta_object`, `bsl_meta_collection`, `bsl_meta_index`,
`bsl_contract_version`.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `BSL_MCP_TOKEN` | yes | Bearer token agents must send |
| `NGINX_PORT` | no | Host port for nginx (default `8080`) |
| `PROJ_A_PATH`, `PROJ_B_PATH`, `PROJ_C_PATH` | yes | Absolute host paths of 1C projects (mounted 1:1) |

Service name must be `bsl-<proj>` for `/bsl/<proj>/...` routing. Index settings
(`index-mode`, `select`/`ignore`, `exclude`) come from `onec-hbk-bsl.toml` in the
project root.

## Documentation

- [QUICKSTART.md](QUICKSTART.md) — full deployment guide (Russian)
- [docs/tls-letsencrypt.md](docs/tls-letsencrypt.md) — HTTPS via Let's Encrypt, step by step (Russian)
- [docs/bsl-lsp-go-overview.md](docs/bsl-lsp-go-overview.md) — analysis of the previous Go bridge (Russian)

## Credits

- Analysis engine, parser, index and base MCP surface:
  [`onec-hbk-bsl`](https://github.com/mussolene/1c_hbk_bsl) (MIT).
- Diagnostic rule corpus adapted from
  [`BSL Language Server`](https://github.com/1c-syntax/bsl-language-server).
