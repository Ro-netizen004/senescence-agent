"""POST HOC / RETROSPECTIVE R1: saved E1 evidence-flow audit only."""
from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(os.environ.get("SENESCENCE_RETRO_OUTPUT", ROOT / "eval/results/retrospective_reproduction"))
E1 = ROOT / "eval/results/v2/e1/e1_v2_1_20261022_01"
TARGETS = ("ATP2A2", "CYB5R4", "ELOB", "GATA3", "KDM1A", "MED24", "MEN1", "NFKB2", "SGF29")
FIELDS = ("target_symbol_ensembl_mapping", "donor_sample_count", "paired_design", "control_group_identity",
          "experimental_covariates", "on_target_log2fc", "on_target_raw_p", "on_target_padj",
          "numerical_fit_warnings", "gene_level_numerical_rows", "native_stability_diagnostic",
          "paired_donor_sensitivity", "gate1_decision", "gate2_license")


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def row_match(text, gene):
    return next((line for line in text.splitlines() if re.search(r"\|\s*" + re.escape(gene) + r"\s*\|", line)), "")


def displayed_numeric_match(line, reference_lfc, reference_q):
    try:
        cells = [cell.strip().replace("**", "") for cell in line.split("|") if cell.strip()]
        if len(cells) < 3:
            return False
        lfc, q = float(cells[1]), float(cells[-1])
        expected_lfc, expected_q = float(reference_lfc), float(reference_q)
        return (abs(lfc - expected_lfc) <= max(abs(expected_lfc) * .006, .006)
                and abs(q - expected_q) <= max(abs(expected_q) * .01, 1e-300))
    except (TypeError, ValueError):
        return False


def classify(upstream, schema, rendered, report, policy=False, applicable=True, verifiable=True):
    if not applicable:
        return "NOT_APPLICABLE"
    if not verifiable:
        return "UNVERIFIABLE"
    if not upstream:
        return "UNAVAILABLE_UPSTREAM"
    if policy:
        return "INTENTIONALLY_WITHHELD_BY_POLICY"
    if not schema:
        return "OMITTED_AT_INTERFACE"
    if not rendered or not report:
        return "OMITTED_AT_RENDERER"
    return "PRESENT"


