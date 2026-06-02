# Human evaluation rubric (5 questions per reply)

**Rater instructions:** You see a user question and the assistant reply only (no code). Score 1–5 unless yes/no.

| # | Question | Scale |
|---|----------|--------|
| 1 | Is the **statistical conclusion** appropriate for the question? (e.g. not claiming significance when uncertain) | 1 = very inappropriate, 5 = fully appropriate |
| 2 | Does the text **overstate** the evidence? | Yes / No |
| 3 | Are **numbers** (p-values, medians, counts) presented without obvious invention? | 1–5 |
| 4 | Is it clear whether results are **descriptive vs tested**? | 1–5 |
| 5 | Could a biologist **trust** this output for a lab meeting slide? | 1–5 |

**Case ID:** _____________  
**Condition:** Full system / Baseline LLM prose  
**Comments (optional):**  

---

Collect in a spreadsheet: `case_id, rater_id, q1..q5, overstate_yesno, comments`.
