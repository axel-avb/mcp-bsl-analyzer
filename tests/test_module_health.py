import pytest

from bsl_mcp import lsp_facade as facade
from bsl_mcp.tools import module_health as mh

pytest.importorskip("onec_hbk_bsl", reason="onec-hbk-bsl-core required (Python >=3.12)")


def _rows():
    return [
        facade.ComplexityRow(name="Простая", kind="procedure", line=1, cognitive=0, mccabe=1),
        facade.ComplexityRow(name="Сложная", kind="function", line=5, cognitive=11, mccabe=6),
    ]


def test_enclosing_method():
    rows = _rows()
    assert mh._enclosing(rows, 1) == 0
    assert mh._enclosing(rows, 4) == 0
    assert mh._enclosing(rows, 5) == 1
    assert mh._enclosing(rows, 900) == 1
    assert mh._enclosing(rows, 0) is None


def test_score_adds_weights_and_overage():
    e = {"security": 1, "performance": 2, "sql": 0, "over_cognitive": True,
         "cognitive": 20, "over_mccabe": False, "mccabe": 1}
    assert mh._score(e) == 10 * 1 + 4 * 2 + 4 * 0 + 20


def test_quality_categories_mapping(monkeypatch):
    monkeypatch.setattr(facade, "rule_tags", lambda code: {"security", "query"})
    assert facade.rule_quality_categories("BSL012") == ["security", "sql"]
    assert facade.rule_quality_categories("BSL999") == []
