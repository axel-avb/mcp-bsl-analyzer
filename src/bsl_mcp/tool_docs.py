"""Rich tool descriptions/titles tuned for small (3B-7B) models.

After ``create_mcp_app()`` registers the upstream onec-hbk-bsl tools, :func:`apply`
overwrites the human-facing ``title`` and ``description`` of every tool with an
explicit what/when/how/example block. Behaviour, names and parameters are untouched;
only the text a model reads in ``tools/list`` changes.
"""

from __future__ import annotations

from typing import Any

# Top-level guidance returned in `initialize` (models read this before any tool).
INSTRUCTIONS = """
BSL / 1C static analysis server. Follow this workflow.

START: call bsl_status once to confirm the index is ready (ready=true).

FIND code:
- know the name -> bsl_find_symbol (fuzzy=true for partial names)
- know only text/regex -> bsl_search
- list a known file's methods -> bsl_file_symbols

READ code:
- bsl_read_file with start_line/end_line (do NOT read whole big files)

UNDERSTAND a method:
- signature/docs -> bsl_hover
- who calls it  -> bsl_callers
- what it calls -> bsl_callees
- everything    -> bsl_references

CHECK quality:
- one file, all rules         -> bsl_diagnostics
- one file, ranked "fix first"-> module_health
- complexity only             -> complexity
- whole project (aggregated)  -> workspace_diagnostics

AFTER editing a file: call bsl_index_file so navigation sees the change
(the server does not watch the filesystem).

RULES:
- Paths are absolute or workspace-relative (e.g. "Module.bsl").
- Write tools (bsl_format, bsl_fix, bsl_rename) default to dry-run; pass
  write/apply=true only when the user asked to change files.
- Report diagnostics to the user; do not silently ignore them.
""".strip()


