from pathlib import Path

import pytest

from bsl_mcp import lsp_facade as facade

pytest.importorskip("onec_hbk_bsl", reason="onec-hbk-bsl-core required (Python >=3.12)")

FIXTURE = Path(__file__).parent / "fixtures" / "simple.bsl"


def test_complexity_per_method():
    rows = facade.file_complexity(FIXTURE, facade.EngineOptions())
    by_name = {r.name: r for r in rows}

    assert set(by_name) == {"Простая", "Сложная"}
    assert by_name["Простая"].line < by_name["Сложная"].line
    assert by_name["Сложная"].cognitive > by_name["Простая"].cognitive
    assert by_name["Сложная"].mccabe > by_name["Простая"].mccabe


def test_complexity_flags_over_threshold():
    rows = facade.file_complexity(FIXTURE, facade.EngineOptions())
    simple = next(r for r in rows if r.name == "Простая").to_dict(15, 20)
    assert simple["over_cognitive"] is False and simple["over_mccabe"] is False
