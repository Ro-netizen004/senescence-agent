"""Regression tests for blinded human-annotation reply extraction."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "eval/ablation/annotation/extract_blinded_replies.py"
SPEC = importlib.util.spec_from_file_location("extract_blinded_replies", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_extracts_permutations_and_distinguishes_ungoverned(tmp_path: Path) -> None:
    _write(
        tmp_path / "study_governed_same_method_seed1.json",
        {"arm": "governed_same_method", "dataset": "Study", "permutations": [
            {"seed": 1, "reply": "governed reply"},
        ]},
    )
    _write(
        tmp_path / "study_ungoverned_same_method_seed1.json",
        {"arm": "ungoverned_same_method", "dataset": "Study", "permutations": [
            {"seed": 1, "reply": "ungoverned reply"},
        ]},
    )

    rows = MODULE.extract_replies(tmp_path)

    assert [(row["arm"], row["reply"]) for row in rows] == [
        ("governed", "governed reply"),
        ("ungoverned", "ungoverned reply"),
    ]


def test_extracts_both_arms_from_paired_record(tmp_path: Path) -> None:
    _write(
        tmp_path / "paired_results.json",
        {"allocations": [{
            "seed": 7,
            "governed": {"reply": "withheld"},
            "ungoverned": {"reply": "significant"},
        }]},
    )

    rows = MODULE.extract_replies(tmp_path)

    assert {row["arm"] for row in rows} == {"governed", "ungoverned"}
    assert {row["seed"] for row in rows} == {7}


def test_unknown_unpaired_arm_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path / "unknown.json", {"results": [{"reply": "ambiguous"}]})

    try:
        MODULE.extract_replies(tmp_path)
    except ValueError as exc:
        assert "Cannot determine" in str(exc)
    else:
        raise AssertionError("Unknown source arm should not be guessed")
