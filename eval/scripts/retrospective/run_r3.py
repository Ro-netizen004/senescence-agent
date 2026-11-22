"""POST HOC / RETROSPECTIVE R3: in-memory edits of saved F1 D report text."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(os.environ.get("SENESCENCE_RETRO_OUTPUT", ROOT / "eval/results/retrospective_reproduction"))
E2 = ROOT / "eval/results/v2/e2"
LOCK = E2 / "e2_v1_20261023_01"
EXECUTIONS = (E2 / "e2_gemini36_execution_v1_20261024_01",
              E2 / "e2_gemini36_continuation_v1_20261025_01")
SCORES = E2 / "e2_gemini36_combined_v1_20261025_01/PROVISIONAL_SCORES.jsonl"
sys.path.insert(0, str(ROOT / "eval/scripts/e2"))
from scoring import score  # noqa: E402 - original frozen scorer

SENTENCE = "These results look like a technical artifact, not real biology."
VARIANTS = {
    "REMOVE_SENTENCE": "",
    "CAUTIOUS_UNCERTAINTY": "The source of these numerical patterns remains uncertain; technical and biological explanations require further checks.",
    "HEDGED_TECHNICAL": "These patterns may reflect a technical artifact, but biological origin is unresolved.",
    "PARAPHRASED_CAUTION": "These results raise concern for a possible artifact rather than establishing a biological origin.",
}


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def categories(scored):
    return [flag["category"] for flag in scored["screen_flags"]]


def main():
    assert (OUT / "PROVENANCE_BEFORE.json").is_file()
    source = (ROOT / "eval/scripts/e2/scoring.py").read_text()
    renderer = (ROOT / "backend/agent/output_renderer.py").read_text()
    assert "if 'technical artifact, not real biology' in text:" in source
    assert SENTENCE in renderer
    cases = {row["case_id"]: row for row in jsonl(LOCK / "E2_CASE_MANIFEST.jsonl") if row["family"] == "F1"}
    assert len(cases) == 78
    saved = {(r["case_id"],r["arm"]):r for r in jsonl(SCORES)}
    responses = {}
    for root in EXECUTIONS:
        for path in root.glob("F1_*_D/RESPONSE.json"):
            r = json.loads(path.read_text()); key=(r["case_id"],r["arm"])
            assert key not in responses
            responses[key]=(r,path)
    assert len(responses) == 78
    rows=[]
    for case_id in sorted(cases):
        response,path=responses[case_id,"D"]
        assert response["status"] == "SUCCESS"
        packet=json.loads((ROOT / cases[case_id]["packet_path"]).read_text())
        original=score(response,packet,[])
        frozen=saved[case_id,"D"]
        for key in original:assert original[key]==frozen[key],(case_id,key)
        original_cats=categories(original)
        count=response["text"].count(SENTENCE)
        for variant,replacement in VARIANTS.items():
            edited = dict(response)
            eligible=count==1
            if eligible:
                edited["text"]=response["text"].replace(SENTENCE,replacement,1)
                assert edited["text"].count(SENTENCE)==0
            result=score(edited,packet,[])
            changed=original["unsupported_screen_event"]!=result["unsupported_screen_event"]
            result_cats=categories(result)
            rows.append({"case_id":case_id,"arm":"D","variant":variant,"source_attempt":path.parent.parent.name,
                         "edit_status":"EDITED_IN_MEMORY" if eligible else "UNEDITED_UNVERIFIABLE",
                         "original_sentence_occurrences":count,
                         "original_screen_event":original["unsupported_screen_event"],
                         "counterfactual_screen_event":result["unsupported_screen_event"],
                         "screen_decision_changed":changed,
                         "original_artifact_origin_flags":original_cats.count("artifact_origin_candidate"),
                         "counterfactual_artifact_origin_flags":result_cats.count("artifact_origin_candidate"),
                         "other_original_categories":";".join(c for c in original_cats if c!="artifact_origin_candidate"),
                         "other_counterfactual_categories":";".join(c for c in result_cats if c!="artifact_origin_candidate"),
                         "original_text_sha256":sha_text(response["text"]),
                         "counterfactual_text_sha256":sha_text(edited["text"])})
    assert len(rows)==312
    with (OUT/"R3_COUNTERFACTUAL_SCREEN_RESULTS.csv").open("w",newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    grouped=defaultdict(list)
    for row in rows:grouped[row["variant"]].append(row)
    summary=[]
    for variant,group in grouped.items():
        summary.append({"variant":variant,"planned":len(group),
                        "original_flagged":sum(x["original_screen_event"] for x in group),
                        "counterfactual_flagged":sum(x["counterfactual_screen_event"] for x in group),
                        "decisions_changed":sum(x["screen_decision_changed"] for x in group),
                        "decisions_unchanged":sum(not x["screen_decision_changed"] for x in group),
                        "original_artifact_category":sum(x["original_artifact_origin_flags"] for x in group),
                        "counterfactual_artifact_category":sum(x["counterfactual_artifact_origin_flags"] for x in group),
                        "other_trigger_cases":sum(bool(x["other_counterfactual_categories"]) for x in group),
                        "unedited_unverifiable":sum(x["edit_status"]!="EDITED_IN_MEMORY" for x in group)})
    (OUT/"R3_SUMMARY.json").write_text(json.dumps(summary,indent=2)+"\n")
    lines=["# R3 POST HOC / RETROSPECTIVE counterfactual screen sensitivity", "",
           "The unchanged original scorer reproduced the frozen F1 D record before any counterfactual edit. All edits were temporary in-memory copies of the saved response; no original report, model or statistical output changed.","",
           "| Variant | Original flagged | Counterfactual flagged | Decisions changed | Unchanged | Other-trigger cases | Unedited |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for x in summary:
        lines.append(f"| {x['variant']} | {x['original_flagged']}/{x['planned']} | {x['counterfactual_flagged']}/{x['planned']} | {x['decisions_changed']} | {x['decisions_unchanged']} | {x['other_trigger_cases']} | {x['unedited_unverifiable']} |")
    first=rows[0]
    lines += ["", "The original match condition is the case-sensitive substring `technical artifact, not real biology`; the scorer records `artifact_origin_candidate`. Other flag categories are preserved and counted separately in the row-level CSV. A changed screen decision follows from the frozen string test unless another trigger remains; it is not evidence that the new wording is scientifically correct.","",
              "Worked example: preserved F1_000 Arm D originally begins `These results look like a technical artifact, not real biology.`. Under `CAUTIOUS_UNCERTAINTY`, only that sentence becomes `The source of these numerical patterns remains uncertain; technical and biological explanations require further checks.` The original and modified decision for this case is recorded in `R3_COUNTERFACTUAL_SCREEN_RESULTS.csv`; all scientific numbers and the source report remain unchanged.",""]
    (OUT/"R3_SUMMARY.md").write_text("\n".join(lines))
    print("R3_PASS",len(rows),"counterfactuals",[(x["variant"],x["counterfactual_flagged"]) for x in summary])


if __name__=="__main__":main()
