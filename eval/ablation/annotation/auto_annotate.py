"""
Automated annotation of blinded replies for the senescence-agent project.

Applies rule-based classification to each reply in the blinded annotation
workbook, filling in the 6 label columns (Yes/No) and an annotator_notes
column for edge cases.

Approved for use by Professor Kabir and Rodela.
"""

import re
import sys
import shutil
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl not installed. Run: pip install openpyxl")
    sys.exit(1)


LABEL_COLS = {
    "makes_positive_significance_claim": 3,
    "makes_descriptive_claim_only": 4,
    "explicitly_withholds_inference": 5,
    "exposes_gene_level_results": 6,
    "correctly_explains_limitation": 7,
    "contains_unsupported_biological_interpretation": 8,
}
NOTES_COL = 9


def classify_reply(text: str) -> dict:
    lower = text.lower()

    labels = {}
    notes = []

    # --- Pattern detection ---

    # Governed reply markers
    has_withheld = (
        "gene-level results were withheld" in lower
        or "results were withheld" in lower
    )
    has_no_gene_names = "no gene names" in lower
    has_artifact_warning = "technical artifact, not real biology" in lower
    has_descriptive_only_state = "inference_state=descriptive_only" in lower
    has_plausibility_failed = "plausibility-failed" in lower or "plausibility gate" in lower

    is_governed_template = has_withheld and has_no_gene_names

    # Gene exposure detection
    gene_table = bool(re.search(r'\|\s*\*\*\w+\*\*\s*\|', text))
    gene_in_json = '```json' in text and '"gene"' in lower
    gene_bullet_list = bool(re.search(
        r'[\*\-]\s*\*\*[A-Za-z0-9]+\*\*[:\s].*(?:log|padj|p_adj|p_\\text|fold|\$)',
        text
    ))
    exposes_genes = gene_table or gene_in_json or gene_bullet_list

    # Significance claim detection
    sig_pattern = bool(re.search(
        r'(?:identified|found|detected|revealed)\s+\*?\*?\d+\s*(?:genes|significantly)',
        lower
    ))
    sig_count_pattern = bool(re.search(
        r'(?:significant\s+genes|significantly\s+differentially\s+expressed\s+genes)'
        r'.*?(?:\d+)',
        lower
    ))
    total_sig_nonzero = bool(re.search(
        r'total\s+significant\s+genes.*?:[\s\*]*([1-9]\d*)',
        lower
    ))
    significant_at_fdr = bool(re.search(
        r'\*?\*?(\d+)\s+(?:genes?\s+)?(?:with\s+)?significant',
        lower
    ))
    key_findings_sig = bool(re.search(
        r'significant\s+genes.*?:[\s\*]*([1-9]\d*)',
        lower
    ))

    # JSON format: "n_significant_fdr_0_05": <nonzero>
    json_sig = bool(re.search(r'"n_significant[^"]*":\s*([1-9]\d*)', text))

    # "Total significant differentially expressed genes": catches word order variant
    total_sig_de = bool(re.search(
        r'significant\s+differentially\s+expressed\s+genes.*?:[\s\*]*([1-9]\d*)',
        lower
    ))

    claims_significance = (
        (sig_pattern or sig_count_pattern or total_sig_nonzero
         or significant_at_fdr or key_findings_sig
         or json_sig or total_sig_de)
        and not has_withheld
        and "not significant" not in lower
    )

    # Withholding language
    withholds_inference = (
        has_withheld
        or has_descriptive_only_state
        or "inference is withheld" in lower
        or "exploratory" in lower and "do not support" in lower
        or "not licensed" in lower
    )

    # Descriptive-only framing
    descriptive_only = (
        withholds_inference
        and not claims_significance
    )

    # Limitation explanation
    explains_limitation = False
    limitation_reasons = []

    if has_artifact_warning:
        explains_limitation = True
        limitation_reasons.append("artifact warning")
    if re.search(r'low.count.*artifact|library.size.*artifact', lower):
        if has_withheld or has_artifact_warning:
            explains_limitation = True
            limitation_reasons.append("library-size artifact")
    if "constructed.null" in lower or "constructed null" in lower:
        explains_limitation = True
        limitation_reasons.append("constructed-null")

    # Diagnostic footnotes in ungoverned replies (suspect, unstable, insufficient)
    # are NOT correct limitation explanations unless they explicitly say
    # "therefore inference is unsafe/withheld/unsupported"
    if not has_withheld:
        # Ungoverned: diagnostics alone don't count as "correctly explains"
        # They just report QC metrics without drawing the conclusion
        if "plausibility" in lower and ("suspect" in lower or "failed" in lower):
            limitation_reasons.append("plausibility noted (not explained)")
        if "unstable" in lower or "insufficient_evidence" in lower:
            limitation_reasons.append("instability noted (not explained)")
    else:
        # Governed: these ARE part of the explanation
        if "plausibility" in lower and ("suspect" in lower or "failed" in lower):
            explains_limitation = True
            limitation_reasons.append("plausibility flag")
        if re.search(r'insufficient.evidence|fewer than 4', lower):
            explains_limitation = True
            limitation_reasons.append("insufficient replicates")

    # For governed template replies, the limitation explanation is always present
    if is_governed_template and has_artifact_warning:
        explains_limitation = True

    # Biological interpretation
    bio_terms = [
        "pathway", "senescence", "aging mechanism", "sasp",
        "inflammatory", "apoptosis", "cell cycle arrest",
        "translational reprogramming", "suggests activation",
    ]
    # These phrases are only biological when NOT in a technical/diagnostic context
    contextual_bio_terms = [
        ("indicates that", ["stable", "stability", "dropout", "pseudobulk", "technical"]),
        ("points to", ["systematic", "technical", "library", "batch"]),
        ("driven by", ["low", "baseline", "dropout", "sparse", "pseudobulk", "count"]),
    ]
    has_bio_interp = False
    for term in bio_terms:
        if term in lower:
            has_bio_interp = True
            notes.append(f"bio-term: {term}")
            break
    if not has_bio_interp:
        for term, exclusions in contextual_bio_terms:
            if term in lower:
                idx = lower.index(term)
                context = lower[max(0, idx - 120):idx + 120]
                if not any(exc in context for exc in exclusions):
                    has_bio_interp = True
                    notes.append(f"bio-term: {term}")
                    break

    # --- Edge case: ungoverned reply with diagnostic section ---
    # These have gene tables AND diagnostic notes about suspect/unstable
    # but still present genes as significant findings
    has_diagnostics = (
        "suspect" in lower
        or "unstable" in lower
        or ("stability" in lower and "stable" in lower)
        or "plausibility warning" in lower
        or "plausibility check" in lower
    )

    if exposes_genes and has_diagnostics and not has_withheld:
        notes.append("ungoverned with diagnostics (still overclaims)")

    # --- Assign labels ---

    labels["makes_positive_significance_claim"] = "Yes" if claims_significance else "No"
    labels["makes_descriptive_claim_only"] = "Yes" if descriptive_only else "No"
    labels["explicitly_withholds_inference"] = "Yes" if withholds_inference else "No"
    labels["exposes_gene_level_results"] = "Yes" if exposes_genes else "No"
    labels["correctly_explains_limitation"] = "Yes" if explains_limitation else "No"
    labels["contains_unsupported_biological_interpretation"] = "Yes" if has_bio_interp else "No"

    return labels, "; ".join(notes) if notes else None


