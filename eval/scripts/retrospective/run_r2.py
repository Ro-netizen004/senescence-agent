"""POST HOC / RETROSPECTIVE R2. Reads saved E2 records; never calls a model."""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(os.environ.get("SENESCENCE_RETRO_OUTPUT", ROOT / "eval/results/retrospective_reproduction"))
E2 = ROOT / "eval/results/v2/e2"
LOCK = E2 / "e2_v1_20261023_01"
SCORES = E2 / "e2_gemini36_combined_v1_20261025_01/PROVISIONAL_SCORES.jsonl"
EXECUTIONS = (E2 / "e2_gemini36_execution_v1_20261024_01",
              E2 / "e2_gemini36_continuation_v1_20261025_01")
sys.path.insert(0, str(ROOT / "eval/scripts/e2"))
from scoring import score, near, numerical_match, table_values  # noqa: E402 - frozen code

NUMBER = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
LFC_LABEL = re.compile(r"\b(?:log\s*2\s*(?:fold\s*change|fc)|lfc)\b\s*[:=]?\s*" + NUMBER, re.I)
Q_LABEL = re.compile(r"\b(?:padj|adjusted\s*p(?:\s*-?\s*value)?|fdr|q(?:-?\s*value)?)\b\s*[:=]?\s*" + NUMBER, re.I)


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def normalized(line):
    return line.replace("−", "-").replace("–", "-").replace("—", "-").replace("**", "").replace(",", "")


def close(reported, reference, kind):
    tolerance = max(abs(reference) * (.006 if kind == "lfc" else .01), .006 if kind == "lfc" else 1e-300)
    return abs(reported - reference) <= tolerance


def detect(opportunity, text):
    lines = near(text, opportunity["gene"], opportunity.get("symbol"))
    format_ok = any(True for line in lines for _ in table_values([line]))
    table_content = numerical_match(lines, opportunity["log2FC"], opportunity["padj"])
    prose_content = False
    for raw in lines:
        if "|" in raw:
            continue
        line = normalized(raw)
        lfc, q = LFC_LABEL.search(line), Q_LABEL.search(line)
        if lfc and q and close(float(lfc.group(1)), opportunity["log2FC"], "lfc") and close(float(q.group(1)), opportunity["padj"], "q"):
            prose_content = True
            break
    return {"format_compliant": format_ok,
            "exact_numeric_content": table_content or prose_content,
            "exact_prose_content": prose_content,
            "gene_mention_detected": bool(lines)}


def tier(status, classification, content, qualified, refused):
    if status != "SUCCESS":
        return "MISSING_OR_TRUNCATED"
    if content and qualified and not refused:
        return "COMPLETE_NUMERICAL_COMMUNICATION"
    if classification == "EXPLICITLY_REFUSED_CONDITIONAL_OPPORTUNITY":
        return "INTENTIONALLY_WITHHELD"
    if classification == "PARTIALLY_COMMUNICATED" or content:
        return "PARTIAL_NUMERICAL_COMMUNICATION"
    return "NO_DETECTED_NUMERICAL_COMMUNICATION"


