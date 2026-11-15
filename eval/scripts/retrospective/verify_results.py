"""Independent aggregation and Decimal spot-exhaustive check of new result tables."""
from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(os.environ.get("SENESCENCE_RETRO_OUTPUT", ROOT/"eval/results/retrospective_reproduction"))
LOCK=ROOT/"eval/results/v2/e2/e2_v1_20261023_01"
EXECUTIONS=(ROOT/"eval/results/v2/e2/e2_gemini36_execution_v1_20261024_01",
            ROOT/"eval/results/v2/e2/e2_gemini36_continuation_v1_20261025_01")
SCORES=ROOT/"eval/results/v2/e2/e2_gemini36_combined_v1_20261025_01/PROVISIONAL_SCORES.jsonl"
MATH=re.compile(r"^\$?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\\times\s*10\^\{([+-]?\d+)\}\s*\$?$")


def csvrows(name):
    with (OUT/name).open(newline="") as stream:return list(csv.DictReader(stream))


def jsonlines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def parse_decimal(cell):
    cell=cell.strip().replace("`","").replace("**","").strip("$")
    match=MATH.fullmatch(cell)
    return Decimal(match.group(1))*(Decimal(10)**int(match.group(2))) if match else Decimal(cell)


def within(value, reference, kind):
    tol=max(abs(reference)*Decimal("0.006" if kind=="lfc" else "0.01"),Decimal("0.006" if kind=="lfc" else "1e-300"))
    return abs(value-reference)<=tol


def main():
    r1=csvrows("R1_FIELD_LEVEL_MATRIX.csv")
    assert len(r1)==126 and len({x["target"] for x in r1})==9
    r1summary=json.loads((OUT/"R1_SUMMARY.json").read_text())
    for field in r1summary:
        items=[x for x in r1 if x["field"]==field]
        assert len(items)==9
        for category,count in Counter(x["classification"] for x in items).items():assert r1summary[field][category]==count

    baseline=csvrows("R2_OPPORTUNITY_AUDIT.csv")
    v11=csvrows("R2_LATEX_OPPORTUNITY_AUDIT.csv")
    reports=csvrows("R2_FORMAT_VS_CONTENT.csv")
    assert len(reports)==408 and len(baseline)==len(v11)==596
    assert Counter(x["status"] for x in reports)=={"SUCCESS":398,"TRUNCATED_RESPONSE":8,"API_FAILURE":2}
    bmap={(x["case_id"],x["arm"],x["opportunity_id"]):x for x in baseline}
    assert len(bmap)==596
    new=[x for x in v11 if x["new_exact_detection"]=="True"]
    assert len(new)==71
    assert all(x["v1_exact_content"]=="False" and x["v1_1_exact_content"]=="True" for x in new)
    opps={x["id"]:x for x in json.loads((LOCK/"E2_SUPPORTED_OPPORTUNITIES.json").read_text())}
    responses={}
    for folder in EXECUTIONS:
        for path in folder.glob("*/RESPONSE.json"):
            x=json.loads(path.read_text());responses[x["case_id"],x["arm"]]=x
    independent=0
    for record in new:
        op=opps[record["opportunity_id"]]
        text=responses[record["case_id"],record["arm"]]["text"]
        for line in text.splitlines():
            if op["gene"] not in line or "|" not in line:continue
            cells=[cell.strip() for cell in line.split("|") if cell.strip()]
            if len(cells)<3:continue
            try:
                lfc,q=parse_decimal(cells[1]),parse_decimal(cells[-1])
            except Exception:
                continue
            if within(lfc,Decimal(str(op["log2FC"])),"lfc") and within(q,Decimal(str(op["padj"])),"q"):
                independent+=1;break
        else:raise AssertionError((record["case_id"],record["arm"],record["opportunity_id"]))
    assert independent==71
    grouped=defaultdict(list)
    for x in v11:grouped[x["family"],x["arm"]].append(x)
    counts={f"{family}_{arm}":sum(x["new_exact_detection"]=="True" for x in items) for (family,arm),items in grouped.items()}
    assert counts=={"F3_A":50,"F3_B":21,"F3_C":0,"F3_D":0,"F4_A":0,"F4_B":0,"F4_C":0,"F4_D":0}

    r3=csvrows("R3_COUNTERFACTUAL_SCREEN_RESULTS.csv")
    assert len(r3)==312
    by_variant=defaultdict(list)
    for x in r3:by_variant[x["variant"]].append(x)
    assert len(by_variant)==4
    for variant,items in by_variant.items():
        assert len(items)==78 and len({x["case_id"] for x in items})==78
        assert all(x["original_screen_event"]=="True" and x["counterfactual_screen_event"]=="False" for x in items)
        assert all(x["other_counterfactual_categories"]=="" for x in items)
    frozen=jsonlines(SCORES)
    assert len(frozen)==408
    assert sum(x["retained"] for x in frozen if x["family"]=="F3" and x["arm"]=="A")==0
    assert sum(x["retained"] for x in frozen if x["family"]=="F3" and x["arm"]=="B")==0
    result={"status":"PASS","r1_field_rows":126,"r2_reports":408,"r2_success":398,
            "r2_planned_arm_opportunities":596,"r2_new_exact_decimal_verified":independent,
            "r2_new_exact_by_family_arm":counts,"r3_counterfactual_rows":312,
            "r3_original_flagged_per_variant":78,"r3_counterfactual_flagged_per_variant":0,
            "scope":"saved artifacts and deterministic text analyses; no scientific recomputation or LLM calls"}
    (OUT/"QUALITY_CONTROL.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    (OUT/"QUALITY_CONTROL.md").write_text("# Quality control\n\nIndependent aggregation of the written R1/R2/R3 CSVs passed. A separate `decimal.Decimal` parser rechecked all 71 newly detected F3 numerical rows against their frozen opportunity values and the unchanged display tolerances. All 408 response statuses and all 596 opportunity rows were accounted for. Each R3 variant contains the original 78 matched cases, all with no remaining alternative screen trigger after the edit. These checks validate arithmetic and source consistency, not semantic or biological correctness.\n")
    print("QUALITY_CONTROL_PASS",independent,"decimal_verified_new_rows")


if __name__=="__main__":main()
