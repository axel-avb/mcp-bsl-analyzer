from dataclasses import replace
from pathlib import Path

import pytest

from bsl_mcp import lsp_facade as facade


def _opts(**over) -> facade.EngineOptions:
    return replace(facade.EngineOptions(), **over)


def test_resolve_path_allows_inside(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    sub = tmp_path / "src" / "Module.bsl"
    sub.parent.mkdir()
    sub.write_text("Процедура А()\nКонецПроцедуры\n", encoding="utf-8")
    assert facade.resolve_path("src/Module.bsl") == sub.resolve()


def test_resolve_path_denies_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    with pytest.raises(facade.PathDenied):
        facade.resolve_path("../outside.bsl")


def test_severity_rank_order():
    assert facade.severity_rank("ERROR") < facade.severity_rank("WARNING")
    assert facade.severity_rank("WARNING") < facade.severity_rank("HINT")


def test_iter_bsl_files_skips_and_excludes(tmp_path):
    (tmp_path / "A.bsl").write_text("", encoding="utf-8")
    (tmp_path / "B.os").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    skip = tmp_path / ".git"
    skip.mkdir()
    (skip / "C.bsl").write_text("", encoding="utf-8")
    skip2 = tmp_path / "tasks"
    skip2.mkdir()
    (skip2 / "D.bsl").write_text("", encoding="utf-8")

    found = {Path(p).name for p in facade.iter_bsl_files(tmp_path, _opts())}
    assert found == {"A.bsl", "B.os"}

    excluded = {Path(p).name for p in facade.iter_bsl_files(tmp_path, _opts(exclude_globs=("*A.bsl",)))}
    assert excluded == {"B.os"}


def test_enrich_complexity_messages(monkeypatch):
    f = tmp_path_wrapper()
    monkeypatch.setattr(
        facade, "file_complexity",
        lambda path, opts: [
            facade.ComplexityRow(name="Плохо", kind="function", line=1, cognitive=20, mccabe=30),
        ],
    )
    issues = [
        {"code": "BSL011", "line": 1, "message": "Когнитивная сложность"},
        {"code": "BSL019", "line": 1, "message": "Цикломатическая сложность"},
        {"code": "BSL001", "line": 99, "message": "неизвестно"},
    ]
    facade.enrich_complexity_messages(f, facade.EngineOptions(), issues)
    assert issues[0]["message"] == "Когнитивная сложность метода «Плохо»: 20 (допустимо ≤ 15)"
    assert issues[1]["message"] == "Цикломатическая сложность метода «Плохо»: 30 (допустимо ≤ 20)"
    assert issues[2]["message"] == "неизвестно"


def tmp_path_wrapper() -> Path:
    import tempfile

    d = tempfile.mkdtemp()
    return Path(d) / "mod.bsl"
