"""Stage published evaluator reference sources; never send them to the agent."""
import hashlib
import json
from datetime import datetime, timezone
from urllib.request import Request,urlopen
from acquire_sources import OUT,COMMIT

def main():
    sources = [
        "metadata/suppl_tables/IL10IL21bulkRNAseq_DESeq2_results_bygene.csv",
        "metadata/suppl_tables/IL10_IL21_arrayed_validation_combined.csv",
        "metadata/suppl_tables/sgrna_library_metadata.suppl_table.csv",
        "src/5_cytokine_regulators/cytokine_followup_regulator.ipynb",
    ]
    entries=[]
    for path,url in [(p,f"https://raw.githubusercontent.com/emdann/GWT_perturbseq_analysis_2025/{COMMIT}/{p}") for p in sources]+[("paper_PMC13614707.html","https://pmc.ncbi.nlm.nih.gov/articles/PMC13614707/?pdf=0")]:
        dest=OUT/path
        entry={"path":path,"url":url}
        try:
            if dest.exists():
                raise FileExistsError("source already staged; do not repeat")
            with urlopen(Request(url,headers={"User-Agent":"E1-source-audit"}),timeout=60) as r:
                data=r.read()
                entry["resolved_url"]=r.url
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(data)
            entry.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),retrieved_at=datetime.now(timezone.utc).isoformat())
            print(path,len(data),flush=True)
        except Exception as e:
            entry["error"]=str(e)
        entries.append(entry)
    (OUT/"REFERENCE_ACQUISITION.json").write_text(json.dumps(entries,indent=2)+"\n")

if __name__ == "__main__":
    main()
