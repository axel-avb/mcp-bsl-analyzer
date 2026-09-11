"""``complexity`` MCP tool: per-method cyclomatic + cognitive complexity.

onec-hbk-bsl exposes complexity only as threshold diagnostics (BSL011/BSL019, with an
empty message) and as LSP code lens. This tool surfaces the raw numbers per method.
"""

from __future__ import annotations

from typing import Annotated, Any

from bsl_mcp import lsp_facade as facade


def register_complexity_tool(app: Any) -> None:
    @app.tool(
        description=(
            "Per-method cyclomatic (McCabe) and cognitive complexity for a BSL/1C module, "
            "computed by the onec-hbk-bsl engine. Use to decide what to refactor and to "
            "check a changed method stays within budget. Defaults: cognitive > 15 and "
            "cyclomatic > 20 are flagged; thresholds come from onec-hbk-bsl.toml."
        )
    )
    def complexity(
        file: Annotated[str, "BSL module path (absolute or workspace-relative)"],
    ) -> dict:
        try:
            path = facade.resolve_path(file)
        except facade.PathDenied as exc:
            return {"error": str(exc)}

        if not path.is_file():
            return {"error": f"not a file: {file}"}

        opts = facade.load_engine_options(facade.workspace_root())
        rows = facade.file_complexity(path, opts)
        data = [r.to_dict(opts.cognitive_threshold, opts.mccabe_threshold) for r in rows]

        flagged = [r for r in data if r["over_cognitive"] or r["over_mccabe"]]
        return {
            "file": str(path),
            "thresholds": {
                "cognitive": opts.cognitive_threshold,
                "mccabe": opts.mccabe_threshold,
            },
            "method_count": len(data),
            "flagged_count": len(flagged),
            "max_cognitive": max((r["cognitive"] for r in data), default=0),
            "max_mccabe": max((r["mccabe"] for r in data), default=0),
            "methods": data,
        }