def main():
    assert (OUT / "PROVENANCE_BEFORE.json").is_file()
    eligibility = {row["target"]: row for row in read_csv(E1 / "E1_TARGET_ELIGIBILITY.csv")}
    assert tuple(sorted(eligibility)) == tuple(sorted(TARGETS))
    renderer = (ROOT / "backend/agent/output_renderer.py").read_text()
    schema_source = (ROOT / "backend/agent/output_schema.py").read_text()
    executor = (ROOT / "eval/scripts/e1/execute_e1.py").read_text()
    assert "top_genes[:100]" in renderer and '"top_genes": [] if withheld else rows[:100]' in schema_source
    assert executor.index('sensitivity=p/"paired_sensitivity"') < executor.index('with (p/"original_governed_reply.txt")')
    results = []
    per_target = []
    for target in TARGETS:
        base = E1 / "execution" / target
        e = eligibility[target]
        gene = e["target_gene_id"]
        tool = json.loads((base / "tool_result.json").read_text())
        schema = json.loads((base / "output_schema.json").read_text())[0]
        governed = json.loads((base / "governed_result.json").read_text())
        gate1 = json.loads((base / "gate1.json").read_text())
        reply = (base / "original_governed_reply.txt").read_text()
        full = {row[""]: row for row in read_csv(base / "deseq2_results.csv")}
        assert gene in full and gate1["admissible"] is True
        assert schema["result_withheld"] == (len(schema["metrics"]["top_genes"]) == 0)
        top = {row["gene"]: row for row in schema["metrics"]["top_genes"]}
        row = row_match(reply, gene)
        warning_lines = [line for line in (base / "analysis.log").read_text().splitlines()
                         if re.search(r"RuntimeWarning:|UserWarning:", line)]
        sensitivity = list((base / "paired_sensitivity").glob("*.csv"))
        state = governed["inference_state"]["state"]
        assert state == schema["inference_state"]
        withheld = schema["result_withheld"]
        n_samples = tool["n_samples"]
        ref = tool["reference_group"]
        covariates = tool.get("covariates_used") or []
        assert isinstance(n_samples, int) and ref

        def add(field, upstream, schema_yes, render_access, report_yes, source, key,
                note="", policy=False, applicable=True, verifiable=True):
            status = classify(upstream, schema_yes, render_access, report_yes, policy, applicable, verifiable)
            results.append({"target": target, "field": field, "upstream_available": upstream,
                            "schema_available": schema_yes, "renderer_accessible": render_access,
                            "final_report_present": report_yes, "policy_withheld": policy,
                            "classification": status, "gate2_state": state,
                            "upstream_source": source, "source_key": key, "note": note})

        add("target_symbol_ensembl_mapping", bool(gene), False, False,
            target in reply and gene in reply,
            "E1_TARGET_ELIGIBILITY.csv; data/expression_genes.csv; canonical_evidence_packet.json",
            "target,target_gene_id; gene_ids,gene_name; target",
            "The original schema has gene IDs in allowed rows but no verified symbol-to-ID pair; six outputs also censor gene rows.")
        add("donor_sample_count", bool(n_samples), bool(schema["population"].get("n_samples")), True,
            bool(re.search(r"Samples:\s*" + str(n_samples) + r"\b", reply)),
            "tool_result.json", "n_samples;samples_per_group;population.n_samples",
            "The sample count is not a count of independent cells.")
        add("paired_design", "donor_id" in tool.get("design_factors", []), False, False,
            bool(re.search(r"paired\s+donor|donor_id", reply, re.I)), "tool_result.json",
            "design_factors;covariates_used", "A per-group sample count does not state the paired formula.")
        add("control_group_identity", bool(ref), schema["population"].get("youngest_group") == ref, True,
            bool(re.search(r"\b" + re.escape(ref) + r"\b", reply)), "tool_result.json",
            "reference_group;population.youngest_group", "The schema's age-named key carries the control label.")
        add("experimental_covariates", bool(covariates), False, False,
            all(re.search(r"\b" + re.escape(c) + r"\b", reply) for c in covariates),
            "tool_result.json", "covariates_used;design_factors", "No donor identifiers are copied into this audit.")

        target_in_schema = gene in top
        target_in_report = displayed_numeric_match(row, full[gene]["log2FoldChange"], full[gene]["padj"])
        add("on_target_log2fc", True, target_in_schema, target_in_schema, target_in_report,
            "deseq2_results.csv", "[target_gene_id].log2FoldChange;metrics.top_genes",
            "Censored if result_withheld; otherwise top-100 projection may omit the target.", withheld)
        add("on_target_raw_p", bool(full[gene].get("pvalue")), target_in_schema and "pvalue" in top.get(gene, {}), False,
            False, "deseq2_results.csv", "[target_gene_id].pvalue;metrics.top_genes.pvalue",
            "The original renderer prints log2FC and padj, not raw pvalue.", withheld)
        add("on_target_padj", bool(full[gene].get("padj")), target_in_schema and "padj" in top.get(gene, {}),
            target_in_schema, target_in_report, "deseq2_results.csv",
            "[target_gene_id].padj;metrics.top_genes.padj", "A count of significant genes is not the on-target padj.", withheld)
        add("numerical_fit_warnings", bool(warning_lines), False, False,
            bool(re.search(r"mean-based dispersion trend|residual degrees of freedom|RuntimeWarning|UserWarning", reply, re.I)),
            "analysis.log", "RuntimeWarning;UserWarning",
            "The fit log was written before the report; these warnings did not enter tool_result or schema.")
        add("gene_level_numerical_rows", bool(full), bool(top), bool(top),
            bool(re.search(r"\|\s*ENSG\d+\s*\|", reply)), "deseq2_results.csv",
            "results;metrics.top_genes", "Unwithheld output is capped at 100 rows; full CSV may be linked.", withheld)
        stability = tool.get("replicate_stability") or {}
        stab_verdict = stability.get("verdict")
        add("native_stability_diagnostic", bool(stability), bool(schema.get("replicate_stability")), True,
            bool(stab_verdict and re.search(r"\b" + re.escape(stab_verdict) + r"\b", reply, re.I)),
            "tool_result.json", "replicate_stability;schema.replicate_stability",
            "The renderer mentions the verdict in its stability-failure branch; it need not render a stable verdict.")
        add("paired_donor_sensitivity", bool(sensitivity), False, False, False,
            "paired_sensitivity/*.csv; execute_e1.py", "paired donor omission refit",
            "Saved sensitivity files were created before original report rendering; only four-donor targets have them.",
            applicable=bool(sensitivity))
        add("gate1_decision", bool(gate1), False, False,
            bool(re.search(r"Gate\s*1\s*[:=]\s*(?:PASS|BLOCK)|admissible\s*[:=]\s*(?:true|false)", reply, re.I)),
            "gate1.json", "admissible;blocked_reasons;checks",
            "A generic statement that the design passed does not preserve the complete Gate 1 decision record.")
        add("gate2_license", bool(governed.get("inference_state")),
            bool(schema.get("inference_state") and schema.get("allowed_interpretation_level")), True,
            ("inference_state=" + state) in reply, "governed_result.json;output_schema.json",
            "inference_state;allowed_interpretation_level;result_withheld",
            "The system footer exposes the state; this is a policy label, not biological truth.")
        per_target.append({"target": target, "gate2_state": state, "withheld": withheld,
                           "schema_gene_rows": len(top), "warning_lines": len(warning_lines),
                           "paired_sensitivity_files": len(sensitivity),
                           "omitted_interface": sum(r["classification"] == "OMITTED_AT_INTERFACE" for r in results if r["target"] == target),
                           "omitted_renderer": sum(r["classification"] == "OMITTED_AT_RENDERER" for r in results if r["target"] == target)})

    assert len(results) == 9 * len(FIELDS)
    assert set(r["field"] for r in results) == set(FIELDS)
    fields = list(results[0])
    with (OUT / "R1_FIELD_LEVEL_MATRIX.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(results)
    with (OUT / "R1_PER_TARGET.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(per_target[0])); writer.writeheader(); writer.writerows(per_target)
    grouped = defaultdict(list)
    for record in results: grouped[record["field"]].append(record)
    summary = {field: {"all_targets": len(items), "applicable_upstream": sum(x["classification"] not in {"UNAVAILABLE_UPSTREAM", "NOT_APPLICABLE", "UNVERIFIABLE"} for x in items),
                       **dict(Counter(x["classification"] for x in items))} for field, items in grouped.items()}
    (OUT / "R1_SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    lines = ["# R1 POST HOC / RETROSPECTIVE evidence-transfer findings", "",
             "Nine fixed E1 targets; one row per target and field in `R1_FIELD_LEVEL_MATRIX.csv`. Counts below are per applicable target, not per cell or gene. A policy-withheld row is not counted as an interface loss.", "",
             "| Field | Applicable upstream | Present | Interface omission | Renderer omission | Policy withheld | Not applicable |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for field in FIELDS:
        s = summary[field]
        lines.append(f"| {field} | {s['applicable_upstream']} | {s.get('PRESENT',0)} | {s.get('OMITTED_AT_INTERFACE',0)} | {s.get('OMITTED_AT_RENDERER',0)} | {s.get('INTENTIONALLY_WITHHELD_BY_POLICY',0)} | {s.get('NOT_APPLICABLE',0)} |")
    lines.extend(["", "## Per-target trace", "", "| Target | Gate 2 | Rows in schema | Logged warnings | Paired refit files | Interface omissions | Renderer omissions |", "|---|---|---:|---:|---:|---:|---:|"])
    for x in per_target:
        lines.append(f"| {x['target']} | {x['gate2_state']} | {x['schema_gene_rows']} | {x['warning_lines']} | {x['paired_sensitivity_files']} | {x['omitted_interface']} | {x['omitted_renderer']} |")
    lines += ["", "## Interpretation", "",
              "The target symbol-to-Ensembl mapping, paired formula, covariate list and logged fit warnings can be traced upstream but are not carried as such by the original reporting schema. The schema carries sample counts, group labels and Gate 2 state. It holds `pvalue` in permitted top-gene rows, yet the renderer prints only `log2FC` and `padj`. Six gene-row suppressions are explicitly policy driven. These observations establish field loss and intentional censoring, not whether a withheld scientific claim was justified.",
              "", "## Source-traced examples", "",
              "- KDM1A: a saved mapped on-target result enters the permitted top-gene list; the report prints the Ensembl row's log2FC and adjusted p, while its target symbol mapping, paired design and raw p are absent from the original rendered text. See `execution/KDM1A/{deseq2_results.csv,output_schema.json,original_governed_reply.txt}`.",
              "- ATP2A2: the saved full DE result and target mapping exist, but `result_withheld=true` yields no gene rows in the original schema or reply. The original log records fitting warnings that are not passed to the report. See `execution/ATP2A2/{analysis.log,output_schema.json,original_governed_reply.txt}`.",
              "", "An improved architecture diagram should show separate source→tool packet, tool→schema and schema→renderer edges, annotate the lost fields at each edge, and show Gate 2 censorship as a distinct intentional branch. The E2 adapter belongs on an evaluation-only later branch.", ""]
    (OUT / "R1_SUMMARY.md").write_text("\n".join(lines))
    (OUT / "R1_SOURCE_TRACE.md").write_text("""# R1 source trace (POST HOC / RETROSPECTIVE)

- `eval/scripts/e1/execute_e1.py`: `analysis.log` and paired-donor refits are written during analysis before the original `report` stage writes `canonical_evidence_packet.json`, `governed_result.json`, `output_schema.json` and `original_governed_reply.txt`.
- `eval/results/v2/e1/e1_v2_1_20261022_01/E1_TARGET_ELIGIBILITY.csv`: nine verified target symbols and Ensembl IDs. The original `canonical_evidence_packet.json` has a top-level target symbol; the renderer schema does not project the symbol-to-ID pair.
- Per-target `tool_result.json`: group names, sample count, `design_factors`, `covariates_used`, raw-count validation, native stability and plausibility. Per-target `gate1.json`: admissibility and design checks. Per-target `deseq2_results.csv`: full gene estimates, raw p and adjusted p.
- `backend/agent/output_schema.py::build_output_schema`, `run_deseq2` branch: `population` retains group names and count, `metrics.top_genes` is empty on withholding or capped at 100. It omits target mapping, paired formula, fit warning log, paired refits and detailed Gate 1 check record.
- `backend/agent/output_renderer.py` `run_deseq2` branch: prints sample/group fields, fixed plausibility and stability warnings, and permitted rows as `Gene | log2FC | padj`. It does not print raw p or standard errors. Its footer prints inference state. Source line ranges are in the prior `AAIBD2026_FINAL_RESEARCH_HANDOFF/03_SOURCE_CODE_COMPONENT_MAP.csv`.

The field matrix uses the saved artifacts directly and records file/key provenance without copying donor identifiers, raw counts or full result tables. A classification of omission is a data-transfer observation, not an assertion that the omitted fact should have been publicly released under the frozen license.
""")
    print("R1_PASS",len(results),"rows",sum(x["withheld"] for x in per_target),"withheld_targets")


if __name__ == "__main__":
    main()
