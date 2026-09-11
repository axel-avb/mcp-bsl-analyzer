"""MCP tool registration for the BSL server."""

from __future__ import annotations

from typing import Any


def register_tools(app: Any) -> None:
    from bsl_mcp.tool_docs import apply as apply_tool_docs
    from bsl_mcp.tools.complexity import register_complexity_tool
    from bsl_mcp.tools.module_health import register_module_health_tool
    from bsl_mcp.tools.workspace_diagnostics import register_workspace_diagnostics_tool

    register_complexity_tool(app)
    register_module_health_tool(app)
    register_workspace_diagnostics_tool(app)

    # Overwrite all tool texts (ours + upstream) with small-model-friendly docs.
    apply_tool_docs(app)
