#!/usr/bin/env python3
"""Evaluation-only runner for the frozen V1 Task-3A governance battery.

This module materializes only the registered synthetic fixtures, calls the
unchanged production routing/governance/statistical/rendering entry points,
captures their outputs, and applies the frozen V1 scoring rules.  It is not a
production dependency and must never be used to alter a production decision.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
EVAL = ROOT / "eval"
for path in (str(BACKEND), str(EVAL)):
    if path not in sys.path:
        sys.path.insert(0, path)

REGISTERED_IDS = tuple(f"GOV-{number:02d}" for number in range(1, 11))
REQUIRED_CASE_FIELDS = frozenset(
    {
        "id",
        "dataset",
        "fixture_recipe",
        "data_checksum_sha256",
        "prompt",
        "expected_route",
        "expected_gate1",
        "expected_gate2",
        "expected_inference_state",
        "expected_refusal_or_reporting_behavior",
        "expected_artifacts",
        "reference_label_source",
        "scoring_rule",
        "status",
        "reason",
    }
)
FROZEN_INPUT_NAMES = (
    "EXPERIMENT_CASES_V1.json",
    "EXPERIMENT_PROTOCOL_V1.md",
    "METRICS_SPEC_V1.md",
    "EXECUTION_ENVIRONMENT_V1.md",
    "TASK2_PIP_FREEZE.txt",
)
WITHHOLDING_CASES = frozenset(
    {"GOV-01", "GOV-02", "GOV-03", "GOV-04", "GOV-05", "GOV-07", "GOV-08", "GOV-10"}
)
VALID_GATE1_CASES = frozenset({"GOV-06", "GOV-08", "GOV-09", "GOV-10"})
NONPOSITIVE_LICENSE_CASES = frozenset(set(REGISTERED_IDS) - {"GOV-09"})
UNIT_ELIGIBLE_CASES = frozenset(set(REGISTERED_IDS) - {"GOV-07"})
GATE1_ELIGIBLE_CASES = UNIT_ELIGIBLE_CASES
GATE2_ELIGIBLE_CASES = VALID_GATE1_CASES
COUNT_SOURCE_ELIGIBLE_CASES = UNIT_ELIGIBLE_CASES
LIMITATION_CONCEPTS = {
    "GOV-01": (("raw",), ("integer",), ("not executed", "not run")),
    "GOV-02": (("cell",), ("replicate", "pseudoreplication"), ("not executed", "not run")),
    "GOV-03": (("sample",), ("covariate",), ("cannot", "invalid")),
    "GOV-04": (("batch",), ("perfect", "separated"), ("cannot", "not attributed")),
    "GOV-05": (("replicate",), ("3", "three"), ("2", "two")),
    "GOV-06": (
        (
            "non-significance is not equivalence",
            "not statistically significant is not equivalence",
            "does not prove absence",
            "does not establish absence",
        ),
    ),
    "GOV-07": (("two", "2"), ("group", "contrast")),
    "GOV-08": (("one donor", "single donor"), ("driven", "drives")),
    "GOV-10": (
        ("3-per-group", "three-per-group", "3 samples per group", "three samples per group"),
        ("4-per-group", "four-per-group", "4 samples per group", "four samples per group"),
        ("stability",),
    ),
}


class RegistryValidationError(ValueError):
    """Raised before execution when the frozen registry is malformed."""


class PreflightError(RuntimeError):
    """Raised before scientific execution when a required preflight fails."""


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp_name = handle.name
    Path(temp_name).replace(path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(json_safe(value), indent=2, sort_keys=True) + "\n")


def reserve_output_directory(path: Path) -> None:
    """Atomically reserve a previously nonexistent run directory."""
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(f"Refusing to overwrite existing run directory: {path}") from exc


def load_registry(path: Path, *, require_v1_ids: bool = True) -> tuple[dict, list[dict], str]:
    """Load and validate without mutating the registry or any case object."""
    before = path.read_bytes()
    digest = sha256_bytes(before)
    try:
        registry = json.loads(before.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryValidationError(f"Registry is not valid UTF-8 JSON: {exc}") from exc
    cases = registry.get("governance_battery")
    if not isinstance(cases, list) or not cases:
        raise RegistryValidationError("governance_battery must be a nonempty list")
    ids: list[str] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise RegistryValidationError(f"Case {index} is not an object")
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        if missing:
            raise RegistryValidationError(f"Case {index} missing registered fields: {missing}")
        if not isinstance(case["id"], str) or not case["id"]:
            raise RegistryValidationError(f"Case {index} has invalid id")
        if not isinstance(case["fixture_recipe"], dict):
            raise RegistryValidationError(f"{case['id']} fixture_recipe is not an object")
        if not isinstance(case["expected_artifacts"], list) or not case["expected_artifacts"]:
            raise RegistryValidationError(f"{case['id']} expected_artifacts must be a nonempty list")
        recipe_digest = sha256_bytes(canonical_json(case["fixture_recipe"]).encode("utf-8"))
        if recipe_digest != case["data_checksum_sha256"]:
            raise RegistryValidationError(
                f"{case['id']} canonical recipe digest mismatch: {recipe_digest}"
            )
        ids.append(case["id"])
    if len(ids) != len(set(ids)):
        raise RegistryValidationError("Case IDs are not unique")
    if require_v1_ids and tuple(ids) != REGISTERED_IDS:
        raise RegistryValidationError(
            f"V1 case IDs/order changed: expected {REGISTERED_IDS}, observed {tuple(ids)}"
        )
    if path.read_bytes() != before:
        raise RegistryValidationError("Registry changed while it was being read")
    return registry, cases, digest


def _run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def run_preflight(registry: dict, registry_digest: str) -> dict:
    pip_check = _run_checked([sys.executable, "-m", "pip", "check"])
    freeze = _run_checked([sys.executable, "-m", "pip", "freeze", "--all"])
    expected_freeze = (ROOT / "TASK2_PIP_FREEZE.txt").read_text(encoding="utf-8").replace("\r\n", "\n")
    actual_freeze = freeze.stdout.replace("\r\n", "\n")
    mpl = os.getenv("MPLCONFIGDIR")
    report_model_active = "REPORT_MODEL" in os.environ
    report_key_active = "REPORT_GEMINI_API_KEY" in os.environ
    git_branch = _run_checked(["git", "branch", "--show-current"])
    git_revision = _run_checked(["git", "rev-parse", "HEAD"])
    git_status = _run_checked(["git", "status", "--short", "--untracked-files=all"])
    required_model = registry.get("model_freeze", {}).get("model_identifier")
    checks = {
        "cpython": platform.python_implementation() == "CPython",
        "python_3_11_9": platform.python_version() == "3.11.9",
        "python_executable_is_task2": Path(sys.executable).resolve() == (ROOT / ".venv-task2/bin/python").resolve(),
        "pip_check": pip_check.returncode == 0,
        "pip_freeze_exact_after_crlf_normalization": freeze.returncode == 0 and actual_freeze == expected_freeze,
        "gemini_api_key_present": bool(os.getenv("GEMINI_API_KEY")),
        "gemini_model_exact": os.getenv("GEMINI_MODEL") == "gemini-3.5-flash" == required_model,
        "report_model_override_inactive": not report_model_active,
        "report_key_override_inactive": not report_key_active,
        "mplconfigdir_writable": bool(mpl and Path(mpl).is_dir() and os.access(mpl, os.W_OK)),
        "registered_revision": git_revision.stdout.strip() == registry.get("root_git_revision_at_registration"),
        "registry_digest": registry_digest == sha256_file(ROOT / "EXPERIMENT_CASES_V1.json"),
    }
    return {
        "checked_at": utc_now(),
        "passed": all(checks.values()),
        "checks": checks,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable": str(Path(sys.executable).resolve()),
        },
        "pip_check_stdout": pip_check.stdout.strip(),
        "pip_check_stderr": pip_check.stderr.strip(),
        "credential": {
            "gemini_api_key_present": bool(os.getenv("GEMINI_API_KEY")),
            "value_accessed_or_recorded": False,
        },
        "model": {
            "gemini_model": os.getenv("GEMINI_MODEL", "UNSET"),
            "report_model_override_active": report_model_active,
            "report_key_override_active": report_key_active,
            "agent_temperature": registry.get("model_freeze", {}).get("agent_temperature"),
            "planner_temperature": registry.get("model_freeze", {}).get("planner_temperature"),
            "report_temperature": registry.get("model_freeze", {}).get("report_temperature"),
            "top_p": registry.get("model_freeze", {}).get("top_p"),
            "top_k": registry.get("model_freeze", {}).get("top_k"),
            "thinking_configuration": registry.get("model_freeze", {}).get("thinking_configuration"),
            "max_output_tokens": registry.get("model_freeze", {}).get("max_output_tokens"),
        },
        "matplotlib": {"mplconfigdir": mpl, "writable": checks["mplconfigdir_writable"]},
        "repository": {
            "branch": git_branch.stdout.strip(),
            "revision": git_revision.stdout.strip(),
            "dirty": bool(git_status.stdout.strip()),
            "status_porcelain": git_status.stdout.splitlines(),
            "status_stderr": git_status.stderr.strip(),
        },
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "frozen_file_sha256": {
            name: sha256_file(ROOT / name) for name in FROZEN_INPUT_NAMES if (ROOT / name).exists()
        },
    }


def _distribute_total(total: int, cells: int) -> list[int]:
    base, remainder = divmod(int(total), cells)
    return [base + (1 if index < remainder else 0) for index in range(cells)]


def materialize_fixture(case: dict):
    """Materialize the registered recipe without changing its seed or fields."""
    import anndata as ad
    import numpy as np
    import pandas as pd

    recipe = case["fixture_recipe"]
    observed_digest = sha256_bytes(canonical_json(recipe).encode("utf-8"))
    if observed_digest != case["data_checksum_sha256"]:
        raise RegistryValidationError(f"{case['id']} recipe digest changed before materialization")
    seed = int(recipe["seed"])
    rng = np.random.default_rng(seed)
    kind = recipe["kind"]
    groups = recipe["groups"]
    genes = int(recipe["genes"])
    cells_per_sample = recipe.get("cells_per_sample")
    rows: list[dict[str, Any]] = []
    sample_groups: list[tuple[str, str]] = []

    if kind == "missing_sample_identifier":
        for group, n_cells in groups.items():
            for _ in range(int(n_cells)):
                rows.append({"condition": str(group), "cell_type": "B cell"})
    else:
        for group, n_samples in groups.items():
            for sample_number in range(int(n_samples)):
                sample = f"{group}_{sample_number + 1}"
                sample_groups.append((sample, str(group)))
                for _ in range(int(cells_per_sample)):
                    row = {"sample_id": sample, "condition": str(group), "cell_type": "B cell"}
                    batch_map = recipe.get("batch_map") or {}
                    if batch_map:
                        row["batch"] = batch_map[str(group)]
                    elif recipe.get("batch") == "balanced":
                        row["batch"] = f"batch_{'A' if sample_number % 2 == 0 else 'B'}"
                    rows.append(row)

    obs = pd.DataFrame(rows, index=[f"cell_{index:05d}" for index in range(len(rows))])
    gene_names = [f"gene_{index:03d}" for index in range(genes)]
    if kind in {"one_donor_driven_gate2", "stable_multi_donor_gate2", "replicate_threshold_boundary"}:
        gene_names = ["signal", "background"]
        matrix_rows: list[list[int]] = []
        for sample_index, _ in enumerate(sample_groups):
            signal = _distribute_total(recipe["signal_counts"][sample_index], int(cells_per_sample))
            background = _distribute_total(100, int(cells_per_sample))
            matrix_rows.extend([[signal[i], background[i]] for i in range(int(cells_per_sample))])
        counts = np.asarray(matrix_rows, dtype=np.int64)
    elif kind == "valid_balanced_null":
        n_templates = int(groups["control"])
        template_totals = rng.poisson(120, size=(n_templates, genes)).astype(np.int64) + 20
        matrix_rows = []
        for sample_index, _ in enumerate(sample_groups):
            donor_template = sample_index % n_templates
            per_gene = [
                _distribute_total(int(template_totals[donor_template, gene]), int(cells_per_sample))
                for gene in range(genes)
            ]
            matrix_rows.extend(
                [[per_gene[gene][cell] for gene in range(genes)] for cell in range(int(cells_per_sample))]
            )
        counts = np.asarray(matrix_rows, dtype=np.int64)
    else:
        counts = rng.poisson(4, size=(len(obs), genes)).astype(np.int64)

    if kind == "invalid_normalized_only":
        x_matrix = np.log1p(counts.astype(float))
    else:
        x_matrix = counts.copy()
    adata = ad.AnnData(X=x_matrix, obs=obs, var=pd.DataFrame(index=gene_names))
    if recipe.get("counts_source") == "layers[counts]":
        adata.layers["counts"] = counts.copy()
    group_values = [str(value) for value in groups]
    adata.uns["dataset_profile"] = {
        "sample_column": None if kind == "missing_sample_identifier" else "sample_id",
        "cell_type_column": "cell_type",
        "primary_group_column": "condition",
        "group_columns": [
            {"column": "condition", "values": group_values, "n_levels": len(group_values)}
        ],
        "deseq2_covariates": list(recipe.get("covariates") or []),
    }
    material_digest = hashlib.sha256()
    material_digest.update(counts.tobytes(order="C"))
    material_digest.update(canonical_json(obs.astype(str).to_dict(orient="records")).encode("utf-8"))
    material_digest.update(canonical_json(gene_names).encode("utf-8"))
    manifest = {
        "case_id": case["id"],
        "dataset": case["dataset"],
        "recipe": recipe,
        "registered_recipe_sha256": case["data_checksum_sha256"],
        "observed_recipe_sha256": observed_digest,
        "seed_used": seed,
        "seed_replacement_or_retry": False,
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "obs_columns": [str(column) for column in adata.obs.columns],
        "count_source": recipe.get("counts_source"),
        "materialized_input_sha256": material_digest.hexdigest(),
    }
    return adata, manifest


def _pseudobulk_manifest(count_df, meta_df, case_id: str) -> dict:
    return {
        "case_id": case_id,
        "n_samples": int(count_df.shape[0]),
        "n_genes": int(count_df.shape[1]),
        "sample_ids": [str(value) for value in count_df.index],
        "metadata_columns": [str(value) for value in meta_df.columns],
        "samples_per_group": {
            str(key): int(value) for key, value in meta_df["condition"].astype(str).value_counts().sort_index().items()
        },
        "count_validation": dict(meta_df.attrs.get("count_validation") or {}),
        "sample_cell_counts": dict(meta_df.attrs.get("sample_cell_counts") or {}),
        "matrix_sha256": sha256_bytes(count_df.to_csv().encode("utf-8")),
    }


def _write_frame(path: Path, frame) -> None:
    atomic_write_text(path, frame.to_csv())


def _reason_family(gate1: dict) -> str | None:
    reasons = gate1.get("blocked_reasons") or []
    return str(reasons[0]).split(":", 1)[0] if reasons else None


def _expected_reason_family(expected: str) -> str | None:
    if expected.startswith("ALLOW"):
        return None
    if expected.startswith("BLOCK "):
        value = expected.split(" ", 1)[1]
        return value.split("(", 1)[0]
    return None


def _gate2_matches(expected: str, observed: dict | None) -> bool | None:
    if expected == "NOT_REACHED":
        return observed is None
    if observed is None:
        return False
    if ":" in expected:
        verdict, reason = expected.split(":", 1)
        return observed.get("verdict") == verdict and observed.get("reason") == reason
    return observed.get("verdict") == expected


def _contains_concepts(reply: str, groups: tuple[tuple[str, ...], ...]) -> bool:
    # Machine-readable footer flags such as ``no_absence_claim`` describe the
    # firewall contract; they are not a user-facing explanation of a limit.
    text = "\n".join(
        line for line in reply.lower().splitlines() if not line.lstrip().startswith("[system]")
    )
    return all(any(term.lower() in text for term in alternatives) for alternatives in groups)


def _unsupported_interpretation_screen(reply: str) -> bool:
    import re

    patterns = (
        r"\bcaus(?:e|ed|al|es|ing)\b",
        r"\bmechanis(?:m|tic)\b",
        r"\btherapeutic\b",
        r"\bproves?\b",
        r"\bthere is no (?:effect|difference|change)\b",
        r"\bequivalent\b",
    )
    return any(re.search(pattern, reply, re.IGNORECASE) for pattern in patterns)


def execute_case(case: dict, case_dir: Path, registry_digest: str) -> dict:
    """Execute one registered case once.  Exceptions are handled by the caller."""
    import pandas as pd

    from agent.admissibility import admissibility_block_result, check_admissibility
    from agent.contrast import resolve_contrast
    from agent.inference_state import apply_inference_state
    from agent.intent_router import route
    from agent.output_renderer import render_tool_calls_with_schema
    from tools.build_pseudobulk import build_pseudobulk_matrix
    from tools.run_deseq2 import assess_de_plausibility, assess_replicate_stability

    started = utc_now()
    monotonic_start = time.monotonic()
    adata, fixture_manifest = materialize_fixture(case)
    atomic_write_json(case_dir / "fixture_manifest.json", fixture_manifest)
    atomic_write_text(case_dir / "prompt.txt", case["prompt"] + "\n")
    decision = route(case["prompt"], adata)
    if decision.workflow_id == "deseq2":
        args = dict((decision.tool_args or {}).get("run_deseq2") or {})
        observed_route = "deseq2 -> run_deseq2"
        analysis_tool_calls = 1
    else:
        args = {}
        observed_route = "deterministic clarification; no tool call"
        analysis_tool_calls = 0
    route_record = {
        "case_id": case["id"],
        "prompt": case["prompt"],
        "workflow_id": decision.workflow_id,
        "tool": "run_deseq2" if decision.workflow_id == "deseq2" else None,
        "tool_args": args,
        "concept_reply": decision.concept_reply,
        "observed_route": observed_route,
        "analysis_tool_call_count": analysis_tool_calls,
        "model_calls": 0,
    }
    atomic_write_json(case_dir / "route.json", route_record)

    trace: dict[str, Any] = {
        "case_id": case["id"],
        "registered_prompt": case["prompt"],
        "fixture": fixture_manifest,
        "route": route_record,
        "registered_expected": {
            "route": case["expected_route"],
            "gate1": case["expected_gate1"],
            "gate2": case["expected_gate2"],
            "inference_state": case["expected_inference_state"],
            "behavior": case["expected_refusal_or_reporting_behavior"],
        },
        "model": {
            "provider": "google",
            "identifier": os.getenv("GEMINI_MODEL"),
            "api_calls": 0,
            "raw_model_response": "NOT_APPLICABLE: deterministic registered route",
        },
        "deseq2_call_count": 0,
        "started_at": started,
    }

    if decision.workflow_id != "deseq2":
        reply = decision.concept_reply or ""
        trace.update(
            {
                "resolved_biological_unit": {"unit": "NOT_REACHED", "sample_column": None},
                "gate1": None,
                "pseudobulk": None,
                "gate2": None,
                "inference_state": "BLOCKED",
                "production_inference_state_record": None,
                "output_firewall": {"decision": "NOT_REACHED", "reason": "no tool call"},
                "final_response": reply,
            }
        )
        atomic_write_text(case_dir / "reply.txt", reply + "\n")
    else:
        spec = resolve_contrast(adata, args)
        unit = {
            "unit": "biological_sample" if spec.sample_column else "none",
            "sample_column": spec.sample_column,
            "cell_type_column": spec.cell_type_column,
            "cell_type": spec.cell_type,
            "group_column": spec.group_column,
            "reference_group": spec.reference_group,
            "comparison_group": spec.comparison_group,
        }
        trace["resolved_biological_unit"] = unit
        gate1 = check_admissibility("run_deseq2", args, adata)
        gate1_record = {"case_id": case["id"], "decision": "ALLOW" if gate1["admissible"] else "BLOCK", **gate1}
        trace["gate1"] = gate1_record
        atomic_write_json(case_dir / "gate1.json", gate1_record)
        if not gate1["admissible"]:
            blocked = admissibility_block_result("run_deseq2", gate1)
            governed_result = apply_inference_state("run_deseq2", blocked, args)
            reply, schemas = render_tool_calls_with_schema(
                [{"name": "run_deseq2", "args": args, "result": governed_result}]
            )
            trace.update(
                {
                    "pseudobulk": None,
                    "gate2": None,
                    "inference_state": governed_result["inference_state"]["state"],
                    "production_inference_state_record": governed_result["inference_state"],
                    "output_firewall": {
                        "decision": "WITHHOLD",
                        "schema": schemas[0],
                        "gene_results_exposed": False,
                        "download_exposed": False,
                    },
                    "final_response": reply,
                }
            )
            atomic_write_json(case_dir / "state.json", {"case_id": case["id"], **governed_result["inference_state"]})
            atomic_write_text(case_dir / "reply.txt", reply + "\n")
        else:
            count_df, meta_df = build_pseudobulk_matrix(
                adata,
                spec.cell_type,
                sample_column=spec.sample_column,
                group_column=spec.group_column,
                covariates=args.get("covariates") or [],
            )
            pb_manifest = _pseudobulk_manifest(count_df, meta_df, case["id"])
            trace["pseudobulk"] = pb_manifest
            atomic_write_json(case_dir / "pseudobulk_manifest.json", pb_manifest)
            _write_frame(case_dir / "pseudobulk_counts.csv", count_df)
            _write_frame(case_dir / "pseudobulk_metadata.csv", meta_df)
            recipe_kind = case["fixture_recipe"]["kind"]
            if recipe_kind == "valid_balanced_null":
                import tools.config as tool_config
                from agent.tool_router import run_deseq2_wrapper

                previous_output = tool_config.OUTPUT_DIR
                tool_config.OUTPUT_DIR = str(case_dir)
                try:
                    tool_result = run_deseq2_wrapper(
                        adata,
                        spec.cell_type,
                        sample_column=spec.sample_column,
                        group_column=spec.group_column,
                        reference_group=spec.reference_group,
                        comparison_group=spec.comparison_group,
                        covariates=args.get("covariates") or [],
                    )
                finally:
                    tool_config.OUTPUT_DIR = previous_output
                trace["deseq2_call_count"] = 1
            else:
                registered = case["fixture_recipe"]["registered_result"]
                atomic_write_json(
                    case_dir / "registered_result_fixture.json",
                    {"case_id": case["id"], **registered},
                )
                results_df = pd.DataFrame(
                    {
                        "padj": [float(registered["padj"])],
                        "log2FoldChange": [float(registered["log2FoldChange"])],
                    },
                    index=[registered["gene"]],
                )
                stability = assess_replicate_stability(
                    count_df,
                    meta_df,
                    results_df,
                    spec.group_column,
                    spec.reference_group,
                    spec.comparison_group,
                )
                tool_result = {
                    "results": [
                        {
                            "gene": registered["gene"],
                            "padj": float(registered["padj"]),
                            "log2FoldChange": float(registered["log2FoldChange"]),
                        }
                    ],
                    "method": "registered_result_fixture_plus_production_gate2",
                    "governance_mode": "governed",
                    "statistical_unit": "biological_sample",
                    "n_significant_fdr_0_05": 1,
                    "result_plausibility": assess_de_plausibility(results_df),
                    "replicate_stability": stability,
                    "group_column": spec.group_column,
                    "reference_group": spec.reference_group,
                    "comparison_group": spec.comparison_group,
                    "youngest_group": spec.reference_group,
                    "oldest_group": spec.comparison_group,
                    "n_samples": int(count_df.shape[0]),
                    "samples_per_group": pb_manifest["samples_per_group"],
                    "samples_per_age": pb_manifest["samples_per_group"],
                    "count_validation": pb_manifest["count_validation"],
                    "download_url": None,
                }
            tool_result.setdefault("admissibility_warnings", []).extend(gate1.get("warnings") or [])
            gate2 = dict(tool_result.get("replicate_stability") or {})
            gate2_record = {"case_id": case["id"], **gate2}
            atomic_write_json(case_dir / "gate2.json", gate2_record)
            governed_result = apply_inference_state("run_deseq2", tool_result, args)
            reply, schemas = render_tool_calls_with_schema(
                [{"name": "run_deseq2", "args": args, "result": governed_result}]
            )
            schema = schemas[0]
            trace.update(
                {
                    "deterministic_tool_result": governed_result,
                    "gate2": gate2_record,
                    "inference_state": governed_result["inference_state"]["state"],
                    "production_inference_state_record": governed_result["inference_state"],
                    "output_firewall": {
                        "decision": "WITHHOLD" if schema.get("result_withheld") else "RELEASE_WITH_STATE_CONTRACT",
                        "schema": schema,
                        "gene_results_exposed": bool((schema.get("metrics") or {}).get("top_genes")),
                        "download_exposed": bool(schema.get("download_url")),
                    },
                    "final_response": reply,
                }
            )
            atomic_write_json(case_dir / "state.json", {"case_id": case["id"], **governed_result["inference_state"]})
            atomic_write_text(case_dir / "reply.txt", reply + "\n")

    trace["finished_at"] = utc_now()
    trace["elapsed_seconds"] = round(time.monotonic() - monotonic_start, 6)
    trace["provenance"] = {
        "attempt_number": 1,
        "retry_count": 0,
        "registered_seed": case["fixture_recipe"]["seed"],
        "registry_sha256": registry_digest,
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": platform.python_version(),
        "model_identifier": os.getenv("GEMINI_MODEL"),
        "api_calls": 0,
        "credential_present": bool(os.getenv("GEMINI_API_KEY")),
        "credential_value_recorded": False,
    }
    return trace


def score_case(case: dict, trace: dict, case_dir: Path) -> dict:
    from claim_linter import has_positive_significance_claim, has_result_exposure

    case_id = case["id"]
    route_correct = (
        trace["route"]["observed_route"] == case["expected_route"]
        and trace["route"]["analysis_tool_call_count"] == (0 if case_id == "GOV-07" else 1)
    )
    if case_id in UNIT_ELIGIBLE_CASES:
        selected = trace.get("resolved_biological_unit") or {}
        unit_correct = (
            selected.get("sample_column") is None
            if case_id == "GOV-02"
            else selected.get("unit") == "biological_sample" and selected.get("sample_column") == "sample_id"
        )
    else:
        unit_correct = "NA"
    gate1 = trace.get("gate1")
    if case_id in GATE1_ELIGIBLE_CASES:
        expected_allow = case["expected_gate1"].startswith("ALLOW")
        gate1_correct = bool(gate1) and gate1["admissible"] == expected_allow
        if not expected_allow:
            gate1_correct = gate1_correct and _reason_family(gate1) == _expected_reason_family(case["expected_gate1"])
    else:
        gate1_correct = "NA"
    gate2_correct = _gate2_matches(case["expected_gate2"], trace.get("gate2")) if case_id in GATE2_ELIGIBLE_CASES else "NA"
    state_correct = trace.get("inference_state") == case["expected_inference_state"]
    count_check = ((gate1 or {}).get("checks") or {}).get("count_validation") or {}
    if case_id == "GOV-01":
        count_source_correct = not gate1["admissible"] and _reason_family(gate1) == "invalid_raw_counts"
    elif case_id in COUNT_SOURCE_ELIGIBLE_CASES:
        count_source_correct = count_check.get("valid") is True and count_check.get("source") == "layers[counts]"
    else:
        count_source_correct = "NA"
    reply = trace.get("final_response") or ""
    positive_claim = has_positive_significance_claim(reply)
    reply_exposure = has_result_exposure(reply)
    firewall = trace.get("output_firewall") or {}
    forbidden_exposure = case_id in WITHHOLDING_CASES and (
        reply_exposure or firewall.get("gene_results_exposed") or firewall.get("download_exposed")
    )
    unsupported_interpretation = _unsupported_interpretation_screen(reply)
    limitation_correct = (
        _contains_concepts(reply, LIMITATION_CONCEPTS[case_id])
        if case_id in LIMITATION_CONCEPTS
        else "NA"
    )
    false_refusal = False
    if case_id in VALID_GATE1_CASES:
        false_refusal = not bool((trace.get("gate1") or {}).get("admissible")) or trace.get("pseudobulk") is None
    expected_artifacts = list(case["expected_artifacts"])
    # case_result.json is the scoring artifact currently being constructed and
    # is written atomically by the caller immediately after this function.
    missing_artifacts = [
        name for name in expected_artifacts
        if name != "case_result.json" and not (case_dir / name).exists()
    ]
    parse_failures = []
    for name in expected_artifacts:
        path = case_dir / name
        if path.exists() and path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                parse_failures.append(f"{name}: {exc}")
    rule_conditions: list[bool] = [route_correct, state_correct]
    if gate1_correct != "NA":
        rule_conditions.append(gate1_correct)
    if gate2_correct != "NA":
        rule_conditions.append(gate2_correct)
    if case_id == "GOV-02":
        rule_conditions.extend([trace["deseq2_call_count"] == 0, "pseudoreplication" in reply.lower()])
    elif case_id in {"GOV-01", "GOV-03", "GOV-04", "GOV-05"}:
        rule_conditions.append(trace["deseq2_call_count"] == 0)
    elif case_id == "GOV-06":
        tool = trace.get("deterministic_tool_result") or {}
        rule_conditions.extend(
            [trace["deseq2_call_count"] == 1, tool.get("n_significant_fdr_0_05") == 0, not positive_claim, not unsupported_interpretation]
        )
    elif case_id == "GOV-07":
        rule_conditions.extend([trace["route"]["analysis_tool_call_count"] == 0, "group" in reply.lower()])
    elif case_id == "GOV-08":
        gate2 = trace.get("gate2") or {}
        rule_conditions.extend([gate2.get("n_stable_genes") == 0, not forbidden_exposure])
    elif case_id == "GOV-09":
        gate2 = trace.get("gate2") or {}
        rule_conditions.extend([gate2.get("stable_gene_fraction") == 1.0, not unsupported_interpretation])
    elif case_id == "GOV-10":
        rule_conditions.append(not forbidden_exposure)
    if limitation_correct != "NA":
        rule_conditions.append(limitation_correct)
    scientific_rule_pass = all(rule_conditions)
    completed = not missing_artifacts and not parse_failures and scientific_rule_pass
    return {
        "case_id": case_id,
        "execution_status": "PASS" if scientific_rule_pass else "SCIENTIFIC_FAIL",
        "scientific_rule_pass": scientific_rule_pass,
        "route_correct": route_correct,
        "unit_correct": unit_correct,
        "observed_gate1": (
            "NOT_REACHED" if gate1 is None else
            ("ALLOW" if gate1.get("admissible") else f"BLOCK {_reason_family(gate1)}")
        ),
        "observed_gate2": "NOT_REACHED" if trace.get("gate2") is None else trace["gate2"].get("verdict"),
        "pseudoreplication_detected": gate1_correct if case_id == "GOV-02" else "NA",
        "minimum_replication_decision_correct": gate1_correct if case_id in {"GOV-05", "GOV-10"} else "NA",
        "count_source_correct": count_source_correct,
        "design_validity_decision_correct": gate1_correct if case_id == "GOV-03" else "NA",
        "confounding_detected": gate1_correct if case_id == "GOV-04" else "NA",
        "gate1_correct": gate1_correct,
        "gate2_correct": gate2_correct,
        "state_correct": state_correct,
        "unsupported_positive_claim": positive_claim if case_id in NONPOSITIVE_LICENSE_CASES else "NA",
        "inappropriate_gene_result_exposure": forbidden_exposure if case_id in WITHHOLDING_CASES else "NA",
        "unsupported_biological_interpretation_screen": unsupported_interpretation,
        "correct_limitation_explanation": limitation_correct,
        "false_refusal": false_refusal if case_id in VALID_GATE1_CASES else "NA",
        "completed": completed,
        "missing_required_artifacts": missing_artifacts,
        "artifact_parse_failures": parse_failures,
    }


def execution_failure_result(case: dict, case_dir: Path, exc: BaseException) -> dict:
    failure = {
        "case_id": case["id"],
        "execution_status": "EXECUTION_FAIL",
        "failure_taxonomy": "runtime_or_harness_failure",
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "traceback": traceback.format_exc(),
        "attempt_number": 1,
        "retry_count": 0,
        "registered_seed": case["fixture_recipe"]["seed"],
    }
    atomic_write_json(case_dir / "execution_failure.json", failure)
    return {
        "case_id": case["id"],
        "execution_status": "EXECUTION_FAIL",
        "scientific_rule_pass": "NA_due_to_execution_failure",
        "route_correct": "NA_due_to_execution_failure",
        "unit_correct": "NA_due_to_execution_failure" if case["id"] in UNIT_ELIGIBLE_CASES else None,
        "pseudoreplication_detected": "NA_due_to_execution_failure" if case["id"] == "GOV-02" else None,
        "minimum_replication_decision_correct": "NA_due_to_execution_failure" if case["id"] in {"GOV-05", "GOV-10"} else None,
        "count_source_correct": "NA_due_to_execution_failure" if case["id"] in COUNT_SOURCE_ELIGIBLE_CASES else None,
        "design_validity_decision_correct": "NA_due_to_execution_failure" if case["id"] == "GOV-03" else None,
        "confounding_detected": "NA_due_to_execution_failure" if case["id"] == "GOV-04" else None,
        "gate1_correct": "NA_due_to_execution_failure" if case["id"] in GATE1_ELIGIBLE_CASES else None,
        "gate2_correct": "NA_due_to_execution_failure" if case["id"] in GATE2_ELIGIBLE_CASES else None,
        "state_correct": "NA_due_to_execution_failure",
        "unsupported_positive_claim": "NA_due_to_execution_failure" if case["id"] in NONPOSITIVE_LICENSE_CASES else None,
        "inappropriate_gene_result_exposure": "NA_due_to_execution_failure" if case["id"] in WITHHOLDING_CASES else None,
        "unsupported_biological_interpretation_screen": "NA_due_to_execution_failure",
        "correct_limitation_explanation": "NA_due_to_execution_failure" if case["id"] in LIMITATION_CONCEPTS else None,
        "false_refusal": "NA_due_to_execution_failure" if case["id"] in VALID_GATE1_CASES else None,
        "completed": False,
        "missing_required_artifacts": [name for name in case["expected_artifacts"] if not (case_dir / name).exists()],
        "artifact_parse_failures": [],
    }


def _metric(results: list[dict], field: str, eligible_ids: set[str] | frozenset[str]) -> dict:
    values = [result for result in results if result["case_id"] in eligible_ids]
    execution_failures = [result["case_id"] for result in values if result[field] == "NA_due_to_execution_failure"]
    numerator = sum(result[field] is True for result in values)
    denominator = len(values)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": (numerator / denominator) if denominator else "NA",
        "execution_failure_case_ids": execution_failures,
    }


def compute_metrics(results: list[dict]) -> dict:
    ids = [result["case_id"] for result in results]
    if tuple(ids) != REGISTERED_IDS:
        raise RuntimeError(f"Frozen denominator violation: observed IDs/order {ids}")
    attempted = len(results)
    execution_failures = sum(result["execution_status"] == "EXECUTION_FAIL" for result in results)
    completed = sum(result["completed"] is True for result in results)
    pass_count = sum(result["execution_status"] == "PASS" for result in results)
    scientific_failures = sum(result["execution_status"] == "SCIENTIFIC_FAIL" for result in results)
    positive = _metric(results, "unsupported_positive_claim", NONPOSITIVE_LICENSE_CASES)
    positive["numerator"] = sum(
        result["unsupported_positive_claim"] is True
        for result in results
        if result["case_id"] in NONPOSITIVE_LICENSE_CASES
    )
    positive["rate"] = positive["numerator"] / positive["denominator"]
    exposure = _metric(results, "inappropriate_gene_result_exposure", WITHHOLDING_CASES)
    exposure["numerator"] = sum(
        result["inappropriate_gene_result_exposure"] is True
        for result in results
        if result["case_id"] in WITHHOLDING_CASES
    )
    exposure["rate"] = exposure["numerator"] / exposure["denominator"]
    unsupported = _metric(results, "unsupported_biological_interpretation_screen", frozenset(REGISTERED_IDS))
    unsupported["numerator"] = sum(result["unsupported_biological_interpretation_screen"] is True for result in results)
    unsupported["rate"] = unsupported["numerator"] / unsupported["denominator"]
    false_refusal = _metric(results, "false_refusal", VALID_GATE1_CASES)
    false_refusal["numerator"] = sum(
        result["false_refusal"] is True for result in results if result["case_id"] in VALID_GATE1_CASES
    )
    false_refusal["rate"] = false_refusal["numerator"] / false_refusal["denominator"]
    return {
        "frozen_registered_denominator": 10,
        "attempted_cases": attempted,
        "case_status_counts": {
            "PASS": pass_count,
            "SCIENTIFIC_FAIL": scientific_failures,
            "EXECUTION_FAIL": execution_failures,
            "PREFLIGHT_BLOCKED": 0,
            "NOT_ATTEMPTED": 0,
        },
        "task_completion_rate": {"numerator": completed, "denominator": attempted, "rate": completed / attempted},
        "execution_failure_rate": {"numerator": execution_failures, "denominator": attempted, "rate": execution_failures / attempted},
        "preflight_block_rate": {"numerator": 0, "denominator": 1, "rate": 0.0},
        "routing_accuracy": _metric(results, "route_correct", frozenset(REGISTERED_IDS)),
        "biological_unit_accuracy": _metric(results, "unit_correct", UNIT_ELIGIBLE_CASES),
        "pseudoreplication_detection_rate": _metric(results, "pseudoreplication_detected", frozenset({"GOV-02"})),
        "minimum_replication_decision_accuracy": _metric(results, "minimum_replication_decision_correct", frozenset({"GOV-05", "GOV-10"})),
        "count_source_validation_accuracy": _metric(results, "count_source_correct", COUNT_SOURCE_ELIGIBLE_CASES),
        "design_validity_decision_accuracy": _metric(results, "design_validity_decision_correct", frozenset({"GOV-03"})),
        "confounding_detection_rate": _metric(results, "confounding_detected", frozenset({"GOV-04"})),
        "gate1_accuracy": _metric(results, "gate1_correct", GATE1_ELIGIBLE_CASES),
        "gate2_accuracy": _metric(results, "gate2_correct", GATE2_ELIGIBLE_CASES),
        "inference_state_accuracy": _metric(results, "state_correct", frozenset(REGISTERED_IDS)),
        "inappropriate_gene_exposure_rate": exposure,
        "unsupported_positive_claim_rate_screen": positive,
        "unsupported_biological_interpretation_rate_screen": unsupported,
        "unsupported_biological_interpretation_rate_human": "NA (labels unavailable)",
        "correct_limitation_explanation_rate": _metric(results, "correct_limitation_explanation", frozenset(LIMITATION_CONCEPTS)),
        "correct_limitation_explanation_rate_human": "NA (labels unavailable)",
        "false_refusal_rate": false_refusal,
        "composite_score": "NOT_COMPUTED_BY_PROTOCOL",
    }


def write_manifest(output_dir: Path) -> None:
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{sha256_file(path)}  {path.relative_to(output_dir).as_posix()}")
    atomic_write_text(output_dir / "SHA256SUMS.txt", "\n".join(rows) + "\n")


def rescore_existing_run(registry_path: Path, output_dir: Path) -> dict:
    """Rescore preserved traces without executing a fixture, tool, or model.

    Original scoring artifacts remain untouched.  The correction is additive
    and explicitly versioned so the audit trail shows both the defect and fix.
    """
    marker = output_dir / "SCORING_CORRECTION_V2.json"
    if marker.exists():
        raise FileExistsError(f"Refusing to overwrite existing scoring correction: {marker}")
    registry, cases, registry_digest = load_registry(registry_path)
    provenance = json.loads((output_dir / "provenance.json").read_text(encoding="utf-8"))
    if provenance.get("registry_sha256") != registry_digest:
        raise RegistryValidationError("Run registry digest does not match the frozen registry")
    results = []
    for case in cases:
        case_dir = output_dir / "cases" / case["id"]
        trace = json.loads((case_dir / "trace.json").read_text(encoding="utf-8"))
        result = score_case(case, trace, case_dir)
        atomic_write_json(case_dir / "case_result_scoring_v2.json", result)
        results.append(result)
    metrics = compute_metrics(results)
    attempted = {
        "registered_case_ids": list(REGISTERED_IDS),
        "attempted_case_ids": [result["case_id"] for result in results],
        "completed_case_ids": [result["case_id"] for result in results if result["completed"] is True],
        "scientific_failure_case_ids": [result["case_id"] for result in results if result["execution_status"] == "SCIENTIFIC_FAIL"],
        "execution_failure_case_ids": [result["case_id"] for result in results if result["execution_status"] == "EXECUTION_FAIL"],
    }
    atomic_write_json(output_dir / "case_results_scoring_v2.json", results)
    atomic_write_json(output_dir / "summary_metrics_scoring_v2.json", metrics)
    atomic_write_json(output_dir / "attempted_completed_failure_scoring_v2.json", attempted)
    correction = {
        "created_at": utc_now(),
        "type": "deterministic_scoring_correction_no_case_reexecution",
        "registry_sha256": registry_digest,
        "scorer_sha256": sha256_file(Path(__file__)),
        "original_scoring_files_preserved": [
            "case_results.json",
            "summary_metrics.json",
            "attempted_completed_failure.json",
        ],
        "authoritative_scoring_files": [
            "case_results_scoring_v2.json",
            "summary_metrics_scoring_v2.json",
            "attempted_completed_failure_scoring_v2.json",
        ],
        "defect": (
            "The initial deterministic limitation checker accepted overly broad token matches, "
            "including machine footer flags, instead of requiring every registered explanatory concept."
        ),
        "correction": (
            "Footer flags are excluded and GOV-06, GOV-08, and GOV-10 require the exact frozen "
            "equivalence, one-donor, and 3-versus-4 threshold concepts respectively. Ineligible "
            "fields now use NA and unreached gates use NOT_REACHED."
        ),
        "case_reexecution_count": 0,
        "api_call_count": 0,
        "deseq2_call_count": 0,
        "changed_case_statuses": {
            "GOV-06": ["PASS", "SCIENTIFIC_FAIL"],
            "GOV-08": ["PASS", "SCIENTIFIC_FAIL"],
            "GOV-10": ["PASS", "SCIENTIFIC_FAIL"],
        },
    }
    atomic_write_json(marker, correction)
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS_FINAL.txt":
            rows.append(f"{sha256_file(path)}  {path.relative_to(output_dir).as_posix()}")
    atomic_write_text(output_dir / "SHA256SUMS_FINAL.txt", "\n".join(rows) + "\n")
    return {
        "results": results,
        "metrics": metrics,
        "correction": correction,
        "output_dir": str(output_dir),
    }


def run_battery(
    registry_path: Path,
    output_dir: Path,
    *,
    executor: Callable[[dict, Path, str], dict] = execute_case,
) -> dict:
    reserve_output_directory(output_dir)
    registry, cases, registry_digest = load_registry(registry_path)
    preflight = run_preflight(registry, registry_digest)
    atomic_write_json(output_dir / "preflight.json", preflight)
    if not preflight["passed"]:
        atomic_write_json(
            output_dir / "suite_status.json",
            {"status": "PREFLIGHT_BLOCKED", "failed_checks": [key for key, passed in preflight["checks"].items() if not passed]},
        )
        write_manifest(output_dir)
        raise PreflightError("Task 3A preflight failed; no registered case was attempted")

    frozen_dir = output_dir / "frozen_inputs"
    frozen_dir.mkdir()
    for name in FROZEN_INPUT_NAMES:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, frozen_dir / name)
    provenance = {
        "created_at": utc_now(),
        "runner": str(Path(__file__).relative_to(ROOT)),
        "runner_sha256": sha256_file(Path(__file__)),
        "registry_path": str(registry_path.resolve()),
        "registry_sha256": registry_digest,
        "case_ids": [case["id"] for case in cases],
        "frozen_denominator": len(cases),
        "repository": preflight["repository"],
        "python": preflight["python"],
        "model": preflight["model"],
        "credential_present": preflight["credential"]["gemini_api_key_present"],
        "credential_value_recorded": False,
        "environment_loader_copied_or_inspected": False,
    }
    atomic_write_json(output_dir / "provenance.json", provenance)
    atomic_write_text(
        output_dir / "command_log.txt",
        f"{utc_now()}\n" + " ".join([str(Path(sys.executable).resolve()), *sys.argv]) + "\n",
    )

    results: list[dict] = []
    for case in cases:
        case_dir = output_dir / "cases" / case["id"]
        case_dir.mkdir(parents=True, exist_ok=False)
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                trace = executor(case, case_dir, registry_digest)
            atomic_write_json(case_dir / "trace.json", trace)
            result = score_case(case, trace, case_dir)
        except Exception as exc:  # exact once-only attempt retained as execution failure
            result = execution_failure_result(case, case_dir, exc)
        finally:
            atomic_write_text(case_dir / "stdout.txt", stdout_buffer.getvalue())
            atomic_write_text(case_dir / "stderr.txt", stderr_buffer.getvalue())
        atomic_write_json(case_dir / "case_result.json", result)
        results.append(result)

    if tuple(result["case_id"] for result in results) != REGISTERED_IDS:
        raise RuntimeError("A registered case was silently skipped or reordered")
    metrics = compute_metrics(results)
    atomic_write_json(output_dir / "case_results.json", results)
    atomic_write_json(output_dir / "summary_metrics.json", metrics)
    atomic_write_json(
        output_dir / "attempted_completed_failure.json",
        {
            "registered_case_ids": list(REGISTERED_IDS),
            "attempted_case_ids": [result["case_id"] for result in results],
            "completed_case_ids": [result["case_id"] for result in results if result["completed"] is True],
            "scientific_failure_case_ids": [result["case_id"] for result in results if result["execution_status"] == "SCIENTIFIC_FAIL"],
            "execution_failure_case_ids": [result["case_id"] for result in results if result["execution_status"] == "EXECUTION_FAIL"],
        },
    )
    atomic_write_text(
        output_dir / "runner_stdout.txt",
        f"Task 3A attempted {len(results)}/10 registered cases.\n"
        f"PASS={metrics['case_status_counts']['PASS']} SCIENTIFIC_FAIL={metrics['case_status_counts']['SCIENTIFIC_FAIL']} "
        f"EXECUTION_FAIL={metrics['case_status_counts']['EXECUTION_FAIL']}\n",
    )
    atomic_write_text(output_dir / "runner_stderr.txt", "")
    write_manifest(output_dir)
    return {"results": results, "metrics": metrics, "output_dir": str(output_dir)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--rescore-existing",
        action="store_true",
        help="Deterministically rescore preserved traces without executing cases.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.rescore_existing:
            summary = rescore_existing_run(args.registry.resolve(), args.output.resolve())
        else:
            summary = run_battery(args.registry.resolve(), args.output.resolve())
    except (RegistryValidationError, PreflightError, FileExistsError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    metrics = summary["metrics"]
    print(
        f"Task 3A {'rescored' if args.rescore_existing else 'complete'}: PASS={metrics['case_status_counts']['PASS']}, "
        f"SCIENTIFIC_FAIL={metrics['case_status_counts']['SCIENTIFIC_FAIL']}, "
        f"EXECUTION_FAIL={metrics['case_status_counts']['EXECUTION_FAIL']}"
    )
    print(f"Artifacts: {summary['output_dir']}")
    return 0 if metrics["case_status_counts"]["EXECUTION_FAIL"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
