"""
Paired governed vs ungoverned transcripts on a CONSTRUCTED NULL.

Builds a dataset where two "age" groups are a random split of one homogeneous
population (truth = no real difference), then asks the SAME question to:
  - the governed agent (AGENT_GOVERNANCE=on)
  - the ungoverned agent (AGENT_GOVERNANCE=off; per-cell tools, LLM narration)

Saves both replies side by side. The ungoverned arm should overclaim (report
significant DE / a real senescence difference) on data we know is null; the
governed arm should refuse or report no significant difference.

Requires GEMINI_API_KEY (ungoverned arm narrates via the LLM).

Usage:
    python eval/ablation/paired_transcripts.py
    python eval/ablation/paired_transcripts.py --cell-type "fenestrated cell" --seed 1
"""

import os
import sys
import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np
import scanpy as sc

from agent.pipeline import ensure_pipeline
from agent.cache import cache_adata
from agent import agent as agent_mod

OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DATA = ROOT / "backend" / "data" / "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"
MIN_CELLS_PER_SAMPLE = 20


def _mouse_sex(mouse_id: str) -> str:
    """TMS mouse ids encode sex as a trailing _M / _F."""
    s = str(mouse_id).rsplit("_", 1)[-1].upper()
    return s if s in ("M", "F") else "?"


def build_null_dataset(data_path: Path, cell_type: str, seed: int):
    """
    Subset to one cell type, then build a GENUINELY NULL split by restricting to
    mice of the SAME real age AND sex before randomly assigning them to two fake
    groups. Stratifying removes real age/sex signal, so any difference a method
    reports is a false positive (unlike a naive mixed-age split, which can be
    confounded by chance on a single draw).
    """
    adata = sc.read_h5ad(str(data_path))
    ensure_pipeline(adata, "mouse")
    profile = adata.uns.get("dataset_profile") or {}
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    sample_col = profile.get("sample_column") or "sample_id"
    age_col = profile.get("age_column") or "age"

    if not cell_type:
        counts = adata.obs.groupby([ct_col, sample_col], observed=True).size().unstack(fill_value=0)
        cell_type = (counts >= MIN_CELLS_PER_SAMPLE).sum(axis=1).sort_values(ascending=False).index[0]

    sub = adata[adata.obs[ct_col].astype(str) == str(cell_type)].copy()
    vc = sub.obs[sample_col].astype(str).value_counts()
    mice = sorted(vc[vc >= MIN_CELLS_PER_SAMPLE].index.tolist())
    if len(mice) < 4:
        raise SystemExit(f"Only {len(mice)} usable mice for {cell_type}; need >=4.")

    # Real (age, sex) per mouse.
    mouse_age = {m: str(sub.obs.loc[sub.obs[sample_col].astype(str) == m, age_col].iloc[0]) for m in mice}
    mouse_sex = {m: _mouse_sex(m) for m in mice}

    # Largest homogeneous (age, sex) stratum with >= 4 mice.
    from collections import defaultdict
    strata = defaultdict(list)
    for m in mice:
        strata[(mouse_age[m], mouse_sex[m])].append(m)
    homogeneous = sorted(
        [ms for ms in strata.values() if len(ms) >= 4], key=len, reverse=True
    )
    if homogeneous:
        pool = homogeneous[0]
        stratum = f"{mouse_age[pool[0]]} / sex {mouse_sex[pool[0]]}"
    else:
        # Fall back to largest single-age stratum (control age, not sex).
        by_age = defaultdict(list)
        for m in mice:
            by_age[mouse_age[m]].append(m)
        age_pools = sorted([ms for ms in by_age.values() if len(ms) >= 4], key=len, reverse=True)
        if not age_pools:
            raise SystemExit(
                f"No same-age (let alone same-sex) stratum with >=4 mice for {cell_type}. "
                f"Strata: { {k: len(v) for k, v in strata.items()} }"
            )
        pool = age_pools[0]
        stratum = f"{mouse_age[pool[0]]} / mixed sex"

    # Random split of the homogeneous pool into two fake groups.
    rng = np.random.default_rng(seed)
    perm = list(rng.permutation(pool))
    half = len(perm) // 2
    grp_young = set(perm[:half])
    grp_old = set(perm[half:2 * half])
    sub = sub[sub.obs[sample_col].astype(str).isin(grp_young | grp_old)].copy()

    new_age = np.where(sub.obs[sample_col].astype(str).isin(list(grp_young)), "3m", "24m")
    sub.obs["age"] = new_age
    sub.uns.pop("dataset_profile", None)  # refresh so the agent re-reads ages

    print(f"Homogeneous stratum used: {stratum} ({len(pool)} mice)")
    return sub, str(cell_type), sorted(grp_young), sorted(grp_old)


