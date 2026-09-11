"""``module_health`` MCP tool: per-method complexity + quality diagnostics, ranked.

Combo over onec-hbk-bsl: complexity metrics (code lens source) plus security /
performance / SQL query diagnostics, attributed to the enclosing method and scored so
an agent sees "what to refactor first" in one call.
"""

from __future__ import annotations

from typing import Annotated, Any

from bsl_mcp import lsp_facade as facade

_WEIGHTS = {"security": 10, "performance": 4, "sql": 4}


def _enclosing(rows: list[facade.ComplexityRow], line: int) -> int | None:
    """Index of the method whose declaration is the last one <= *line*, else None."""
    found: int | None = None
    for i, row in enumerate(rows):
        if row.line <= line:
            found = i
        else:
            break
    return found


def _score(entry: dict[str, Any]) -> int:
    score = sum(_WEIGHTS[cat] * entry[cat] for cat in _WEIGHTS)
    if entry["over_cognitive"]:
        score += entry["cognitive"]
    if entry["over_mccabe"]:
        score += entry["mccabe"]
    return score


def register_module_health_tool(app: Any) -> None:
    @app.tool(
        description=(
            "Combined per-module health report for a BSL/1C module: cyclomatic + cognitive "
            "complexity merged with security/performance/SQL diagnostics, attributed per "
            "method and ranked by refactor priority. Use to triage what to fix first; for "
            "raw complexity use `complexity`, for one project-wide view use "
            "`workspace_diagnostics`."
        )
    )
    def module_health(
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
        diags = facade.file_diagnostics(path, opts)

        entries: list[dict[str, Any]] = [
            {
                "name": r.name,
                "kind": r.kind,
                "line": r.line,
                "cognitive": r.cognitive,
                "mccabe": r.mccabe,
                "over_cognitive": r.cognitive > opts.cognitive_threshold,
                "over_mccabe": r.mccabe > opts.mccabe_threshold,
                "security": 0,
                "performance": 0,
                "sql": 0,
            }
            for r in rows
        ]

        module_level = {"security": 0, "performance": 0, "sql": 0}
        totals = {"security": 0, "performance": 0, "sql": 0}
        for d in diags:
            cats = facade.rule_quality_categories(d["code"])
            if not cats:
                continue
            target = _enclosing(rows, d["line"])
            for cat in cats:
                totals[cat] += 1
                if target is None:
                    module_level[cat] += 1
                else:
                    entries[target][cat] += 1

        for e in entries:
            e["score"] = _score(e)

        ranked = sorted(
            (e for e in entries if e["score"] > 0),
            key=lambda e: (-e["score"], e["line"]),
        )
        flagged = sum(1 for e in entries if e["over_cognitive"] or e["over_mccabe"])

        return {
            "file": str(path),
            "thresholds": {
                "cognitive": opts.cognitive_threshold,
                "mccabe": opts.mccabe_threshold,
            },
            "weights": {**_WEIGHTS, "complexity_overage": "value added when over threshold"},
            "method_count": len(entries),
            "flagged_count": flagged,
            "issue_totals": totals,
            "module_level_issues": module_level,
            "top_targets": ranked,
            "methods": entries,
        }
