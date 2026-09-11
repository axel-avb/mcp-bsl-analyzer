from types import SimpleNamespace

from bsl_mcp import tool_docs


def _fake_app(names):
    tools = {n: SimpleNamespace(title=None, description="old") for n in names}
    return SimpleNamespace(_tool_manager=SimpleNamespace(_tools=tools)), tools


def test_apply_sets_title_and_description():
    app, tools = _fake_app(["complexity", "workspace_diagnostics", "bsl_status", "unknown_tool"])
    updated = tool_docs.apply(app)
    assert updated == 3
    assert tools["complexity"].title == "Complexity per method (raw numbers)"
    assert "USE WHEN" in tools["complexity"].description
    assert tools["unknown_tool"].description == "old"


def test_all_known_names_have_docs():
    names = {
        "bsl_contract_version", "bsl_status", "bsl_find_symbol", "bsl_file_symbols",
        "bsl_callers", "bsl_callees", "bsl_diagnostics", "bsl_definition", "bsl_check_file",
        "bsl_list_rules", "bsl_index_file", "bsl_hover", "bsl_references", "bsl_read_file",
        "bsl_search", "bsl_format", "bsl_rename", "bsl_fix", "bsl_workspace_scan",
        "bsl_meta_object", "bsl_meta_collection", "bsl_meta_index",
        "complexity", "module_health", "workspace_diagnostics",
    }
    assert set(tool_docs.TOOL_DOCS) == names


def test_descriptions_are_non_trivial():
    for name, (title, desc) in tool_docs.TOOL_DOCS.items():
        assert title and len(title) < 60, name
        assert len(desc) > 150, name
        assert "WHAT:" in desc and "Example" in desc, name
