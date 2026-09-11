"""``workspace_diagnostics`` MCP tool: whole-project BSL diagnostics, aggregated.

onec-hbk-bsl ships ``bsl_diagnostics`` / ``bsl_check_file`` for a single file. This tool
adds the workspace-wide view: walk the tree, run the diagnostic engine per file, and
return counts + rankings instead of a raw per-file dump.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from bsl_mcp import lsp_facade as facade


def register_workspace_diagnostics_tool(app: Any) -> None:
    @app.tool(
        description=(
            "Run BSL diagnostics across a whole directory/project and return an aggregated "
            "report: totals by severity and rule, the worst files, and optional raw items. "
            "Respects onec-hbk-bsl.toml (exclude, select/ignore) and BSL_SELECT/BSL_IGNORE."
        )
    )
    def workspace_diagnostics(
        path: Annotated[str, "Directory to scan (absolute or workspace-relative); default '.'"] = ".",
        select: Annotated[str | None, "Comma-separated rules to include (BSL### or BSLLS name)"] = None,
        ignore: Annotated[str | None, "Comma-separated rules to skip"] = None,
        min_severity: Annotated[str, "ERROR | WARNING | INFORMATION | HINT; default WARNING"] = "WARNING",
        top_n: Annotated[int, "How many top rules/files to return (default 20)"] = 20,
        max_files: Annotated[int, "Safety cap on scanned .bsl files (default 2000)"] = 2000,
        include_items: Annotated[bool, "Include capped raw diagnostic items (default False)"] = False,
    ) -> dict:
        root = facade.workspace_root()
        try:
            scan_root = facade.resolve_path(path, base=root)
        except facade.PathDenied as exc:
            return {"error": str(exc)}

        if not scan_root.is_dir():
            return {"error": f"not a directory: {path}"}

        min_rank = facade.severity_rank(min_severity)
        opts = facade.load_engine_options(root, select=select, ignore=ignore)

        by_rule: Counter[str] = Counter()
        by_severity: Counter[str] = Counter()
        by_file: Counter[str] = Counter()
        items: list[dict[str, Any]] = []
        scanned = 0
        files_with_issues = 0

        for f in facade.iter_bsl_files(scan_root, opts, max_files=max_files):
            scanned += 1
            diags = facade.file_diagnostics(f, opts)
            if not diags:
                continue
            files_with_issues += 1
            for d in diags:
                if facade.severity_rank(d["severity"]) > min_rank:
                    continue
                by_rule[d["code"]] += 1
                by_severity[d["severity"]] += 1
                by_file[d["file"]] += 1
                if include_items:
                    items.append(d)

        total = sum(by_rule.values())
        top_rules = [
            {"code": code, "rule_name": facade.rule_name(code), "count": count}
            for code, count in by_rule.most_common(top_n)
        ]
        top_files = [
            {"file": file, "count": count} for file, count in by_file.most_common(top_n)
        ]

        return {
            "root": str(scan_root),
            "files_scanned": scanned,
            "files_with_issues": files_with_issues,
            "total": total,
            "min_severity": min_severity.upper(),
            "by_severity": dict(by_severity),
            "top_rules": top_rules,
            "top_files": top_files,
            "items": items[:top_n] if include_items else None,
        }
