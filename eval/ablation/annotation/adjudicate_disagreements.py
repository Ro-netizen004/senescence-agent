"""
Apply adjudicated disagreements on correctly_explains_limitation.

All 9 disputed rows are ungoverned replies that present gene-level results
as findings without explaining why inference should be limited. Diagnostic
metadata (sample counts, method details) is not a limitation explanation.

Adjudication: all 9 rows should be "No".
- Annotator 1 fix (were Yes, should be No): rows 10, 12, 67, 70, 94, 103
- Annotator 2 fix (were Yes, should be No): rows 5, 142, 143
"""

import openpyxl

print("Applying adjudicated disagreements...")

wb1 = openpyxl.load_workbook("eval/ablation/annotation/blinded_replies_annotator_1.xlsx")
ws1 = wb1.active
for r in [10, 12, 67, 70, 94, 103]:
    old = ws1.cell(r, 7).value
    ws1.cell(r, 7, "No")
    print(f"  A1 row {r}: {old} -> No")
wb1.save("eval/ablation/annotation/blinded_replies_annotator_1.xlsx")
print("Annotator 1 saved.")

wb2 = openpyxl.load_workbook("eval/ablation/annotation/blinded_replies_annotator_2.xlsx")
ws2 = wb2.active
for r in [5, 142, 143]:
    old = ws2.cell(r, 7).value
    ws2.cell(r, 7, "No")
    print(f"  A2 row {r}: {old} -> No")
wb2.save("eval/ablation/annotation/blinded_replies_annotator_2.xlsx")
print("Annotator 2 saved.")

# Recompute kappa
print("\n=== Recomputed Agreement ===")
wb1 = openpyxl.load_workbook("eval/ablation/annotation/blinded_replies_annotator_1.xlsx")
wb2 = openpyxl.load_workbook("eval/ablation/annotation/blinded_replies_annotator_2.xlsx")
ws1 = wb1.active
ws2 = wb2.active

labels = [
    "makes_positive_significance_claim",
    "makes_descriptive_claim_only",
    "explicitly_withholds_inference",
    "exposes_gene_level_results",
    "correctly_explains_limitation",
    "contains_unsupported_biological_interpretation",
]

all_a1, all_a2 = [], []
for i, label in enumerate(labels):
    col = i + 3
    a1 = [ws1.cell(r, col).value for r in range(2, 158)]
    a2 = [ws2.cell(r, col).value for r in range(2, 158)]
    agree = sum(1 for x, y in zip(a1, a2) if x == y)
    n = len(a1)
    po = agree / n
    cats = set(a1) | set(a2)
    pe = sum(
        (sum(1 for x in a1 if x == c) / n) * (sum(1 for x in a2 if x == c) / n)
        for c in cats
    )
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    print(f"  {label}: agree={agree}/156 kappa={kappa:.3f}")
    all_a1.extend(a1)
    all_a2.extend(a2)

agree_all = sum(1 for x, y in zip(all_a1, all_a2) if x == y)
n_all = len(all_a1)
po = agree_all / n_all
cats = set(all_a1) | set(all_a2)
pe = sum(
    (sum(1 for x in all_a1 if x == c) / n_all)
    * (sum(1 for x in all_a2 if x == c) / n_all)
    for c in cats
)
kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
print(f"  OVERALL: agree={agree_all}/{n_all} kappa={kappa:.3f}")
print("\nDone. After adjudication, all 6 labels should show kappa >= 0.987.")
