"""Outcome-informed R2 V1.1 sensitivity; baseline V1 files are read-only."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from run_r2 import OUT, ROOT, LOCK, SCORES, EXECUTIONS, close, jsonl, normalized, near, LFC_LABEL, Q_LABEL

BASELINE_HASHES = {
    "ANALYSIS_PLAN_V1.md": "0985670285072932f3d1492976b19aaa2c7e5410d63005eed298b811e6f5d0f7",
    "R2_FORMAT_VS_CONTENT.csv": "540723400c5a48cb0d4cb6d3733770d8ce6187b89819ae8fa3e6ac7637c0ec9d",
    "R2_OPPORTUNITY_AUDIT.csv": "e2fdf7d208c07041be3717a2aad96ff8dd3a6e114b0510adc210e7ce76b367cd",
    "R2_ARM_COMPARISON.csv": "c6c3090a0c05cb642c7caec78df4b90c5aaa61b5c79593154f25e55efd15c00e",
    "R2_SUMMARY.json": "34cd17db596b753947c8b1e3ce223fa2f0fdec51b256af4126f54cfdca32f0f9",
    "run_r2.py": "6361eb2b19ab9e2bb7564936820e26b33d792736ea7d52eaf8099e13d556161f",
}
MATH = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:\\times|×)\s*10\s*\^\s*\{?([+-]?\d+)\}?$")
Q_EXT = re.compile(r"\b(?:padj|adjusted\s*p(?:\s*-?\s*value)?|fdr|q(?:-?\s*value)?)\b\s*[:=]?\s*(\$?\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:\s*(?:\\times|×)\s*10\s*\^\s*\{?[+-]?\d+\}?)?\s*\$?)", re.I)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_math_number(raw):
    token = raw.strip().replace("**", "").replace("`", "").replace("$", "").replace(",", "")
    token = token.replace("−", "-").replace("–", "-").strip()
    try:
        return float(token)
    except ValueError:
        pass
    match = MATH.fullmatch(token)
    return float(match.group(1)) * 10.0 ** int(match.group(2)) if match else None


def detect_extended(op, text):
    lines = near(text, op["gene"], op.get("symbol"))
    format_ok = False
    content_ok = False
    source = ""
    for line in lines:
        if "|" in line:
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]
            if len(cells) >= 3:
                lfc, q = parse_math_number(cells[1]), parse_math_number(cells[-1])
                if lfc is not None and q is not None:
                    format_ok = True
                    if close(lfc, op["log2FC"], "lfc") and close(q, op["padj"], "q"):
                        content_ok = True; source = "pipe_math_or_float"
        else:
            cleaned = normalized(line)
            lfc, q = LFC_LABEL.search(cleaned), Q_EXT.search(cleaned)
            if lfc and q:
                qval = parse_math_number(q.group(1))
                if qval is not None and close(float(lfc.group(1)), op["log2FC"], "lfc") and close(qval, op["padj"], "q"):
                    content_ok = True; source = "labeled_prose_math_or_float"
    return format_ok, content_ok, source


def main():
    for name, expected in BASELINE_HASHES.items():
        assert sha(OUT / name) == expected, f"V1 baseline changed: {name}"
    base = {(r["case_id"], r["arm"], r["opportunity_id"]): r for r in csv.DictReader((OUT / "R2_OPPORTUNITY_AUDIT.csv").open())}
    cases = {r["case_id"]: r for r in jsonl(LOCK / "E2_CASE_MANIFEST.jsonl")}
    opportunities = defaultdict(list)
    for op in json.loads((LOCK / "E2_SUPPORTED_OPPORTUNITIES.json").read_text()):
        opportunities[op["case_id"]].append(op)
    saved = {(r["case_id"], r["arm"]): r for r in jsonl(SCORES)}
    responses = {}
    for folder in EXECUTIONS:
        for path in folder.glob("*/RESPONSE.json"):
            x = json.loads(path.read_text()); key = (x["case_id"], x["arm"])
            assert key not in responses
            responses[key] = x
    out=[]; examples=[]
    for (cid, arm), response in sorted(responses.items()):
        for op in opportunities[cid]:
            old = base[cid,arm,op["id"]]
            if response["status"] == "SUCCESS":
                fmt, content, source = detect_extended(op, response["text"])
            else:
                fmt, content, source = False, False, "incomplete_response"
            assert (not bool(old["exact_numeric_content"] == "True")) or content, (cid,arm,op["id"])
            row = {"case_id":cid,"family":cases[cid]["family"],"arm":arm,"opportunity_id":op["id"],
                   "status":response["status"],"strict_retained":old["strict_retained"],
                   "v1_format":old["format_compliant"],"v1_exact_content":old["exact_numeric_content"],
                   "v1_1_format":fmt,"v1_1_exact_content":content,"source_pattern":source,
                   "new_exact_detection":content and old["exact_numeric_content"]!="True"}
            out.append(row)
            if row["new_exact_detection"] and len(examples)<3:
                examples.append({"case_id":cid,"arm":arm,"opportunity_id":op["id"],"source_pattern":source})
    assert len(out) == 596 and len(base) == 596
    with (OUT/"R2_LATEX_OPPORTUNITY_AUDIT.csv").open("w", newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
    grouped=defaultdict(list)
    for row in out: grouped[row["family"],row["arm"]].append(row)
    comp=[]
    for (family,arm), group in sorted(grouped.items()):
        comp.append({"family":family,"arm":arm,"planned_opportunities":len(group),
                     "successful_opportunities":sum(x["status"]=="SUCCESS" for x in group),
                     "strict_retained":sum(x["strict_retained"]=="True" for x in group),
                     "v1_format":sum(x["v1_format"]=="True" for x in group),
                     "v1_1_format":sum(x["v1_1_format"] for x in group),
                     "v1_exact_content":sum(x["v1_exact_content"]=="True" for x in group),
                     "v1_1_exact_content":sum(x["v1_1_exact_content"] for x in group),
                     "new_exact_detection":sum(x["new_exact_detection"] for x in group)})
    with (OUT/"R2_LATEX_ARM_COMPARISON.csv").open("w",newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=list(comp[0]));w.writeheader();w.writerows(comp)
    summary={"classification":"POST_HOC_OUTCOME_INFORMED_SENSITIVITY", "arm_opportunities":len(out),
             "new_exact_detections":sum(x["new_exact_detection"] for x in out),
             "examples":examples,"by_arm_family":comp}
    (OUT/"R2_LATEX_SUMMARY.json").write_text(json.dumps(summary,indent=2)+"\n")
    lines=["# R2 V1.1 post-observation LaTeX notation sensitivity", "",
           "The V1 rule and its zero-divergence result remain intact. This outcome-informed V1.1 parser accepts LaTeX scientific notation in the same gene-matched cells while keeping the original numeric tolerances and all 596 planned arm-opportunities. It measures detectable numerical transfer under a broader notation grammar, not biological correctness.","",
           "| Family | Arm | Strict | V1 format | V1.1 format | V1 exact | V1.1 exact | Newly detected exact |",
           "|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in comp:
        lines.append(f"| {x['family']} | {x['arm']} | {x['strict_retained']}/{x['planned_opportunities']} | {x['v1_format']} | {x['v1_1_format']} | {x['v1_exact_content']} | {x['v1_1_exact_content']} | {x['new_exact_detection']} |")
    lines += ["",f"New exact detections across all opportunities: **{summary['new_exact_detections']}**. These are exploratory after inspecting a V1 miss. No original score changed.",""]
    if examples:
        e=examples[0]
        lines += [f"Worked source trace: `{e['case_id']}` Arm `{e['arm']}` opportunity `{e['opportunity_id']}` uses a gene-matched pipe row whose adjusted-p cell is written in LaTeX `\\times 10^{{...}}` notation. The unchanged original scorer's `float()` parser rejects that cell; V1.1 converts the notation and checks both saved values within the original tolerances. The exact report is in its preserved `RESPONSE.json`; the opportunity is in `E2_SUPPORTED_OPPORTUNITIES.json`. No report text was changed.",""]
    (OUT/"R2_LATEX_SUMMARY.md").write_text("\n".join(lines))
    for name,expected in BASELINE_HASHES.items():assert sha(OUT/name)==expected
    print("R2_V1_1_PASS",len(out),"opportunities",summary["new_exact_detections"],"new_exact")


if __name__=="__main__":main()