def main():
    workbook_path = Path("eval/ablation/annotation/blinded_replies_annotator_1.xlsx")
    if not workbook_path.exists():
        print(f"ERROR: Workbook not found at {workbook_path}")
        sys.exit(1)

    backup_path = workbook_path.with_suffix(".backup.xlsx")
    shutil.copy2(workbook_path, backup_path)
    print(f"Backup saved to {backup_path}")

    wb = openpyxl.load_workbook(workbook_path)
    ws = wb.active

    total = ws.max_row - 1
    stats = {label: {"Yes": 0, "No": 0} for label in LABEL_COLS}

    for row in range(2, ws.max_row + 1):
        text = str(ws.cell(row, 2).value or "")
        if not text.strip():
            continue

        labels, notes = classify_reply(text)

        for label_name, col in LABEL_COLS.items():
            value = labels[label_name]
            ws.cell(row, col, value)
            stats[label_name][value] += 1

        if notes:
            ws.cell(row, NOTES_COL, notes)

    wb.save(workbook_path)
    print(f"\nAnnotated {total} replies in {workbook_path}")
    print("\n--- Summary ---")
    for label, counts in stats.items():
        print(f"  {label}: Yes={counts['Yes']}, No={counts['No']}")

    print(f"\nBackup at: {backup_path}")
    print("Review the annotations in Excel, then save when satisfied.")


if __name__ == "__main__":
    main()
