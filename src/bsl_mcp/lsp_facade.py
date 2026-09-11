"""Thin facade over ``onec_hbk_bsl`` internals.

Everything that reaches into another project's non-public modules lives here, so an
upstream rename only breaks one file.

ponytail: relies on onec_hbk_bsl internal APIs (document_snapshot, diagnostic.engine);
pinned to onec-hbk-bsl-core==0.8.50 in pyproject. Bump + re-run tests on upgrade.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# BSL LS reference defaults; overridden by onec-hbk-bsl.toml via engine_kwargs().
DEFAULT_COGNITIVE_THRESHOLD = 15
DEFAULT_MCCABE_THRESHOLD = 20

_SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFORMATION": 2, "HINT": 3}


class PathDenied(ValueError):
    """Raised when a requested path escapes the configured workspace root."""


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT") or os.getcwd()).resolve()


def resolve_path(path: str, *, base: Path | None = None) -> Path:
    """Resolve *path* (absolute or workspace-relative) and keep it inside the root."""
    root = (base or workspace_root()).resolve()
    raw = Path(path)
    if not raw.is_absolute():
        raw = root / raw
    resolved = raw.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise PathDenied(f"path outside workspace: {path}")
    return resolved


@dataclass(frozen=True, slots=True)
class ComplexityRow:
    name: str
    kind: str
    line: int  # 1-based
    cognitive: int
    mccabe: int

    def to_dict(self, cog_threshold: int, mccabe_threshold: int) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "line": self.line,
            "cognitive": self.cognitive,
            "mccabe": self.mccabe,
            "over_cognitive": self.cognitive > cog_threshold,
            "over_mccabe": self.mccabe > mccabe_threshold,
        }


def _load_config(root: Path):
    from onec_hbk_bsl.cli.config import load_config, resolve_config

    return resolve_config(load_config(str(root)))


@dataclass(frozen=True, slots=True)
class EngineOptions:
    select: set[str] | None = None
    ignore: set[str] | None = None
    engine_kwargs: dict[str, Any] = field(default_factory=dict)
    cognitive_threshold: int = DEFAULT_COGNITIVE_THRESHOLD
    mccabe_threshold: int = DEFAULT_MCCABE_THRESHOLD
    exclude_globs: tuple[str, ...] = ()
    per_file_ignores: dict[str, list[str]] = field(default_factory=dict)

    def is_excluded(self, path: Path) -> bool:
        s = str(path)
        return any(fnmatch.fnmatch(s, pat) or fnmatch.fnmatch(path.name, pat) for pat in self.exclude_globs)


def load_engine_options(root: Path, *, select: str | None = None, ignore: str | None = None) -> EngineOptions:
    from onec_hbk_bsl.analysis.diagnostics import normalize_rule_code_set

    cfg = _load_config(root)
    sel = normalize_rule_code_set(select.split(",")) if select else cfg.select
    ign = normalize_rule_code_set(ignore.split(",")) if ignore else cfg.ignore
    kwargs = cfg.engine_kwargs()
    return EngineOptions(
        select=sel,
        ignore=ign,
        engine_kwargs=kwargs,
        cognitive_threshold=int(kwargs.get("max_cognitive_complexity", DEFAULT_COGNITIVE_THRESHOLD)),
        mccabe_threshold=int(kwargs.get("max_mccabe_complexity", DEFAULT_MCCABE_THRESHOLD)),
        exclude_globs=tuple(cfg.exclude),
        per_file_ignores=dict(cfg.per_file_ignores),
    )


def _new_engine(opts: EngineOptions):
    from onec_hbk_bsl.analysis.diagnostic.engine import DiagnosticEngine
    from onec_hbk_bsl.parser.bsl_parser import BslParser

    return DiagnosticEngine(
        parser=BslParser(),
        select=opts.select,
        ignore=opts.ignore,
        **opts.engine_kwargs,
    )


def file_complexity(path: Path, opts: EngineOptions) -> list[ComplexityRow]:
    """Per-method ``(cognitive, mccabe)`` metrics for a single BSL module."""
    from onec_hbk_bsl.analysis.document_snapshot import build_document_snapshot
    from onec_hbk_bsl.parser.bsl_parser import BslParser

    content = path.read_text(encoding="utf-8-sig", errors="replace")
    snapshot = build_document_snapshot(str(path), content=content, parser=BslParser())
    procs = snapshot.procedures
    metrics = snapshot.complexity_metrics_for_procs(procs)
    rows: list[ComplexityRow] = []
    for proc, (cognitive, mccabe) in zip(procs, metrics, strict=False):
        rows.append(
            ComplexityRow(
                name=str(getattr(proc, "name", "")),
                kind=str(getattr(proc, "kind", "")),
                line=int(getattr(proc, "start_idx", 0)) + 1,
                cognitive=int(cognitive),
                mccabe=int(mccabe),
            )
        )
    rows.sort(key=lambda r: r.line)
    return rows


def file_diagnostics(path: Path, opts: EngineOptions) -> list[dict[str, Any]]:
    engine = _new_engine(opts)
    issues = engine.check_file(str(path))
    out: list[dict[str, Any]] = []
    for d in issues:
        out.append(
            {
                "file": str(path),
                "line": int(d.line),
                "character": int(d.character),
                "end_line": int(d.end_line),
                "end_character": int(d.end_character),
                "severity": d.severity.name,
                "code": d.code,
                "message": d.message,
            }
        )
    enrich_complexity_messages(path, opts, out)
    return out


_COMPLEXITY_ATTR = {"BSL011": "cognitive", "BSL019": "mccabe"}
_COMPLEXITY_LABEL = {"BSL011": "Когнитивная сложность", "BSL019": "Цикломатическая сложность"}


def enrich_complexity_messages(path: Path, opts: EngineOptions, issues: list[dict[str, Any]]) -> None:
    """Fill self-sufficient messages for complexity diagnostics (BSL011/BSL019).

    onec-hbk-bsl reports these with just the rule name as message. We append the method,
    actual value and the allowed threshold so a diagnostic reads standalone.
    """
    if not {d["code"] for d in issues} & set(_COMPLEXITY_ATTR):
        return
    rows = file_complexity(path, opts)
    by_line = {r.line: r for r in rows}
    for d in issues:
        attr = _COMPLEXITY_ATTR.get(d["code"])
        if attr is None:
            continue
        row = by_line.get(d["line"])
        if row is None:
            continue
        value = getattr(row, attr)
        threshold = opts.cognitive_threshold if d["code"] == "BSL011" else opts.mccabe_threshold
        d["message"] = (
            f"{_COMPLEXITY_LABEL[d['code']]} метода «{row.name}»: {value} "
            f"(допустимо ≤ {threshold})"
        )


def rule_name(code: str) -> str:
    from onec_hbk_bsl.analysis.diagnostic.i18n import get_rule

    try:
        return get_rule(code).name
    except Exception:
        return code


def rule_tags(code: str) -> list[str]:
    from onec_hbk_bsl.analysis.diagnostics import RULE_METADATA

    return list(RULE_METADATA.get(code, {}).get("tags", []))


# onec-hbk-bsl rule tags mapped onto the risk categories we report.
_QUALITY_TAGS: dict[str, tuple[str, ...]] = {
    "security": ("security", "credentials", "access-control"),
    "performance": ("performance",),
    "sql": ("query",),
}


def rule_quality_categories(code: str) -> list[str]:
    """Risk categories (security/performance/sql) a rule belongs to, by its tags."""
    tags = {t.lower() for t in rule_tags(code)}
    return [cat for cat, wanted in _QUALITY_TAGS.items() if tags.intersection(wanted)]


def iter_bsl_files(root: Path, opts: EngineOptions, *, max_files: int | None = None) -> Iterator[Path]:
    skip_dirs = {".git", ".svn", "node_modules", "vendor", "tasks", "build", "out", "bin", "__pycache__"}
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for name in filenames:
            if not name.lower().endswith((".bsl", ".os")):
                continue
            p = Path(dirpath) / name
            if opts.is_excluded(p):
                continue
            yield p
            count += 1
            if max_files is not None and count >= max_files:
                return


def severity_rank(severity: str) -> int:
    return _SEVERITY_ORDER.get(severity.upper(), 99)
