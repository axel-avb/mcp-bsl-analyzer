"""BSL MCP server entrypoint (variant D).

Reuses onec-hbk-bsl's FastMCP app factory and registers only the two tools upstream
lacks (``complexity``, ``workspace_diagnostics``), then serves Streamable HTTP.
No fork, no proxy, one process.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("BSL_MCP_LOG_LEVEL", "INFO").upper(),
        format="[bsl-mcp] %(levelname)s %(name)s: %(message)s",
    )


def _bootstrap_env() -> tuple[str, str]:
    """Resolve workspace + index location BEFORE importing onec-hbk-bsl's server."""
    workspace = str(Path(os.environ.get("WORKSPACE_ROOT") or os.getcwd()).resolve())
    os.environ["WORKSPACE_ROOT"] = workspace

    from onec_hbk_bsl.cli.config import load_config, resolve_config
    from onec_hbk_bsl.indexer.db_path import resolve_index_db_path

    index_mode = resolve_config(load_config(workspace)).index_mode
    os.environ["BSL_INDEX_MODE"] = index_mode
    db_path = ":memory:" if index_mode == "off" else resolve_index_db_path(workspace)
    os.environ.setdefault("INDEX_DB_PATH", db_path)
    return workspace, db_path


def _autoindex(workspace: str, db_path: str) -> None:
    # Match upstream ``mcp`` command: populate an empty index in the background.
    try:
        from onec_hbk_bsl.__main__ import _autoindex_if_empty

        _autoindex_if_empty(workspace, db_path)
    except Exception:  # pragma: no cover - upstream internal may move
        logging.getLogger(__name__).warning(
            "auto-index bootstrap unavailable; index tools may return empty until indexed",
            exc_info=True,
        )


def main() -> None:
    _setup_logging()
    workspace, db_path = _bootstrap_env()

    from onec_hbk_bsl.mcp_bridge.server import create_mcp_app

    from bsl_mcp.tools import register_tools

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8051"))

    _autoindex(workspace, db_path)

    app = create_mcp_app(host=host, port=port)
    register_tools(app)

    logging.getLogger(__name__).info(
        "BSL MCP server: workspace=%s index_mode=%s db=%s http=%s:%d",
        workspace,
        os.environ.get("BSL_INDEX_MODE"),
        os.environ.get("INDEX_DB_PATH"),
        host,
        port,
    )
    app.run(transport="streamable-http")


if __name__ == "__main__":
    main()
