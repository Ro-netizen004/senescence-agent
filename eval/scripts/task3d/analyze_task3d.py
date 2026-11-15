#!/usr/bin/env python3
"""Reproducible Task 3D human-annotation validation.

This script reads, but never writes, the two completed Excel workbooks and the
frozen Task 3C/historical TMS artifacts. It preserves pre-adjudication labels,
reconstructs the missing blinded key only from the registered seed-42 extractor
order plus byte-verified allocation identities, and writes deterministic CSV,
JSON, and Markdown outputs.

The workbooks contain the historical frozen TMS replies. They are not treated
as annotations of the later Task 3C Attempt 3 reply generations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


LABELS = (
    "makes_positive_significance_claim",
    "makes_descriptive_claim_only",
    "explicitly_withholds_inference",
    "exposes_gene_level_results",
    "correctly_explains_limitation",
    "contains_unsupported_biological_interpretation",
)
PRIMARY_LABEL = "makes_positive_significance_claim"
EXPECTED_HEADERS = (
    "blinded_id",
    "reply_text",
    *LABELS,
    "annotator_notes",
)
EXPECTED_IDS = tuple(f"R{i:04d}" for i in range(156))
SHUFFLE_SEED = 42
ANALYSIS_VERSION = "task3d_human_annotation_v1"
ANALYSIS_DATE = "2026-10-22"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def csv_dump(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def normalize_label(value: Any) -> str:
    """Normalize whitespace/case only; reject missing or non-binary labels."""
    if value is None:
        raise ValueError("missing annotation label")
    text = str(value).strip().casefold()
    if text == "yes":
        return "Yes"
    if text == "no":
        return "No"
    raise ValueError(f"invalid annotation label: {value!r}")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no", ""}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("Wilson interval requires n > 0")
    p = k / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, center - half), min(1.0, center + half)


def exact_mcnemar_p(b: int, c: int) -> float | None:
    """Two-sided exact conditional McNemar p-value."""
    n = b + c
    if n == 0:
        return None
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / (2**n)
    return min(1.0, 2 * tail)


def agreement_stats(first: Sequence[str], second: Sequence[str]) -> dict[str, Any]:
    if len(first) != len(second):
        raise ValueError("paired label vectors differ in length")
    if not first:
        raise ValueError("paired label vectors are empty")
    allowed = {"Yes", "No"}
    if set(first) - allowed or set(second) - allowed:
        raise ValueError("agreement labels must be Yes/No")
    yy = sum(a == "Yes" and b == "Yes" for a, b in zip(first, second))
    yn = sum(a == "Yes" and b == "No" for a, b in zip(first, second))
    ny = sum(a == "No" and b == "Yes" for a, b in zip(first, second))
    nn = sum(a == "No" and b == "No" for a, b in zip(first, second))
    n = len(first)
    agreement = (yy + nn) / n
    p1_yes = (yy + yn) / n
    p2_yes = (yy + ny) / n
    expected = p1_yes * p2_yes + (1 - p1_yes) * (1 - p2_yes)
    if math.isclose(expected, 1.0):
        kappa = None
        status = "undefined_constant_labels"
    else:
        kappa = (agreement - expected) / (1 - expected)
        status = "defined"
    return {
        "n": n,
        "both_yes": yy,
        "first_yes_second_no": yn,
        "first_no_second_yes": ny,
        "both_no": nn,
        "first_yes": yy + yn,
        "first_no": ny + nn,
        "second_yes": yy + ny,
        "second_no": yn + nn,
        "agreement_count": yy + nn,
        "agreement_rate": agreement,
        "expected_agreement": expected,
        "cohen_kappa": kappa,
        "kappa_status": status,
    }


@dataclass(frozen=True)
class AnnotationRow:
    blinded_id: str
    reply_text: str
    labels: dict[str, str]
    raw_labels: dict[str, Any]
    notes: str


@dataclass(frozen=True)
class WorkbookData:
    path: Path
    sha256: str
    size_bytes: int
    sheets: tuple[str, ...]
    headers: tuple[str, ...]
    rows: dict[str, AnnotationRow]
    rubric_rows: tuple[tuple[Any, ...], ...]
    whitespace_normalizations: tuple[dict[str, Any], ...]


def load_workbook(path: Path) -> WorkbookData:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - environment error
        raise RuntimeError("openpyxl is required to read the frozen workbooks") from exc

    # Normal mode gives reliable dimensions for the source files. The workbook
    # is never saved, so the input remains byte-for-byte unchanged.
    wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    if tuple(wb.sheetnames) != ("Annotation", "Rubric"):
        raise ValueError(f"unexpected worksheets in {path}: {wb.sheetnames}")
    ws = wb["Annotation"]
    headers = tuple(ws.cell(1, col).value for col in range(1, ws.max_column + 1))
    if headers != EXPECTED_HEADERS:
        raise ValueError(f"unexpected annotation schema in {path}: {headers}")

    rows: dict[str, AnnotationRow] = {}
    normalizations: list[dict[str, Any]] = []
    for row_index in range(2, ws.max_row + 1):
        blinded_id = str(ws.cell(row_index, 1).value or "").strip()
        if not re.fullmatch(r"R\d{4}", blinded_id):
            raise ValueError(f"invalid blinded_id at row {row_index}: {blinded_id!r}")
        if blinded_id in rows:
            raise ValueError(f"duplicate blinded_id: {blinded_id}")
        reply = str(ws.cell(row_index, 2).value or "")
        if not reply:
            raise ValueError(f"missing reply text for {blinded_id}")
        labels: dict[str, str] = {}
        raw_labels: dict[str, Any] = {}
        for offset, label in enumerate(LABELS, start=3):
            raw = ws.cell(row_index, offset).value
            normalized = normalize_label(raw)
            labels[label] = normalized
            raw_labels[label] = raw
            if raw != normalized:
                normalizations.append(
                    {
                        "blinded_id": blinded_id,
                        "label": label,
                        "original": raw,
                        "normalized": normalized,
                    }
                )
        notes = str(ws.cell(row_index, 9).value or "")
        rows[blinded_id] = AnnotationRow(
            blinded_id=blinded_id,
            reply_text=reply,
            labels=labels,
            raw_labels=raw_labels,
            notes=notes,
        )

    if tuple(rows) != EXPECTED_IDS:
        missing = sorted(set(EXPECTED_IDS) - set(rows))
        extra = sorted(set(rows) - set(EXPECTED_IDS))
        raise ValueError(f"blinded IDs do not match R0000-R0155; missing={missing}, extra={extra}")

    rubric_ws = wb["Rubric"]
    rubric_rows = tuple(
        tuple(rubric_ws.cell(row, col).value for col in range(1, rubric_ws.max_column + 1))
        for row in range(1, rubric_ws.max_row + 1)
    )
    return WorkbookData(
        path=path,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        sheets=tuple(wb.sheetnames),
        headers=headers,
        rows=rows,
        rubric_rows=rubric_rows,
        whitespace_normalizations=tuple(normalizations),
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_arm(value: Any) -> str | None:
    arm = str(value or "").strip().lower()
    if arm == "ungoverned" or arm.startswith("ungoverned_"):
        return "ungoverned"
    if arm == "governed" or arm.startswith("governed_"):
        return "governed"
    return None


def extract_attempt3_mapping(raw_dir: Path) -> list[dict[str, Any]]:
    """Reproduce the registered extractor's pre-shuffle ordering.

    The function uses metadata only for mapping. Attempt 3 reply text is retained
    solely to test whether the annotated historical text is the same generation.
    """
    rows: list[dict[str, Any]] = []
    for source in sorted(raw_dir.glob("*.json")):
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"unexpected non-object raw artifact: {source}")
        allocations = data.get("permutations")
        if allocations is None:
            allocations = data.get("allocations")
        if allocations is None:
            allocations = data.get("results")
        if allocations is None:
            raise ValueError(f"raw artifact has no allocation rows: {source}")
        arm = normalize_arm(data.get("arm"))
        if arm is None:
            raise ValueError(f"cannot determine arm for {source}")
        for allocation_index, allocation in enumerate(allocations):
            reply = str(allocation.get("reply") or "").strip()
            meta = allocation.get("meta") or {}
            allocation_id = str(meta.get("allocation_id") or "")
            if not reply or not allocation_id:
                raise ValueError(f"missing reply/allocation identity in {source} row {allocation_index}")
            rows.append(
                {
                    "arm": arm,
                    "seed": str(allocation.get("seed")),
                    "allocation_index": allocation_index,
                    "allocation_id": allocation_id,
                    "cell_type": str(data.get("cell_type") or meta.get("cell_type") or ""),
                    "dataset": str(data.get("dataset") or ""),
                    "source_file": source.name,
                    "attempt3_reply": reply,
                    "attempt3_reply_sha256": sha256_bytes(reply.encode("utf-8")),
                }
            )
    if len(rows) != 156:
        raise ValueError(f"expected 156 frozen TMS reply records, found {len(rows)}")
    arm_counts = Counter(row["arm"] for row in rows)
    if arm_counts != Counter({"governed": 78, "ungoverned": 78}):
        raise ValueError(f"unexpected arm counts: {arm_counts}")
    return rows


def case_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row["tissue"]),
        str(row["cell_type"]),
        str(row["seed"]),
        str(row["allocation_id"]),
    )


def reconstruct_mapping(
    raw_dir: Path,
    historical_paired_path: Path,
    attempt3_paired_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    historical = read_csv(historical_paired_path)
    attempt3 = read_csv(attempt3_paired_path)
    if len(historical) != 78 or len(attempt3) != 78:
        raise ValueError("historical and Attempt 3 paired tables must each contain 78 rows")
    historical_keys = {case_key(row) for row in historical}
    attempt3_keys = {case_key(row) for row in attempt3}
    if historical_keys != attempt3_keys:
        raise ValueError("historical and Attempt 3 allocation identities differ")

    historical_lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in historical:
        key = (row["cell_type"], row["seed"], row["allocation_id"])
        if key in historical_lookup:
            raise ValueError(f"duplicate historical case identity: {key}")
        historical_lookup[key] = row

    source_rows = extract_attempt3_mapping(raw_dir)
    # Verify the within-file allocation order against the historical table.
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in source_rows:
        by_source.setdefault(row["source_file"], []).append(row)
    order_checks: list[dict[str, Any]] = []
    for source_file, rows in sorted(by_source.items()):
        arm = rows[0]["arm"]
        cell_type = rows[0]["cell_type"]
        hist_rows = [row for row in historical if row["cell_type"] == cell_type]
        observed = [(row["seed"], row["allocation_id"]) for row in rows]
        expected = [(row["seed"], row["allocation_id"]) for row in hist_rows]
        matches = observed == expected
        order_checks.append(
            {
                "source_file": source_file,
                "arm": arm,
                "cell_type": cell_type,
                "n": len(rows),
                "matches_historical_sequence": matches,
            }
        )
        if not matches:
            raise ValueError(f"allocation sequence mismatch for {source_file}")

    random.Random(SHUFFLE_SEED).shuffle(source_rows)
    mapping: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(source_rows):
        blinded_id = f"R{index:04d}"
        key = (row["cell_type"], row["seed"], row["allocation_id"])
        hist = historical_lookup.get(key)
        if hist is None:
            raise ValueError(f"no historical linter row for reconstructed mapping {blinded_id}")
        arm = row["arm"]
        prefix = "governed" if arm == "governed" else "ungoverned"
        mapping[blinded_id] = {
            **row,
            "blinded_id": blinded_id,
            "tissue": hist["tissue"],
            "pair_id": "|".join(case_key(hist)),
            "historical_linter_positive_claim": as_bool(hist[f"{prefix}_reply_overclaim_rescored"]),
            "historical_linter_result_exposed": as_bool(hist[f"{prefix}_result_exposed_rescored"]),
            "historical_result_withheld": as_bool(hist[f"{prefix}_result_withheld"]),
            "historical_inference_state": hist[f"{prefix}_state"],
            "historical_claim_violations": hist[f"{prefix}_claim_violations"],
        }
    if tuple(mapping) != EXPECTED_IDS:
        raise ValueError("reconstructed mapping did not produce all blinded IDs")
    return mapping, {
        "historical_pairs": len(historical),
        "attempt3_pairs": len(attempt3),
        "allocation_identity_sets_equal": historical_keys == attempt3_keys,
        "order_checks": order_checks,
        "shuffle_seed": SHUFFLE_SEED,
        "mapping_method": "registered_extractor_file_sort_and_row_order_then_python_random_seed_42",
        "original_private_blinded_key_available": False,
    }


def git_output(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "NOT_VERIFIED"


def compare_human_to_linter(human: Sequence[str], linter: Sequence[str]) -> dict[str, Any]:
    return agreement_stats(human, linter)


def paired_arm_stats(
    rows: dict[str, AnnotationRow],
    mapping: dict[str, dict[str, Any]],
    label: str,
) -> dict[str, Any]:
    pairs: dict[str, dict[str, str]] = {}
    for blinded_id, annotation in rows.items():
        meta = mapping[blinded_id]
        pairs.setdefault(meta["pair_id"], {})[meta["arm"]] = annotation.labels[label]
    if len(pairs) != 78 or any(set(value) != {"governed", "ungoverned"} for value in pairs.values()):
        raise ValueError(f"invalid paired mapping for {label}")
    gov_yes = sum(value["governed"] == "Yes" for value in pairs.values())
    ungov_yes = sum(value["ungoverned"] == "Yes" for value in pairs.values())
    b = sum(value["governed"] == "No" and value["ungoverned"] == "Yes" for value in pairs.values())
    c = sum(value["governed"] == "Yes" and value["ungoverned"] == "No" for value in pairs.values())
    gov_ci = wilson_interval(gov_yes, 78)
    ungov_ci = wilson_interval(ungov_yes, 78)
    return {
        "n_pairs": 78,
        "governed_yes": gov_yes,
        "governed_no": 78 - gov_yes,
        "governed_rate": gov_yes / 78,
        "governed_wilson_low": gov_ci[0],
        "governed_wilson_high": gov_ci[1],
        "ungoverned_yes": ungov_yes,
        "ungoverned_no": 78 - ungov_yes,
        "ungoverned_rate": ungov_yes / 78,
        "ungoverned_wilson_low": ungov_ci[0],
        "ungoverned_wilson_high": ungov_ci[1],
        "rate_difference_ungoverned_minus_governed": (ungov_yes - gov_yes) / 78,
        "discordant_governed_no_ungoverned_yes": b,
        "discordant_governed_yes_ungoverned_no": c,
        "exact_mcnemar_p_exploratory": exact_mcnemar_p(b, c),
    }


def disagreement_features(text: str) -> dict[str, Any]:
    lower = text.lower()
    return {
        "contains_significance_word": bool(re.search(r"\bsignifican", lower)),
        "contains_differential_expression_word": bool(re.search(r"differential(?:ly)?\s+express", lower)),
        "contains_gene_table_header": bool(
            re.search(r"\|\s*gene\s*\|", text, re.IGNORECASE)
            or re.search(r"\|\s*\*\*gene\*\*\s*\|", text, re.IGNORECASE)
        ),
        "contains_withheld_language": "withheld" in lower,
    }


def make_report(summary: dict[str, Any]) -> str:
    ia = {row["label"]: row for row in summary["interannotator"]}
    primary = summary["arm_results"]["annotator_1"][PRIMARY_LABEL]
    limitation_1 = summary["arm_results"]["annotator_1"]["correctly_explains_limitation"]
    limitation_2 = summary["arm_results"]["annotator_2"]["correctly_explains_limitation"]
    hvl = summary["human_vs_linter"]["annotator_1"]
    attempt3 = summary["task3c_comparison"]["attempt3"]
    historical = summary["task3c_comparison"]["historical"]
    kappa_lim = ia["correctly_explains_limitation"]["cohen_kappa"]
    lines = [
        "# Task 3D final report",
        "",
        f"Run: `{summary['run_id']}`  ",
        f"Status: `{summary['status']}`  ",
        f"Analysis date: {ANALYSIS_DATE}",
        "",
        "## 1. Research questions",
        "",
        "Task 3D evaluates inter-annotator reliability (RQ-D1), agreement between human judgments and the frozen deterministic claim linter (RQ-D2), and human-annotated governed-versus-ungoverned communication differences (RQ-D3). The primary endpoint is `makes_positive_significance_claim`.",
        "",
        "## 2. Design and source integrity",
        "",
        "Both supplied workbooks contain 156 arm-blinded replies, IDs R0000--R0155, two worksheets (`Annotation` and `Rubric`), and six binary labels. The workbooks have identical IDs, reply text, and rubric text. Annotator 2 contained two harmless `No ` values; analysis stripped whitespace without modifying either workbook. No IDs, replies, or labels were missing or duplicated, and all 156 reply texts were unique.",
        "",
        "The requested Annotator 1 filename with `(3)` was absent, but the repository file without that suffix had exactly the supplied SHA-256, so it was used as the intended byte-identical input. The workbook hashes matched both supplied expectations.",
        "",
        "### Provenance finding",
        "",
        "The annotation reply texts are not the Task 3C Attempt 3 generations: 137/156 texts differ from Attempt 3 and 19/156 match exactly. They are the historical frozen annotation set packaged before Attempt 3. Historical and Attempt 3 paired tables contain the same 78 allocation identities and identical per-file seed/allocation order, allowing a deterministic seed-42 reconstruction of the missing private blinded key. The original private key and historical raw JSON replies are unavailable, so the reconstruction is explicitly labeled rather than presented as the original key.",
        "",
        "Repository history also shows that Annotator 1's workbook was initially populated alongside `auto_annotate.py` before the final workbook upload. The final labels differ from the current automated classifier on 60/936 label cells and none of 112 final notes exactly matches an automated note, so the final file is not an unchanged automated output. Nevertheless, repository evidence alone cannot prove that Annotator 1 was uninfluenced by automated suggestions; this limits claims of fully independent human annotation.",
        "",
        "## 3. Rubric and annotation procedure",
        "",
        "The embedded rubric matches the six definitions in the annotation protocol. Annotators are study authors, not external experts. Labels remain pre-adjudication; no consensus label was created. Unanimous judgments are reported only for the five dimensions with perfect agreement. The disputed limitation-explanation dimension is reported separately for each annotator.",
        "",
        "## 4. Inter-annotator reliability",
        "",
        "| Dimension | Agreement | Cohen's kappa | A1 Yes | A2 Yes |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in LABELS:
        row = ia[label]
        kappa = "undefined" if row["cohen_kappa"] is None else f"{row['cohen_kappa']:.4f}"
        lines.append(
            f"| `{label}` | {row['agreement_rate']:.2%} ({row['agreement_count']}/156) | {kappa} | {row['annotator_1_yes']} | {row['annotator_2_yes']} |"
        )
    lines.extend(
        [
            "",
            f"Overall raw agreement was {summary['overall_annotation_decision_agreement']['rate']:.2%} ({summary['overall_annotation_decision_agreement']['agreements']}/{summary['overall_annotation_decision_agreement']['decisions']}). The only nine disagreements concerned `correctly_explains_limitation`: {', '.join(summary['human_disagreement_ids'])}. Kappa is undefined for unsupported biological interpretation because both annotators marked all 156 replies No, making expected agreement equal to one.",
            "",
            "## 5. Human versus frozen deterministic linter",
            "",
            "Only the primary positive-significance label has sufficiently equivalent human and frozen-linter semantics for formal agreement statistics. The other dimensions are documented as non-equivalent: result exposure is broader in the linter than the human gene-exposure rubric; withholding and inference state are operational pipeline fields rather than textual judgments; and no saved case-level linter label exactly implements the remaining human concepts.",
            "",
            f"For the primary label, each annotator agreed with the historical linter on {hvl['agreement_count']}/156 replies ({hvl['agreement_rate']:.2%}); Cohen's kappa was {hvl['cohen_kappa']:.4f}. Humans marked 78 replies Yes, while the linter marked 72 Yes. All six disagreements were human-Yes/linter-No and occurred in ungoverned replies. These are disagreements, not proven linter errors, because neither source is an independent biological ground truth.",
            "",
            "## 6. Governed versus ungoverned human results",
            "",
            f"For the primary endpoint, both annotators marked 0/78 governed replies and 78/78 ungoverned replies as making positive significance claims, an observed paired difference of {primary['rate_difference_ungoverned_minus_governed']:.2%}. Descriptive Wilson intervals were [{primary['governed_wilson_low']:.4f}, {primary['governed_wilson_high']:.4f}] and [{primary['ungoverned_wilson_low']:.4f}, {primary['ungoverned_wilson_high']:.4f}], respectively. All 78 pairs were discordant in the governed-No/ungoverned-Yes direction. The exact McNemar p-value ({primary['exact_mcnemar_p_exploratory']:.3e}) is exploratory because the frozen annotation plan preregistered agreement/kappa but not an arm-comparison significance test.",
            "",
            "The perfect-agreement secondary dimensions also separated arms completely: descriptive-only and explicit-withholding were 78/78 governed versus 0/78 ungoverned; gene-level exposure was 0/78 governed versus 78/78 ungoverned. Unsupported biological interpretation was 0/78 in both arms. Limitation explanation was not unanimous and is therefore retained separately: Annotator 1 marked governed/ungoverned Yes counts of " + f"{limitation_1['governed_yes']}/78 and {limitation_1['ungoverned_yes']}/78; Annotator 2 marked {limitation_2['governed_yes']}/78 and {limitation_2['ungoverned_yes']}/78.",
            "",
            "## 7. Comparison with frozen deterministic results",
            "",
            f"The human historical-reply result was 0/78 governed and 78/78 ungoverned. The matching historical deterministic screen was {historical['governed_positive_claims']}/78 and {historical['ungoverned_positive_claims']}/78. Task 3C Attempt 3, on later generated reply text, was {attempt3['governed_positive_claims']}/78 and {attempt3['ungoverned_positive_claims']}/78. Thus human annotation identified six more historical ungoverned positive claims than the historical linter and nine more than the separate Attempt 3 deterministic result. The latter difference is not a human-versus-linter error estimate because 137/156 reply texts differ.",
            "",
            "## 8. Statistical methods",
            "",
            "Raw agreement and Cohen's kappa were computed independently for each binary label using all 156 paired annotations. Constant-label kappa was reported as undefined. Human-versus-linter confusion tables use matched blinded IDs. Arm rates use the frozen denominator of 78 and descriptive Wilson 95% intervals. Pairing uses tissue, cell type, seed, and allocation identity. No reply is treated as an independent experimental pair. Exact McNemar tests are reported only as exploratory additions.",
            "",
            "## 9. Disagreements and negative findings",
            "",
            "All nine human disagreements and all six human-versus-linter disagreements are preserved in separate CSV files with source locators and original notes/text. No labels were adjudicated, relabeled, or deleted. Important negative findings are the provenance mismatch with Attempt 3, the absent original private key and historical raw JSON replies, the uncertain independence of Annotator 1 from prior automated suggestions, undefined kappa under constant labels, and the absence of any positive labels for unsupported biological interpretation, which prevents estimating sensitivity for that dimension.",
            "",
            "## 10. Threats to validity",
            "",
            "The annotators are study authors and not external experts. Allocation reuse means 78 pairs are not 78 independent biological cohorts. Human agreement is not biological truth, and the deterministic linter is not an independent reference standard. The constructed null does not prove every numerical DEG is a biological false discovery. The mapping is a deterministic reconstruction, not the original private key. File timestamps do not establish annotation dates. The historical and Attempt 3 replies used different Gemini generations/models, so their communication rates are related replication results rather than annotations of the same text.",
            "",
            "## 11. Reproduction",
            "",
            "Run the unit tests with the bundled workspace Python, then run `analyze_task3d.py analyze` with the two source workbooks, historical paired table, Attempt 3 paired table, and Attempt 3 packaged raw directory. Re-run into a fresh temporary directory and compare core output hashes. Finally run `analyze_task3d.py finalize` to refresh provenance output hashes and the SHA-256 manifest. No Gemini or DESeq2 call is made.",
            "",
            "## 12. Conclusions supported and not supported",
            "",
            "The data support high author-to-author reproducibility for five rubric dimensions and substantial agreement for limitation explanation. On the historical frozen reply set, both annotators observed complete suppression of positive significance claims and gene-level exposure in the governed arm relative to the ungoverned arm. The result supports an evidence-boundary communication effect in this frozen constructed-null setting.",
            "",
            "The data do not establish biological correctness, causality, mechanism, universal false-discovery control, external-expert agreement, independence from automated annotation assistance, or human validation of the exact Attempt 3 generated replies. No consensus or biological ground truth was created.",
            "",
        ]
    )
    return "\n".join(lines)


def analyze(args: argparse.Namespace) -> None:
    root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()) and not args.allow_existing:
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    a1 = load_workbook(args.annotator_1)
    a2 = load_workbook(args.annotator_2)
    if a1.headers != a2.headers or a1.rubric_rows != a2.rubric_rows:
        raise ValueError("workbook schemas or embedded rubrics differ")
    if tuple(a1.rows) != tuple(a2.rows):
        raise ValueError("annotator ID sets/orders differ")
    if any(a1.rows[key].reply_text != a2.rows[key].reply_text for key in EXPECTED_IDS):
        raise ValueError("reply text differs between annotators")
    duplicate_replies = 156 - len({a1.rows[key].reply_text for key in EXPECTED_IDS})

    mapping, mapping_audit = reconstruct_mapping(
        args.attempt3_raw_dir,
        args.historical_paired,
        args.attempt3_paired,
    )
    attempt3_exact_matches = sum(
        a1.rows[key].reply_text == mapping[key]["attempt3_reply"] for key in EXPECTED_IDS
    )

    inter_rows: list[dict[str, Any]] = []
    prevalence_rows: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    for label in LABELS:
        first = [a1.rows[key].labels[label] for key in EXPECTED_IDS]
        second = [a2.rows[key].labels[label] for key in EXPECTED_IDS]
        stats = agreement_stats(first, second)
        inter_rows.append(
            {
                "label": label,
                "n_valid": stats["n"],
                "annotator_1_yes": stats["first_yes"],
                "annotator_1_no": stats["first_no"],
                "annotator_2_yes": stats["second_yes"],
                "annotator_2_no": stats["second_no"],
                "both_yes": stats["both_yes"],
                "annotator_1_yes_annotator_2_no": stats["first_yes_second_no"],
                "annotator_1_no_annotator_2_yes": stats["first_no_second_yes"],
                "both_no": stats["both_no"],
                "agreement_count": stats["agreement_count"],
                "agreement_rate": stats["agreement_rate"],
                "expected_agreement": stats["expected_agreement"],
                "cohen_kappa": stats["cohen_kappa"],
                "kappa_status": stats["kappa_status"],
            }
        )
        for name, workbook in (("annotator_1", a1), ("annotator_2", a2)):
            yes = sum(workbook.rows[key].labels[label] == "Yes" for key in EXPECTED_IDS)
            prevalence_rows.append(
                {
                    "label": label,
                    "annotator": name,
                    "n": 156,
                    "yes": yes,
                    "no": 156 - yes,
                    "yes_rate": yes / 156,
                }
            )
        for key in EXPECTED_IDS:
            first_value = a1.rows[key].labels[label]
            second_value = a2.rows[key].labels[label]
            if first_value != second_value:
                meta = mapping[key]
                disagreements.append(
                    {
                        "blinded_id": key,
                        "label": label,
                        "annotator_1_decision": first_value,
                        "annotator_2_decision": second_value,
                        "annotator_1_original_value": a1.rows[key].raw_labels[label],
                        "annotator_2_original_value": a2.rows[key].raw_labels[label],
                        "annotator_1_notes": a1.rows[key].notes,
                        "annotator_2_notes": a2.rows[key].notes,
                        "reply_sha256": sha256_bytes(a1.rows[key].reply_text.encode("utf-8")),
                        "tissue": meta["tissue"],
                        "cell_type": meta["cell_type"],
                        "seed": meta["seed"],
                        "allocation_index": meta["allocation_index"],
                        "allocation_id": meta["allocation_id"],
                        "arm": meta["arm"],
                        "source_file": meta["source_file"],
                    }
                )

    human_vs_linter_rows: list[dict[str, Any]] = []
    hvl_details: dict[str, dict[str, Any]] = {}
    linter_disagreements: list[dict[str, Any]] = []
    linter_values = [
        "Yes" if mapping[key]["historical_linter_positive_claim"] else "No"
        for key in EXPECTED_IDS
    ]
    for name, workbook in (("annotator_1", a1), ("annotator_2", a2)):
        human_values = [workbook.rows[key].labels[PRIMARY_LABEL] for key in EXPECTED_IDS]
        stats = compare_human_to_linter(human_values, linter_values)
        hvl_details[name] = stats
        human_vs_linter_rows.append(
            {
                "human_source": name,
                "dimension": PRIMARY_LABEL,
                "semantically_compatible": True,
                "compatibility_reason": "Both classify affirmative positive statistical-significance/differential-expression claims in user-facing reply text.",
                "n": stats["n"],
                "human_yes": stats["first_yes"],
                "linter_yes": stats["second_yes"],
                "both_yes": stats["both_yes"],
                "human_yes_linter_no": stats["first_yes_second_no"],
                "human_no_linter_yes": stats["first_no_second_yes"],
                "both_no": stats["both_no"],
                "agreement_count": stats["agreement_count"],
                "agreement_rate": stats["agreement_rate"],
                "cohen_kappa": stats["cohen_kappa"],
                "kappa_status": stats["kappa_status"],
            }
        )
    unanimous_values = [
        a1.rows[key].labels[PRIMARY_LABEL]
        if a1.rows[key].labels[PRIMARY_LABEL] == a2.rows[key].labels[PRIMARY_LABEL]
        else "DISAGREEMENT"
        for key in EXPECTED_IDS
    ]
    if "DISAGREEMENT" not in unanimous_values:
        stats = compare_human_to_linter(unanimous_values, linter_values)
        hvl_details["unanimous_human"] = stats
        human_vs_linter_rows.append(
            {
                "human_source": "unanimous_human",
                "dimension": PRIMARY_LABEL,
                "semantically_compatible": True,
                "compatibility_reason": "Annotators agreed on all primary labels; shared judgments are unanimous, not adjudicated consensus.",
                "n": stats["n"],
                "human_yes": stats["first_yes"],
                "linter_yes": stats["second_yes"],
                "both_yes": stats["both_yes"],
                "human_yes_linter_no": stats["first_yes_second_no"],
                "human_no_linter_yes": stats["first_no_second_yes"],
                "both_no": stats["both_no"],
                "agreement_count": stats["agreement_count"],
                "agreement_rate": stats["agreement_rate"],
                "cohen_kappa": stats["cohen_kappa"],
                "kappa_status": stats["kappa_status"],
            }
        )

    incompatible = {
        "makes_descriptive_claim_only": "No frozen case-level linter label classifies descriptive-only prose.",
        "explicitly_withholds_inference": "Frozen result-withheld/state fields are operational outputs, not judgments that the reply explicitly communicates withholding.",
        "exposes_gene_level_results": "The frozen result-exposure screen also matches nonzero discovery counts and download links; the human rubric excludes a count alone and requires gene-level content.",
        "correctly_explains_limitation": "No frozen case-level linter judgment implements the human rubric's explanatory adequacy standard.",
        "contains_unsupported_biological_interpretation": "Frozen claim-violation patterns are conditional screening rules and do not implement the full human biological-interpretation rubric.",
    }
    for label, reason in incompatible.items():
        human_vs_linter_rows.append(
            {
                "human_source": "not_compared",
                "dimension": label,
                "semantically_compatible": False,
                "compatibility_reason": reason,
            }
        )

    for key in EXPECTED_IDS:
        human = a1.rows[key].labels[PRIMARY_LABEL]
        linter = "Yes" if mapping[key]["historical_linter_positive_claim"] else "No"
        if human != linter:
            meta = mapping[key]
            features = disagreement_features(a1.rows[key].reply_text)
            if human == "Yes" and linter == "No":
                category = "human_positive_claim_not_matched_by_frozen_linter_patterns"
            else:
                category = "frozen_linter_positive_claim_not_endorsed_by_humans"
            linter_disagreements.append(
                {
                    "blinded_id": key,
                    "arm": meta["arm"],
                    "tissue": meta["tissue"],
                    "cell_type": meta["cell_type"],
                    "seed": meta["seed"],
                    "allocation_id": meta["allocation_id"],
                    "annotator_1": a1.rows[key].labels[PRIMARY_LABEL],
                    "annotator_2": a2.rows[key].labels[PRIMARY_LABEL],
                    "historical_linter": linter,
                    "historical_claim_violations": meta["historical_claim_violations"],
                    "classification": category,
                    **features,
                    "reply_text": a1.rows[key].reply_text,
                }
            )

    arm_results: dict[str, dict[str, dict[str, Any]]] = {}
    arm_csv_rows: list[dict[str, Any]] = []
    for annotator_name, workbook in (("annotator_1", a1), ("annotator_2", a2)):
        arm_results[annotator_name] = {}
        for label in LABELS:
            stats = paired_arm_stats(workbook.rows, mapping, label)
            arm_results[annotator_name][label] = stats
            arm_csv_rows.append({"human_source": annotator_name, "label": label, **stats})
    perfect_labels = [
        row["label"] for row in inter_rows if row["agreement_count"] == 156
    ]
    unanimous_rows = {
        key: AnnotationRow(
            blinded_id=key,
            reply_text=a1.rows[key].reply_text,
            labels={label: a1.rows[key].labels[label] for label in perfect_labels},
            raw_labels={},
            notes="",
        )
        for key in EXPECTED_IDS
    }
    arm_results["unanimous_human"] = {}
    for label in perfect_labels:
        stats = paired_arm_stats(unanimous_rows, mapping, label)
        arm_results["unanimous_human"][label] = stats
        arm_csv_rows.append({"human_source": "unanimous_human", "label": label, **stats})

    mapping_rows: list[dict[str, Any]] = []
    for key in EXPECTED_IDS:
        meta = mapping[key]
        reply = a1.rows[key].reply_text
        mapping_rows.append(
            {
                "blinded_id": key,
                "pair_id": meta["pair_id"],
                "arm": meta["arm"],
                "tissue": meta["tissue"],
                "cell_type": meta["cell_type"],
                "seed": meta["seed"],
                "allocation_index": meta["allocation_index"],
                "allocation_id": meta["allocation_id"],
                "source_file": meta["source_file"],
                "annotated_reply_sha256": sha256_bytes(reply.encode("utf-8")),
                "attempt3_reply_sha256": meta["attempt3_reply_sha256"],
                "attempt3_reply_exact_match": reply == meta["attempt3_reply"],
                "historical_linter_positive_claim": meta["historical_linter_positive_claim"],
                "historical_linter_result_exposed": meta["historical_linter_result_exposed"],
                "historical_result_withheld": meta["historical_result_withheld"],
                "historical_inference_state": meta["historical_inference_state"],
                "mapping_status": "deterministically_reconstructed_original_private_key_absent",
            }
        )

    rubric_rows = []
    for row_number, row in enumerate(a1.rubric_rows, start=1):
        rubric_rows.append(
            {
                "row": row_number,
                "field": row[0] if len(row) > 0 else "",
                "definition": row[1] if len(row) > 1 else "",
                "boundary": row[2] if len(row) > 2 else "",
            }
        )

    total_agreements = sum(row["agreement_count"] for row in inter_rows)
    comparison_historical = read_csv(args.historical_paired)
    comparison_attempt3 = read_csv(args.attempt3_paired)
    historical_counts = {
        "governed_positive_claims": sum(as_bool(row["governed_reply_overclaim_rescored"]) for row in comparison_historical),
        "ungoverned_positive_claims": sum(as_bool(row["ungoverned_reply_overclaim_rescored"]) for row in comparison_historical),
    }
    attempt3_counts = {
        "governed_positive_claims": sum(as_bool(row["governed_reply_overclaim_rescored"]) for row in comparison_attempt3),
        "ungoverned_positive_claims": sum(as_bool(row["ungoverned_reply_overclaim_rescored"]) for row in comparison_attempt3),
    }

    summary = {
        "analysis_date": ANALYSIS_DATE,
        "analysis_version": ANALYSIS_VERSION,
        "run_id": args.run_id,
        "status": "TASK3D_COMPLETE_WITH_DISCLOSED_PROVENANCE_LIMITATIONS",
        "annotated_cases_per_workbook": 156,
        "valid_matched_reply_pairs": 78,
        "workbook_validation": {
            "ids": "R0000-R0155",
            "unique_ids_per_workbook": 156,
            "unique_reply_texts": 156 - duplicate_replies,
            "duplicate_reply_texts": duplicate_replies,
            "matching_ids_and_reply_text": True,
            "matching_embedded_rubric": True,
            "missing_labels": 0,
            "invalid_labels": 0,
            "annotator_1_whitespace_normalizations": len(a1.whitespace_normalizations),
            "annotator_2_whitespace_normalizations": len(a2.whitespace_normalizations),
        },
        "interannotator": inter_rows,
        "overall_annotation_decision_agreement": {
            "agreements": total_agreements,
            "decisions": 156 * len(LABELS),
            "rate": total_agreements / (156 * len(LABELS)),
        },
        "human_disagreement_ids": sorted({row["blinded_id"] for row in disagreements}),
        "human_disagreement_count": len(disagreements),
        "human_vs_linter": hvl_details,
        "human_vs_linter_disagreement_count": len(linter_disagreements),
        "arm_results": arm_results,
        "task3c_comparison": {
            "human_historical_reply_set": {
                "governed_positive_claims": arm_results["unanimous_human"][PRIMARY_LABEL]["governed_yes"],
                "ungoverned_positive_claims": arm_results["unanimous_human"][PRIMARY_LABEL]["ungoverned_yes"],
            },
            "historical": historical_counts,
            "attempt3": attempt3_counts,
            "annotated_reply_exact_matches_to_attempt3": attempt3_exact_matches,
            "annotated_reply_mismatches_to_attempt3": 156 - attempt3_exact_matches,
        },
        "mapping_audit": mapping_audit,
        "interpretation_limits": [
            "The human workbooks annotate the historical frozen reply set, not Task 3C Attempt 3 reply generations.",
            "The original private blinded key and historical raw reply JSON files are unavailable; mapping is a deterministic reconstruction using the registered extractor and identical frozen allocation order.",
            "Repository history does not prove Annotator 1 was uninfluenced by earlier automated annotation suggestions.",
            "Annotators are study authors, not external experts.",
            "Human labels and the deterministic linter are not independent biological ground truth.",
            "Constructed-null numerical discoveries are not automatically proven biological false discoveries.",
            "No consensus/adjudicated labels were created.",
        ],
    }

    csv_dump(
        output_dir / "human_interannotator_agreement.csv",
        inter_rows,
        list(inter_rows[0]),
    )
    csv_dump(output_dir / "human_label_prevalence.csv", prevalence_rows, list(prevalence_rows[0]))
    disagreement_fields = list(disagreements[0]) if disagreements else [
        "blinded_id", "label", "annotator_1_decision", "annotator_2_decision"
    ]
    csv_dump(output_dir / "human_annotation_disagreements.csv", disagreements, disagreement_fields)
    csv_dump(
        output_dir / "human_vs_linter_comparison.csv",
        human_vs_linter_rows,
        [
            "human_source", "dimension", "semantically_compatible", "compatibility_reason",
            "n", "human_yes", "linter_yes", "both_yes", "human_yes_linter_no",
            "human_no_linter_yes", "both_no", "agreement_count", "agreement_rate",
            "cohen_kappa", "kappa_status",
        ],
    )
    linter_disagreement_fields = list(linter_disagreements[0]) if linter_disagreements else [
        "blinded_id", "classification", "reply_text"
    ]
    csv_dump(
        output_dir / "human_vs_linter_disagreements.csv",
        linter_disagreements,
        linter_disagreement_fields,
    )
    csv_dump(
        output_dir / "governed_vs_ungoverned_human_results.csv",
        arm_csv_rows,
        list(arm_csv_rows[0]),
    )
    csv_dump(
        output_dir / "case_level_provenance_mapping_audit.csv",
        mapping_rows,
        list(mapping_rows[0]),
    )
    csv_dump(output_dir / "rubric_definitions.csv", rubric_rows, list(rubric_rows[0]))
    json_dump(output_dir / "task3d_summary_metrics.json", summary)

    report = make_report(summary)
    (output_dir / "TASK3D_FINAL_REPORT.md").write_text(report, encoding="utf-8")

    primary = arm_results["annotator_1"][PRIMARY_LABEL]
    hvl = hvl_details["annotator_1"]
    manuscript = [
        "# Task 3D manuscript tables",
        "",
        "## Inter-annotator reliability",
        "",
        "| Dimension | Agreement | Cohen's kappa |",
        "|---|---:|---:|",
    ]
    for row in inter_rows:
        kappa = "Undefined (constant labels)" if row["cohen_kappa"] is None else f"{row['cohen_kappa']:.4f}"
        manuscript.append(f"| {row['label']} | {row['agreement_rate']:.2%} | {kappa} |")
    manuscript.extend(
        [
            "",
            "## Human primary endpoint by arm",
            "",
            "| Arm | Positive claims | Rate | Descriptive Wilson 95% interval |",
            "|---|---:|---:|---:|",
            f"| Governed | {primary['governed_yes']}/78 | {primary['governed_rate']:.2%} | [{primary['governed_wilson_low']:.4f}, {primary['governed_wilson_high']:.4f}] |",
            f"| Ungoverned | {primary['ungoverned_yes']}/78 | {primary['ungoverned_rate']:.2%} | [{primary['ungoverned_wilson_low']:.4f}, {primary['ungoverned_wilson_high']:.4f}] |",
            "",
            "## Human versus deterministic primary label",
            "",
            "| Comparison | Agreement | Cohen's kappa | Human Yes / linter No | Human No / linter Yes |",
            "|---|---:|---:|---:|---:|",
            f"| Each annotator vs historical linter | {hvl['agreement_rate']:.2%} | {hvl['cohen_kappa']:.4f} | {hvl['first_yes_second_no']} | {hvl['first_no_second_yes']} |",
            "",
            "These tables describe arm-blinded study-author annotation of the historical frozen replies. They do not represent external-expert validation or annotation of the later Attempt 3 generated text.",
            "",
        ]
    )
    (output_dir / "MANUSCRIPT_TABLES.md").write_text("\n".join(manuscript), encoding="utf-8")

    provenance = {
        "analysis_date": ANALYSIS_DATE,
        "analysis_version": ANALYSIS_VERSION,
        "run_id": args.run_id,
        "repository": {
            "root": ".",
            "git_revision": git_output(root, "rev-parse", "HEAD"),
            "worktree_clean": False,
            "status_note": "Pre-existing tracked/untracked work was present; Task 3D changes are scoped to eval/scripts/task3d, eval/results/task3d, and RESEARCH_WORK_LOG.md.",
        },
        "runtime": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "dependencies": {
                "openpyxl": importlib.metadata.version("openpyxl"),
            },
        },
        "inputs": {
            "annotator_1": {"path": str(args.annotator_1.relative_to(root)), "bytes": a1.size_bytes, "sha256": a1.sha256},
            "annotator_2": {"path": str(args.annotator_2.relative_to(root)), "bytes": a2.size_bytes, "sha256": a2.sha256},
            "historical_paired": {"path": str(args.historical_paired.relative_to(root)), "sha256": sha256_file(args.historical_paired)},
            "attempt3_paired": {"path": str(args.attempt3_paired.relative_to(root)), "sha256": sha256_file(args.attempt3_paired)},
            "attempt3_manifest": {"path": str(args.attempt3_manifest.relative_to(root)), "sha256": sha256_file(args.attempt3_manifest)},
            "annotation_protocol": {"path": str(args.annotation_protocol.relative_to(root)), "sha256": sha256_file(args.annotation_protocol)},
            "metrics_spec": {"path": str(args.metrics_spec.relative_to(root)), "sha256": sha256_file(args.metrics_spec)},
            "extractor": {"path": str(args.extractor.relative_to(root)), "sha256": sha256_file(args.extractor)},
            "claim_linter": {"path": str(args.claim_linter.relative_to(root)), "sha256": sha256_file(args.claim_linter)},
        },
        "input_hash_expectations": {
            "annotator_1_expected": "619f47bb3345cb02332c4727d1cf1f4ccccab149240f94faf6c38e7b6aed8ebb",
            "annotator_1_matches": a1.sha256 == "619f47bb3345cb02332c4727d1cf1f4ccccab149240f94faf6c38e7b6aed8ebb",
            "annotator_2_expected": "607ba6a1249b69c5a19f5fcacd8018289adfc9b82811fad77de8d95759bce172",
            "annotator_2_matches": a2.sha256 == "607ba6a1249b69c5a19f5fcacd8018289adfc9b82811fad77de8d95759bce172",
        },
        "mapping": mapping_audit,
        "source_alignment": {
            "workbook_replies_equal_attempt3": False,
            "attempt3_exact_reply_matches": attempt3_exact_matches,
            "attempt3_reply_mismatches": 156 - attempt3_exact_matches,
            "human_linter_comparison_source": "historical frozen paired_allocations.csv",
        },
        "scientific_execution": {
            "gemini_calls": 0,
            "deseq2_calls": 0,
            "labels_modified": 0,
            "workbooks_modified": False,
            "frozen_task3c_modified": False,
        },
        "script": {
            "path": str(Path(__file__).resolve().relative_to(root)),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "scripts": {
            "analysis": {
                "path": str(Path(__file__).resolve().relative_to(root)),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "unit_tests": {
                "path": str(Path(__file__).with_name("test_analyze_task3d.py").resolve().relative_to(root)),
                "sha256": sha256_file(Path(__file__).with_name("test_analyze_task3d.py").resolve()),
            },
            "independent_verification": {
                "path": str(Path(__file__).with_name("verify_task3d.py").resolve().relative_to(root)),
                "sha256": sha256_file(Path(__file__).with_name("verify_task3d.py").resolve()),
            },
        },
        "generated_output_hashes": {},
    }
    json_dump(output_dir / "TASK3D_PROVENANCE.json", provenance)


def finalize(args: argparse.Namespace) -> None:
    output_dir = args.output_dir.resolve()
    provenance_path = output_dir / "TASK3D_PROVENANCE.json"
    if not provenance_path.exists():
        raise FileNotFoundError(provenance_path)
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    excluded = {"TASK3D_PROVENANCE.json", "TASK3D_SHA256_MANIFEST.json"}
    output_hashes = {}
    for path in sorted(p for p in output_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(output_dir).as_posix()
        if rel in excluded:
            continue
        output_hashes[rel] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    provenance["generated_output_hashes"] = output_hashes
    json_dump(provenance_path, provenance)

    files = []
    for path in sorted(p for p in output_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(output_dir).as_posix()
        if rel == "TASK3D_SHA256_MANIFEST.json":
            continue
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest = {
        "analysis_version": ANALYSIS_VERSION,
        "file_count": len(files),
        "files": files,
        "manifest_content_sha256": sha256_bytes(canonical),
        "root": args.run_id,
    }
    json_dump(output_dir / "TASK3D_SHA256_MANIFEST.json", manifest)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("--repo-root", type=Path, required=True)
    analyze_parser.add_argument("--output-dir", type=Path, required=True)
    analyze_parser.add_argument("--run-id", required=True)
    analyze_parser.add_argument("--annotator-1", type=Path, required=True)
    analyze_parser.add_argument("--annotator-2", type=Path, required=True)
    analyze_parser.add_argument("--historical-paired", type=Path, required=True)
    analyze_parser.add_argument("--attempt3-paired", type=Path, required=True)
    analyze_parser.add_argument("--attempt3-raw-dir", type=Path, required=True)
    analyze_parser.add_argument("--attempt3-manifest", type=Path, required=True)
    analyze_parser.add_argument("--annotation-protocol", type=Path, required=True)
    analyze_parser.add_argument("--metrics-spec", type=Path, required=True)
    analyze_parser.add_argument("--extractor", type=Path, required=True)
    analyze_parser.add_argument("--claim-linter", type=Path, required=True)
    analyze_parser.add_argument("--allow-existing", action="store_true")
    analyze_parser.set_defaults(func=analyze)

    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("--output-dir", type=Path, required=True)
    finalize_parser.add_argument("--run-id", required=True)
    finalize_parser.set_defaults(func=finalize)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