def _prompts(cell_type: str) -> list[str]:
    """Several phrasings of the same underlying (null) question, so the failure
    is shown to be robust to wording, not an artifact of one prompt."""
    return [
        (f"Run differential expression (run_deseq2) for '{cell_type}' between the "
         f"3m and 24m groups. Report how many genes are significantly differentially "
         f"expressed and state whether senescence differs significantly between the groups."),
        (f"Is senescence significantly higher in old (24m) versus young (3m) "
         f"'{cell_type}'? Give a yes/no answer and the evidence."),
        (f"Which genes are significantly upregulated with age in '{cell_type}' "
         f"(24m vs 3m)? How many reach significance?"),
        (f"Test whether '{cell_type}' shows a statistically significant age-related "
         f"senescence difference between 3m and 24m."),
    ]


def run_arm(mode: str, file_id: str, prompt: str) -> str:
    os.environ["AGENT_GOVERNANCE"] = mode  # 'on' or 'off'
    try:
        res = agent_mod.run_agent([], prompt, file_id, "mouse")
        return res.get("reply", "(no reply)")
    except Exception as e:
        return f"(arm failed: {e})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default=str(DEFAULT_DATA))
    ap.add_argument("--cell-type", type=str, default="")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        print("WARNING: GEMINI_API_KEY not set — the ungoverned arm needs it to narrate.")

    print("Building constructed-null dataset...")
    sub, cell_type, young, old = build_null_dataset(Path(args.data), args.cell_type, args.seed)

    file_id = "null_demo"
    cache_adata(file_id, sub)
    ensure_pipeline(sub, "mouse")  # sets profile on the cached object

    prompts = _prompts(cell_type)

    print(f"\nCell type: {cell_type}")
    print(f"Fake 'young' mice (random): {young}")
    print(f"Fake 'old'   mice (random): {old}")
    print(f"TRUTH: no real difference (random split). Expected DE genes = 0.")
    print(f"Prompts: {len(prompts)}\n")

    sections = []
    for i, prompt in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] governed ...")
        governed_reply = run_arm("on", file_id, prompt)
        print(f"[{i}/{len(prompts)}] ungoverned ...")
        ungoverned_reply = run_arm("off", file_id, prompt)
        sections.append(
            f"### Q{i}: {prompt}\n\n"
            f"**Governed (AGENT_GOVERNANCE=on):**\n\n{governed_reply}\n\n"
            f"**Ungoverned (AGENT_GOVERNANCE=off):**\n\n{ungoverned_reply}\n"
        )

    report = f"""# Paired Transcripts - Governed vs Ungoverned (Constructed Null)

**Dataset:** {Path(args.data).name}
**Cell type:** {cell_type}
**Construction:** mice randomly relabeled into two fake age groups (seed={args.seed}).
**Ground truth:** NO real difference. Any significant result is a false positive.

- Fake "3m" mice: {young}
- Fake "24m" mice: {old}

Each question below is asked, identically, to both arms. The governed agent uses
pseudobulk (per biological replicate) and the two-gate firewall; the ungoverned
agent uses per-cell tests, no gates, and LLM narration. On this null, every
significant claim from the ungoverned arm is a false positive.

---

""" + "\n---\n\n".join(sections)

    out = OUT_DIR / f"paired_transcripts_seed{args.seed}.md"
    out.write_text(report, encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
