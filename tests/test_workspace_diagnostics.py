from pathlib import Path
from typing import Any

from bsl_mcp import lsp_facade as facade
from bsl_mcp.tools import workspace_diagnostics as wd


class _DummyApp:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, **kwargs: Any):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _tool():
    app = _DummyApp()
    wd.register_workspace_diagnostics_tool(app)
    return app.tools["workspace_diagnostics"]


def test_workspace_aggregates_and_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        facade, "load_engine_options", lambda root, select=None, ignore=None: facade.EngineOptions()
    )
    monkeypatch.setattr(facade, "rule_name", lambda code: code)

    a = tmp_path / "A.bsl"
    b = tmp_path / "B.bsl"
    a.write_text("")
    b.write_text("")

    monkeypatch.setattr(facade, "iter_bsl_files", lambda root, opts, max_files=None: iter([a, b]))

    def fake_diags(path: Path, opts: facade.EngineOptions):
        if Path(path).name != "A.bsl":
            return []
        return [
            {"file": str(path), "line": 1, "character": 0, "end_line": 1, "end_character": 0,
             "severity": "ERROR", "code": "BSL001", "message": "x"},
            {"file": str(path), "line": 2, "character": 0, "end_line": 2, "end_character": 0,
             "severity": "HINT", "code": "BSL002", "message": "y"},
        ]

    monkeypatch.setattr(facade, "file_diagnostics", fake_diags)

    res = _tool()(path=".")
    assert res["files_scanned"] == 2
    assert res["files_with_issues"] == 1
    # HINT is below default min_severity=WARNING
    assert res["total"] == 1
    assert res["by_severity"] == {"ERROR": 1}
    assert res["top_rules"][0]["code"] == "BSL001"


def test_workspace_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    res = _tool()(path="../outside")
    assert "error" in res
