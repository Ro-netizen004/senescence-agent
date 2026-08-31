"""Validate and package the matched OneK1K full-agent null experiment."""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "eval/external_validation/onek1k/full_agent_null.py"
DEFAULT_OUTPUT = ROOT / "eval/results/final_candidate/onek1k_external_validation/full_agent_null_monoc_seed3000_n10"

def _load_harness():
    spec = importlib.util.spec_from_file_location("onek1k_full_agent_null", HARNESS)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

def _sanitize(value):
    if isinstance(value, dict):
        out = {k: _sanitize(v) for k, v in value.items()}
        for key in ("dataset", "plot_path"):
            if isinstance(out.get(key), str): out[key] = Path(out[key]).name
        return out
    if isinstance(value, list): return [_sanitize(v) for v in value]
    return value

def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    module = _load_harness()
    source_summary = json.loads((args.source / "summary.json").read_text(encoding="utf-8"))
    if source_summary.get("n_complete_pairs") != 10: raise ValueError("Expected ten complete pairs")
    if args.output.exists(): shutil.rmtree(args.output)
    raw_out = args.output / "raw"; raw_out.mkdir(parents=True)
    rows, protocol_ids, corrected = [], set(), []
    for seed in range(3000, 3010):
        scored = {}
        for arm in ("governed", "ungoverned"):
            path = args.source / "raw" / f"seed{seed}_{arm}.json"
            rec = json.loads(path.read_text(encoding="utf-8"))
            if rec.get("status") != "complete_full_agent_null": raise ValueError(f"Incomplete: {path}")
            protocol_ids.add(rec["protocol_id"])
            old = rec["score"]
            response = {"reply": old.get("reply", ""), "tool_calls": [old["tool_call"]], "analysis_plan": old.get("analysis_plan")}
            rec["score"] = module.score_response(response, rec["registered"])
            s = rec["score"]
            required = (s.get("routing_success"), s.get("contrast_correct"), s.get("covariates_correct"), s.get("matches_registered_discovery_count"), s.get("communicates_no_significant_result"), not s.get("positive_significance_claim"))
            if not all(required): raise ValueError(f"Validation failure: {path}")
            scored[arm] = s
            _write_json(raw_out / path.name, _sanitize(rec))
        if scored["governed"]["statistical_signature_sha256"] != scored["ungoverned"]["statistical_signature_sha256"]: raise ValueError(f"Parity failure seed {seed}")
        if scored["governed"].get("inference_state") != "NOT_SIGNIFICANT": raise ValueError(f"Governed state failure seed {seed}")
        if (scored["governed"].get("analysis_plan") or {}).get("status") != "accepted": raise ValueError(f"Plan failure seed {seed}")
        pair = {"seed": seed, "both_routed": True, "statistical_parity": True, "both_match_registered": True, "governed_state": "NOT_SIGNIFICANT", "governed_communicates_null": True, "ungoverned_communicates_null": True, "governed_positive_claim": False, "ungoverned_positive_claim": False, "governed_plan_status": "accepted"}
        corrected.append(pair)
        rows.append({"seed":seed,"n_significant_fdr_0_05":0,"governed_route":True,"ungoverned_route":True,"statistical_parity":True,"governed_plan_status":"accepted","governed_state":"NOT_SIGNIFICANT","governed_communicated_null":True,"ungoverned_communicated_null":True,"governed_positive_claim":False,"ungoverned_positive_claim":False,"statistical_signature_sha256":scored["governed"]["statistical_signature_sha256"]})
    if len(protocol_ids) != 1: raise ValueError("Mixed protocol IDs")
    with (args.output / "per_seed_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    aggregate={"both_arms_routed":10,"statistical_parity":10,"both_matched_registered":10,"governed_not_significant":10,"governed_communicated_null":10,"ungoverned_communicated_null":10,"governed_positive_claims":0,"ungoverned_positive_claims":0,"governed_plans_accepted":10}
    run_summary=dict(source_summary); run_summary["pairs"]=corrected; run_summary["aggregate"]=aggregate; run_summary["scoring_note"]="Saved replies were rescored offline after broadening the zero-count matcher; no model or DE calls were repeated."
    _write_json(args.output / "run_summary.json", _sanitize(run_summary))
    revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    harness_hash=hashlib.sha256(HARNESS.read_bytes()).hexdigest()
    paper={"status":"paper_candidate_full_agent_null_calibration","experiment":"onek1k_matched_full_agent_null","protocol_id":next(iter(protocol_ids)),"evaluated_base_git_revision":revision,"full_agent_harness_sha256":harness_hash,"n_allocations":10,"n_agent_runs":20,"n_matched_pairs":10,"routes_correct":{"governed":10,"ungoverned":10},"governed_plans_accepted":10,"statistical_parity_pairs":10,"registered_result_count_matches":{"governed":10,"ungoverned":10},"zero_discovery_results":{"governed":10,"ungoverned":10},"governed_not_significant":10,"null_communication":{"governed":10,"ungoverned":10},"positive_significance_claims":{"governed":0,"ungoverned":0},"runtime_diagnostic":"pyDESeq2 emitted overflow/invalid-value RuntimeWarnings during optimization. All fits completed, paired signatures matched exactly, and every result reproduced the registered zero-discovery count.","interpretation_boundary":"This validates full-agent routing, planning where applicable, execution, state assignment, and null communication in a many-donor UMI setting. Because every statistical result had zero discoveries, it does not estimate a governance withholding advantage. Allocations reuse one donor cohort."}
    _write_json(args.output / "paper_summary.json", paper)
    (args.output / "PAPER_RESULTS.md").write_text("""# OneK1K Full-agent Null Validation\n\n**Status: paper-candidate agent-level calibration result.**\n\nTen registered classical-monocyte donor splits were run through matched governed and ungoverned agents. Each arm independently routed to and executed donor-level pseudobulk DESeq2 with `pool + sex + age + null_group`.\n\n| Endpoint | Result |\n|---|---:|\n| Matched agent pairs | 10/10 |\n| Correct routing, both arms | 20/20 |\n| Governed plans accepted | 10/10 |\n| Exact statistical parity | 10/10 |\n| Registered zero-discovery result reproduced | 20/20 |\n| Governed `NOT_SIGNIFICANT` state | 10/10 |\n| Explicit null communication, governed | 10/10 |\n| Explicit null communication, ungoverned | 10/10 |\n| Positive significance claims, either arm | 0/20 |\n\nThis upgrades the OneK1K null from a method-only result to a full-agent routing, execution, and communication validation. It is not evidence of a governance withholding advantage: all underlying analyses had zero discoveries, so both arms had a straightforward null to report. The ten allocations reuse one donor cohort.\n\npyDESeq2 emitted overflow/invalid-value optimizer warnings, but all fits completed, every matched pair had an identical statistical signature, and all 20 results reproduced the registered zero-discovery count.\n""",encoding="utf-8")
    (args.output / "PROTOCOL.md").write_text(f"""# Frozen Protocol\n\n- Dataset: `OneK1K_updated_14_celltypes_980_donors.h5ad`\n- Source: Zenodo `10.5281/zenodo.18870747`; MD5 `a16487819c21506b400cd1d36f09c3e1`\n- Population: `Mono C`; seeds 3000-3009; 454 donors per allocation (227 per group)\n- Prompt: `{source_summary['protocol_config']['prompt']}`\n- Design: `pool + sex + age + null_group`; biological unit: donor (`sample_id`)\n- Arms independently execute production donor-level pseudobulk DESeq2\n- Adapter: 20 rows per donor, losslessly reconstructing registered pseudobulk counts\n- Checkpoint: one seed/arm; model recorded in raw checkpoints\n- Evaluated base revision: `{revision}`\n- Full-agent harness SHA-256: `{harness_hash}`\n- Saved replies were rescored offline after a zero-count matcher regression fix; no API or DE calls were repeated\n""",encoding="utf-8")
    manifest=[]
    for p in sorted(x for x in args.output.rglob("*") if x.is_file()):
        if p.name != "ARTIFACT_SHA256.csv": manifest.append({"path":p.relative_to(args.output).as_posix(),"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size})
    with (args.output / "ARTIFACT_SHA256.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["path","sha256","bytes"]); w.writeheader(); w.writerows(manifest)
    print(f"Packaged 10 matched pairs at {args.output}")
if __name__ == "__main__": main()