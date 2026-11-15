"""Acquire pinned official E1 documentation; no outcome analysis or model calls."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "eval/results/v2/e1/e1_v2_1_20261022_01/sources"
COMMIT = "aa5c84a973c0e1a090b0072dc5b080bf7fbbed38"
FILES = [
    "README.md", "LICENSE", "metadata/README.md", "metadata/data_sharing_readme.md",
    "metadata/sgRNA_library_curated.csv", "metadata/suppl_tables/sample_metadata.suppl_table.csv",
    "src/3_DE_analysis/make_pseudobulk.py", "src/3_DE_analysis/DE_config_full.yaml",
    "src/3_DE_analysis/DE_analysis_utils.py", "src/3_DE_analysis/README.md",
    "src/3_DE_analysis/prep_DE.ipynb", "src/1_preprocess/preprocess.py",
    "src/1_preprocess/sgrna_assignment.py", "metadata/suppl_tables/validation_donor_metadata.csv",
    "metadata/suppl_tables/md_for_manuscript/Supplementary_Table_11_IL10IL21_flow_cytometry_validation.md",
]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    sources = [(p, f"https://raw.githubusercontent.com/emdann/GWT_perturbseq_analysis_2025/{COMMIT}/{p}") for p in FILES]
    sources += [
        ("geo_GSE314342.txt", "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE314342&targ=self&form=text&view=full"),
        ("vcp_dataset.html", "https://virtualcellmodels.cziscience.com/dataset/genome-scale-tcell-perturb-seq"),
    ]
    for name, url in sources:
        destination = OUT / name
        record = {"path": name, "url": url, "commit": COMMIT if name in FILES else None}
        try:
            if destination.exists():
                payload = destination.read_bytes()
                record["acquisition"] = "already_staged"
            else:
                with urlopen(Request(url, headers={"User-Agent": "E1-research-audit"}), timeout=45) as response:
                    payload = response.read()
                    record["final_url"] = response.url
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
                record["acquisition"] = "downloaded"
            record.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), timestamp=datetime.now(timezone.utc).isoformat())
            print(name, len(payload))
        except Exception as exc:
            record["error"] = str(exc)
            print(name, type(exc).__name__)
        records.append(record)
    (OUT / "SOURCE_ACQUISITION.json").write_text(json.dumps(records, indent=2) + "\n")

if __name__ == "__main__":
    main()