# name -> (title, description)
TOOL_DOCS: dict[str, tuple[str, str]] = {
    "bsl_status": (
        "Index status (call first)",
        """WHAT: Health/state of the workspace symbol index (how many symbols/files are indexed).

USE WHEN:
- First call in a session, before searching/navigation, to confirm the index is ready.
- Results of bsl_find_symbol/bsl_definition/bsl_callers look empty or stale.

Args: workspace_root (string, optional) — project root, defaults to the server workspace.

Returns: {ready (bool), symbol_count, file_count, call_count, indexed_at, workspace_root, db_path}.
If ready=false or symbol_count=0, the index is still building: wait and call again.

Example: bsl_status()""",
    ),
    "bsl_find_symbol": (
        "Find symbol by name",
        """WHAT: Search the index for procedures/functions/variables by name; returns where they are.

USE WHEN: you know (part of) a symbol name and need its file and line before reading code.
DO NOT USE FOR: text/regex search (use bsl_search); listing all symbols of one known file
(use bsl_file_symbols); finding who calls something (use bsl_callers).

Args:
- name (string, required): symbol name, case-insensitive. For partial names set fuzzy=true.
- fuzzy (bool, default false): true = prefix/substring match, false = exact name.
- file_filter (string, optional): keep only hits whose file path contains this text.
- limit (int, default 20): max results.
- workspace_root (string, optional): project root.

Returns: {count, symbols:[{name, kind, file_path, line, signature, is_export, doc_comment}]}
where line is 1-based.

Example: bsl_find_symbol(name="ПодставитьПараметрыВСтроку", fuzzy=true, limit=5)""",
    ),
    "bsl_file_symbols": (
        "Outline one file",
        """WHAT: List every symbol (procedure/function/variable) defined in ONE file, ordered by line.

USE WHEN: you have a file path and want a quick table of contents of the module.
DO NOT USE FOR: searching by name across the project (use bsl_find_symbol).

Args:
- file_path (string, required): absolute or workspace-relative path to the .bsl file.
- workspace_root (string, optional): project root.

Returns: {file_path, count, symbols:[{name, kind, line, end_line, signature, is_export}]}.

Example: bsl_file_symbols(file_path="src/cf/CommonModules/ОбщегоНазначения/Ext/Module.bsl")""",
    ),
    "bsl_definition": (
        "Go to definition (by name)",
        """WHAT: Find where a symbol with the given name is DEFINED (declaration site).

USE WHEN: you have a symbol name and only need its definition location(s).
DO NOT USE FOR: all usages (use bsl_references); signature/doc (use bsl_hover).

Args:
- symbol_name (string, required): exact name to look up.
- file_filter (string, optional): restrict to files whose path contains this text.
- workspace_root (string, optional): project root.

Returns: {symbol_name, count, definitions:[{file_path, line, character, signature, is_export, doc_comment}]}.

Example: bsl_definition(symbol_name="СтрРазделить")""",
    ),
    "bsl_hover": (
        "Signature and docs",
        """WHAT: Signature + doc comment for a symbol, or platform API help for built-in 1C names.

USE WHEN: you need parameters, return value, or the doc comment of a method/function.
DO NOT USE FOR: the method body (use bsl_read_file) or call sites (use bsl_references).

Args:
- symbol_name (string, required): name to look up. Workspace symbols are searched first,
  then the built-in 1C platform API.
- workspace_root (string, optional): project root.

Returns: {found:true, source:"workspace"|"platform_api", name, kind, signature, doc_comment|description, ...}.

Example: bsl_hover(symbol_name="ЗначениеЗаполнено")""",
    ),
    "bsl_callers": (
        "Who calls this",
        """WHAT: All call sites that CALL a given procedure/function (incoming calls, tree up to depth).

USE WHEN: impact analysis — "if I change this, who breaks?", or tracing up the call chain.
DO NOT USE FOR: what the method itself calls (use bsl_callees).

Args:
- symbol_name (string, required): the called procedure/function name.
- depth (int, default 3): how many caller levels to expand.
- file_filter (string, optional): pick one definition when the same name exists in many files.
- workspace_root (string, optional): project root.

Returns: {symbol_name, definition, callers:[...]}. If the name is ambiguous across modules:
{ambiguous:true, candidates:[...]} — pass file_filter to choose.

Example: bsl_callers(symbol_name="ПровестиДокумент", depth=2)""",
    ),
    "bsl_callees": (
        "What it calls",
        """WHAT: All procedures/functions CALLED FROM a given symbol (outgoing calls).

USE WHEN: understanding what a method depends on before refactoring or testing.
DO NOT USE FOR: finding callers of a method (use bsl_callers).

Args:
- symbol_name (string, required): the procedure/function to inspect.
- depth (int, default 3): how deep to follow the chain.
- file_filter (string, optional): disambiguate same-named definitions.
- workspace_root (string, optional): project root.

Returns: {symbol_name, definition, callees:[...]} or {ambiguous:true, candidates:[...]}.

Example: bsl_callees(symbol_name="ЗаполнитьТаблицу", depth=2)""",
    ),
    "bsl_references": (
        "All references (defs + calls)",
        """WHAT: One-shot "everything about a symbol": its definition(s) AND all call sites.

USE WHEN: you want both "where is it defined" and "where is it used" in a single call.
DO NOT USE FOR: a directional tree (use bsl_callers/bsl_callees) or docs (bsl_hover).

Args:
- symbol_name (string, required): symbol to trace.
- include_definitions (bool, default true): include definition locations.
- limit (int, default 100): max call sites.
- workspace_root (string, optional): project root.

Returns: {symbol_name, definition_count, reference_count, definitions:[...], references:[...]}.

Example: bsl_references(symbol_name="СформироватьПечатнуюФорму")""",
    ),
    "bsl_read_file": (
        "Read file / code range",
        """WHAT: Read a .bsl file, or only a line range of it.

USE WHEN: you need actual code (e.g. a method body or a diagnostic context).
PREFER start_line/end_line for large files to save tokens.
DO NOT USE FOR: searching text (use bsl_search) or a module outline (use bsl_file_symbols).

Args:
- file_path (string, required): absolute or workspace-relative .bsl path.
- start_line (int, optional): first line, 1-based, inclusive.
- end_line (int, optional): last line, 1-based, inclusive.
- workspace_root (string, optional): project root.

Returns: {file_path, total_lines, start_line, end_line, content}.

Example: bsl_read_file(file_path="src/cf/.../Module.bsl", start_line=100, end_line=140)""",
    ),
    "bsl_search": (
        "Text / symbol search",
        """WHAT: Search the workspace by symbol name and/or raw text/regex across .bsl files.

USE WHEN: you do NOT know a symbol name and need to find code by text, a literal, or a pattern.
DO NOT USE FOR: exact symbol lookup (use bsl_find_symbol — it is faster and structured).

Args:
- query (string, required): symbol name or regex text.
- search_type (string, default "both"): "symbol" | "text" | "both".
- file_filter (string, optional): restrict to files whose path contains this text.
- case_sensitive (bool, default false): for text search.
- limit (int, default 20): max results per search type.
- workspace_root (string, optional): project root.

Returns: {query, search_type, symbols:[...], text_matches:[{file_path, line, text}], text_match_count}.

Example: bsl_search(query="ПолучитьОбщийМодуль", search_type="text", limit=10)""",
    ),
    "bsl_diagnostics": (
        "Lint ONE file",
        """WHAT: Run the full diagnostic engine (180+ BSL/1C rules) on ONE file.

USE WHEN: checking one module for errors, unused code, style, bugs.
DO NOT USE FOR: a whole project (use workspace_diagnostics); complexity metrics
(use complexity or module_health).
NOTE: set include_unused=true to also report unused non-export methods (needs index).

Args:
- file_path (string, required): path to the .bsl file.
- include_unused (bool, default false): append BSL-DEAD unused-symbol diagnostics.
- workspace_root (string, optional): project root.

Returns: {file_path, count, has_errors, diagnostics:[{line, character, severity, code, rule_name, message}]}.

Example: bsl_diagnostics(file_path="src/cf/.../Module.bsl")""",
    ),
    "bsl_check_file": (
        "Lint file with rule filter",
        """WHAT: Same as bsl_diagnostics but lets you pick which rules to include or skip.

USE WHEN: you need only specific checks (e.g. only security rules) or want to silence noisy ones.
DO NOT USE FOR: a plain full lint (use bsl_diagnostics) or project-wide (workspace_diagnostics).

Args:
- file_path (string, required): path to the .bsl file.
- select (string, optional): comma-separated rules to KEEP (BSL### or BSLLS names).
- ignore (string, optional): comma-separated rules to SKIP.
- include_unused (bool, default false): append unused-symbol diagnostics.
- workspace_root (string, optional): project root.

Returns: {file_path, count, has_errors, diagnostics:[...]}.

Example: bsl_check_file(file_path="Module.bsl", select="BSL012,BSL033")""",
    ),
    "bsl_list_rules": (
        "List available rules",
        """WHAT: Catalogue of the diagnostic rules (code, name, description, severity, tags).

USE WHEN: you need valid rule codes for bsl_check_file select/ignore, or to filter by tag.
DO NOT USE FOR: running checks (use bsl_diagnostics / bsl_check_file).

Args:
- tag_filter (string, optional): only rules having this tag, e.g. "security", "performance", "complexity".

Returns: {count, rules:[{code, name, description, severity, tags}]}.

Example: bsl_list_rules(tag_filter="security")""",
    ),
    "bsl_index_file": (
        "Reindex one file",
        """WHAT: Force re-index of a single file so navigation tools see recent edits.

USE WHEN: right after you edited/created a .bsl file and bsl_find_symbol/bsl_callers
still return stale results. The MCP server does NOT watch the filesystem.
DO NOT USE FOR: normal reading/linting (they already read from disk).

Args:
- file_path (string, required): path to the changed .bsl file.
- workspace_root (string, optional): project root.

Returns: {file_path, symbols_indexed, calls_indexed, error}.

Example: bsl_index_file(file_path="src/cf/.../Module.bsl")""",
    ),
    "bsl_format": (
        "Format a file",
        """WHAT: Format a BSL file (keyword casing, indentation, operator spacing).

USE WHEN: you want to normalise style of a file.
IMPORTANT: this can WRITE the file. Call with write=false first to preview the diff.

Args:
- file_path (string, required): path to the .bsl file.
- write (bool, default false): false = preview only, true = overwrite the file.
- indent_size (int, optional): spaces per indent (default from project config or 4).
- insert_spaces (bool, optional): use spaces instead of tabs.
- workspace_root (string, optional): project root.

Returns: {file_path, changed, formatted, written}.

Example (preview): bsl_format(file_path="Module.bsl")
Example (apply):   bsl_format(file_path="Module.bsl", write=true)""",
    ),
    "bsl_rename": (
        "Rename symbol (dry-run first)",
        """WHAT: Rename a symbol across the workspace with exact semantic spans.

USE WHEN: renaming a procedure/function/variable safely.
IMPORTANT: apply=true WRITES files. Always call with apply=false first, review the plan,
then apply=true.

Args:
- old_name (string, required): current symbol name.
- new_name (string, required): new valid BSL identifier.
- apply (bool, default false): false = dry-run plan, true = commit transactionally.
- workspace_root (string, optional): project root.

Returns: {dry_run, applied, ...plan details...} or a refusal reason.

Example (preview): bsl_rename(old_name="СтароеИмя", new_name="НовоеИмя")""",
    ),
    "bsl_fix": (
        "Auto-fix simple issues",
        """WHAT: Apply automatic fixes (trailing whitespace, tab indentation, missing newline at EOF).

USE WHEN: cleaning up trivial formatting defects reported by diagnostics.
IMPORTANT: write=true WRITES the file; default is a dry run.

Args:
- file_path (string, required): path to the .bsl file.
- write (bool, default false): false = dry run, true = write fixed content.
- rules (string, optional): comma-separated fixable rules (default: all fixable).
- workspace_root (string, optional): project root.

Returns: {file_path, changed, fixes_applied, fixed_rules, written}.

Example: bsl_fix(file_path="Module.bsl", write=true)""",
    ),
    "bsl_workspace_scan": (
        "Project file inventory",
        """WHAT: Walk a directory and return the list of .bsl files with quick per-file metrics.

USE WHEN: orienting in an unknown project (how many files, sizes, symbol counts).
DO NOT USE FOR: diagnostics (use workspace_diagnostics) or symbol search (bsl_find_symbol).

Args:
- directory (string, optional): directory to scan, defaults to the workspace root.
- max_files (int, default 200): cap on returned files.
- include_metrics (bool, default true): include line/symbol counts per file.
- workspace_root (string, optional): project root.

Returns: {directory, file_count, shown_count, total_lines, files:[{path, size_bytes, line_count, symbol_count, procedure_count}]}.

Example: bsl_workspace_scan(directory="src/cf/CommonModules", max_files=50)""",
    ),
    "bsl_meta_object": (
        "1C metadata: one object",
        """WHAT: Structure of one 1C configuration object: attributes, tabular sections, form attributes.

USE WHEN: you need an object's fields/types from the XML metadata export.
REQUIRES: a 1C configuration export (Configuration.xml) present in the workspace.
DO NOT USE FOR: code search (bsl_search) or listing a whole collection (bsl_meta_collection).

Args (typical): object name/reference (e.g. "Документ.РеализацияТоваровУслуг") and/or config root.
Returns: object structure (attributes with types/synonyms, tabular sections, forms).

Example: bsl_meta_object(name="Документ.РеализацияТоваровУслуг")""",
    ),
    "bsl_meta_collection": (
        "1C metadata: list collection",
        """WHAT: List objects of one global collection (Справочники, Документы, РегистрыСведений, ...).

USE WHEN: discovering which objects exist before inspecting one.
REQUIRES: a 1C configuration export (Configuration.xml) in the workspace.
DO NOT USE FOR: code search or one object's fields (use bsl_meta_object).

Args (typical): collection name, optional name filter.
Returns: {objects:[{name, kind, synonym}]}.

Example: bsl_meta_collection(collection="Документы")""",
    ),
    "bsl_meta_index": (
        "1C metadata: reindex",
        """WHAT: Re-parse the 1C configuration XML export and rebuild the metadata index.

USE WHEN: metadata was just changed/added and metadata tools return stale results.
DO NOT USE FOR: normal metadata queries.

Args (typical): optional workspace root.
Returns: indexing summary.

Example: bsl_meta_index()""",
    ),
    "bsl_contract_version": (
        "Server contract version",
        """WHAT: Returns the MCP response-contract version and the list of tools.

USE WHEN: rarely needed; only for diagnostics/integration checks, not for code analysis.
DO NOT USE FOR: any code task.

Args: none.
Returns: {schema_version, server, tool_modes, tools:[...]}.

Example: bsl_contract_version()""",
    ),
    "complexity": (
        "Complexity per method (raw numbers)",
        """WHAT: Cyclomatic (McCabe) and cognitive complexity for EVERY method in one BSL module.

USE WHEN:
- Deciding what to refactor first.
- Checking that a newly written / changed method stays within budget.
- The task mentions "сложность", "refactor", "too complex", "maintainability".
DO NOT USE FOR:
- security/performance/SQL issues (use module_health).
- the whole project (use workspace_diagnostics).
- running lint rules (use bsl_diagnostics/bsl_check_file).

Args:
- file (string, required): path to the .bsl file (absolute or workspace-relative, e.g. "Module.bsl").

Returns:
{file, thresholds:{cognitive:15, mccabe:20}, method_count, flagged_count, max_cognitive, max_mccabe,
 methods:[{name, kind, line, cognitive, mccabe, over_cognitive, over_mccabe}]}
(line is 1-based; over_* = above the threshold.)
Thresholds come from onec-hbk-bsl.toml (defaults cognitive>15, cyclomatic>20).

Example: complexity(file="src/cf/CommonModules/ОбщегоНазначения/Ext/Module.bsl")""",
    ),
    "module_health": (
        "Module triage: complexity + risks",
        """WHAT: One-call health report for a module: complexity per method MERGED with
security/performance/SQL diagnostics, each issue attributed to its method and RANKED.

USE WHEN:
- "what should I fix first in this module?" / pre-commit health gate.
- You want security/performance/SQL problems AND complexity together.
DO NOT USE FOR:
- raw complexity numbers only (use complexity).
- the whole project (use workspace_diagnostics).
- presence of a specific rule in one file (use bsl_check_file).

Args:
- file (string, required): path to the .bsl file.

Returns:
{file, thresholds, weights:{security:10, performance:4, sql:4, ...}, method_count, flagged_count,
 issue_totals:{security, performance, sql}, module_level_issues:{...},
 top_targets:[{name, line, cognitive, mccabe, over_*, security, performance, sql, score}], methods:[...]}
Higher `score` = fix sooner. `top_targets` is already sorted (worst first).

Example: module_health(file="src/cf/.../Module.bsl")""",
    ),
    "workspace_diagnostics": (
        "Lint the whole project (aggregated)",
        """WHAT: Run BSL diagnostics across a directory/project and return AGGREGATED counts
(by severity, by rule, worst files) instead of a giant per-file dump.

USE WHEN:
- Project-wide review / "what is broken in this project?".
- Triage before a release or a big refactor.
DO NOT USE FOR:
- a single file (use bsl_diagnostics — much faster and detailed).
- complexity (use complexity/module_health).

Args:
- path (string, default "."): directory to scan (absolute or workspace-relative).
- select (string, optional): comma-separated rules to KEEP.
- ignore (string, optional): comma-separated rules to SKIP.
- min_severity (string, default "WARNING"): ERROR | WARNING | INFORMATION | HINT.
- top_n (int, default 20): how many top rules/files to return.
- max_files (int, default 2000): safety cap on scanned files; lower it for huge projects.
- include_items (bool, default false): include capped raw diagnostics (default aggregated only).

Returns:
{root, files_scanned, files_with_issues, total, min_severity, by_severity:{...},
 top_rules:[{code, rule_name, count}], top_files:[{file, count}], items|null}
(top_rules/top_files are sorted worst-first.)

Example (common): workspace_diagnostics(path="src/cf", min_severity="ERROR", top_n=10)
Example (detail):  workspace_diagnostics(path="src/cf/CommonModules", include_items=true, top_n=5)""",
    ),
}


def apply(app: Any) -> int:
    """Overwrite titles/descriptions of registered tools. Returns how many were updated."""
    tools = getattr(getattr(app, "_tool_manager", None), "_tools", None)
    if isinstance(tools, dict):
        updated = 0
        for name, (title, description) in TOOL_DOCS.items():
            tool = tools.get(name)
            if tool is None:
                continue
            tool.title = title
            tool.description = description.strip()
            updated += 1
    else:
        updated = 0

    if hasattr(app, "instructions"):
        # FastMCP.instructions is a read-only property; the value lives on the inner server.
        inner = getattr(app, "_mcp_server", None)
        if inner is not None and hasattr(inner, "instructions"):
            inner.instructions = INSTRUCTIONS.strip()
    return updated