def main():
    assert (OUT / "PROVENANCE_BEFORE.json").is_file()
    cases = {record["case_id"]: record for record in jsonl(LOCK / "E2_CASE_MANIFEST.jsonl")}
    assert len(cases) == 102
    opportunities = defaultdict(list)
    for op in json.loads((LOCK / "E2_SUPPORTED_OPPORTUNITIES.json").read_text()):
        opportunities[op["case_id"]].append(op)
    assert sum(map(len, opportunities.values())) == 149
    saved = {(record["case_id"], record["arm"]): record for record in jsonl(SCORES)}
    assert len(saved) == 408
    responses = {}
    for root in EXECUTIONS:
        for path in root.glob("*/RESPONSE.json"):
            record = json.loads(path.read_text())
            key = (record["case_id"], record["arm"])
            assert key not in responses, f"Repeated attempt {key}"
            responses[key] = (record, path)
    assert set(responses) == set(saved) == {(cid, arm) for cid in cases for arm in "ABCD"}

    per_report, per_opportunity = [], []
    for case_id, arm in sorted(saved):
        frozen = saved[case_id, arm]
        response, path = responses[case_id, arm]
        packet = json.loads((ROOT / cases[case_id]["packet_path"]).read_text())
        ops = opportunities[case_id]
        assert len(ops) == cases[case_id]["opportunities"]
        reproduced = score(response, packet, ops)
        for key in reproduced:
            assert reproduced[key] == frozen[key], (case_id, arm, key)
        measures = []
        for op, original in zip(ops, frozen["entries"]):
            assert op["id"] == original["opportunity_id"]
            detected = detect(op, response.get("text", "")) if response["status"] == "SUCCESS" else {
                "format_compliant": False, "exact_numeric_content": False,
                "exact_prose_content": False, "gene_mention_detected": False}
            classification = original["classification"]
            current_tier = tier(response["status"], classification,
                                detected["exact_numeric_content"], frozen["uncertainty_qualification_present"],
                                classification == "EXPLICITLY_REFUSED_CONDITIONAL_OPPORTUNITY")
            measure = {"case_id": case_id, "family": frozen["family"], "arm": arm,
                       "opportunity_id": op["id"], "status": response["status"],
                       "original_classification": classification,
                       "strict_retained": classification == "CORRECTLY_RETAINED_PROVISIONAL",
                       **detected, "communication_tier": current_tier}
            per_opportunity.append(measure); measures.append(measure)
        per_report.append({"case_id": case_id, "family": frozen["family"], "arm": arm,
                           "attempt": path.parent.parent.name, "status": response["status"],
                           "opportunities": len(ops), "strict_retained": frozen["retained"],
                           "format_compliant": sum(x["format_compliant"] for x in measures),
                           "exact_numeric_content": sum(x["exact_numeric_content"] for x in measures),
                           "exact_prose_content": sum(x["exact_prose_content"] for x in measures),
                           "partial_tier": sum(x["communication_tier"] == "PARTIAL_NUMERICAL_COMMUNICATION" for x in measures),
                           "original_partial": frozen["partial"], "policy_withheld": frozen["refused"],
                           "unresolved_original": frozen["unresolved"],
                           "complete_numerical_tier": sum(x["communication_tier"] == "COMPLETE_NUMERICAL_COMMUNICATION" for x in measures)})
    assert len(per_report) == 408 and len(per_opportunity) == 596
    for name, data in [("R2_FORMAT_VS_CONTENT.csv", per_report), ("R2_OPPORTUNITY_AUDIT.csv", per_opportunity)]:
        with (OUT / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0])); writer.writeheader(); writer.writerows(data)
    groups = defaultdict(list)
    for row in per_report: groups[row["family"],row["arm"]].append(row)
    comparison = []
    for (family, arm), group in sorted(groups.items()):
        planned = len(group)
        success = sum(row["status"] == "SUCCESS" for row in group)
        opps = sum(row["opportunities"] for row in group)
        completed_opps = sum(row["opportunities"] for row in group if row["status"] == "SUCCESS")
        comparison.append({"family":family,"arm":arm,"planned_reports":planned,"successful_reports":success,
                           "incomplete_reports":planned-success,"planned_opportunities":opps,
                           "completed_response_opportunities":completed_opps,
                           "strict_retained":sum(row["strict_retained"] for row in group),
                           "format_compliant":sum(row["format_compliant"] for row in group),
                           "exact_numeric_content":sum(row["exact_numeric_content"] for row in group),
                           "exact_prose_content":sum(row["exact_prose_content"] for row in group),
                           "complete_numerical_tier":sum(row["complete_numerical_tier"] for row in group),
                           "partial_tier":sum(row["partial_tier"] for row in group),
                           "original_partial":sum(row["original_partial"] for row in group),
                           "policy_withheld":sum(row["policy_withheld"] for row in group),
                           "strict_per_planned":sum(row["strict_retained"] for row in group)/opps if opps else "NOT_APPLICABLE",
                           "content_per_planned":sum(row["exact_numeric_content"] for row in group)/opps if opps else "NOT_APPLICABLE",
                           "content_per_successful_opportunity":sum(row["exact_numeric_content"] for row in group)/completed_opps if completed_opps else "NOT_APPLICABLE"})
    with (OUT / "R2_ARM_COMPARISON.csv").open("w", newline="") as stream:
        writer=csv.DictWriter(stream, fieldnames=list(comparison[0])); writer.writeheader(); writer.writerows(comparison)
    disagreement=[x for x in per_opportunity if x["status"]=="SUCCESS" and x["exact_numeric_content"] and not x["strict_retained"]]
    fmt_wrong=[x for x in per_opportunity if x["status"]=="SUCCESS" and x["format_compliant"] and not x["exact_numeric_content"]]
    summary={"reports":len(per_report),"successful":sum(x["status"]=="SUCCESS" for x in per_report),
             "truncated":sum(x["status"]=="TRUNCATED_RESPONSE" for x in per_report),
             "api_failure":sum(x["status"]=="API_FAILURE" for x in per_report),
             "planned_arm_opportunities":len(per_opportunity),"strict_zero_content_one":len(disagreement),
             "format_one_content_zero":len(fmt_wrong),"example_strict_zero_content_one":disagreement[0] if disagreement else None}
    (OUT/"R2_SUMMARY.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    lines=["# R2 POST HOC / RETROSPECTIVE format-versus-content findings", "",
           "The unchanged original E2 scorer was reapplied to all 408 saved slots and reproduced every frozen score field. This does not validate scientific truth. The new detector is narrow and may miss valid prose; it requires a gene plus exact labeled log2FC and adjusted p on one line, or an accurate parseable table row.", "",
           "| Family | Arm | Success/planned | Opportunities | Strict | Pipe format | Exact numerical content | Complete qualified tier | Original partial | Policy withheld |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in comparison:
        lines.append(f"| {row['family']} | {row['arm']} | {row['successful_reports']}/{row['planned_reports']} | {row['planned_opportunities']} | {row['strict_retained']} | {row['format_compliant']} | {row['exact_numeric_content']} | {row['complete_numerical_tier']} | {row['original_partial']} | {row['policy_withheld']} |")
    lines += ["",f"Detected exact numerical content without original strict retention: **{len(disagreement)}** arm-opportunities. Pipe syntax without exact matched values: **{len(fmt_wrong)}** arm-opportunities. Full per-report and per-opportunity audit rows are in the CSVs; F1/F2 retention is undefined, not zero quality.", ""]
    if disagreement:
        example=disagreement[0]
        lines.append(f"Source-traced divergence: `{example['case_id']}` Arm `{example['arm']}` opportunity `{example['opportunity_id']}` has exact gene-matched numbers under the post hoc detector but fails the original strict contract. Its source `RESPONSE.json` and registered packet are identified through `R2_FORMAT_VS_CONTENT.csv` and `E2_CASE_MANIFEST.jsonl`. This is a format/qualification distinction, not a support judgment.")
    else:
        lines.append("No high-specificity exact-content/strict-score divergence was detected. The pre-existing partial-direction counts still show that strict zero does not imply no conveyed information, but they do not establish complete numerical transfer.")
    lines += ["", "Original failures are preserved: 398 success, eight truncated and two API failures. C/D are deterministic local reports; A/B generated prose under a token cap. This difference and shared source contexts limit arm comparisons. No biological or semantic correctness rate is estimated.",""]
    (OUT/"R2_SUMMARY.md").write_text("\n".join(lines))
    print("R2_PASS",len(per_report),"reports",len(per_opportunity),"opportunities",len(disagreement),"content_strict_divergences")


if __name__=="__main__":main()
