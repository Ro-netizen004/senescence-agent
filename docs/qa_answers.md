# Q&A Answer Sheet -- Senescence Agent

Memorize these. Practice saying each answer in under 30 seconds.

---

## Q1: Why use a cloud LLM instead of GPT-4?

**Answer:** We use Google Gemini for tool routing, not for generating biology. Gemini was chosen because its function-calling API is well-documented, the free tier is sufficient for a hackathon, and it handles multi-turn tool chaining reliably. The LLM only decides which Scanpy tool to call -- it never writes the scientific results. A deterministic renderer handles all user-facing output.

**If pressed on privacy:** For production deployment with patient data, the architecture supports swapping in a local LLM (Ollama) since the LLM only routes tools -- it never sees raw expression values. The Scanpy analysis runs entirely locally regardless of which LLM is used.

---

## Q2: How do you know it didn't hallucinate the biology?

**Answer:** By design, it cannot. The LLM's only job is tool routing -- picking which Scanpy function to call. Every quantitative result (scores, p-values, fold changes) comes from real Scanpy code running on real data. We go further: our inference state machine classifies every result into states A through E, and a deterministic template renderer generates the user-facing text from tool facts. The LLM never writes the final answer. And every tool call is logged with its arguments and results in a downloadable report -- it's a complete audit trail.

---

## Q3: Why senescence specifically?

**Answer:** Senescence is one of the most well-funded areas in aging research. Calico, Altos Labs, and Unity Biotechnology are spending billions on it. But there's no existing LLM agent specialized for senescence detection. CellAgent is general-purpose scRNA-seq. CompBioAgent focuses on database exploration. ELISA uses embedding-based discovery. None of them have SenMayo scoring, age-stratified analysis, or senescence-specific statistical tests. That gap is our contribution.

---

## Q4: How does this compare to CellAgent?

**Answer:** CellAgent is a general-purpose multi-agent framework for scRNA-seq -- it automates QC, clustering, and annotation. We specialize in senescence. Our unique additions:
- Pre-loaded SenMayo 125-gene signature with automatic mouse/human gene mapping
- Age-comparison analysis across biological replicates
- Mann-Whitney U test on per-sample medians (not per-cell, which would be pseudoreplication)
- Pseudobulk DESeq2 for gene-level differential expression
- An inference state machine that prevents overclaiming from underpowered data

CellAgent could analyze any scRNA-seq dataset. Our tool gives you senescence-specific answers that CellAgent cannot.

---

## Q5: Why SenMayo instead of just p16 expression?

**Answer:** [Show the comparison table slide.] We tested three approaches on the same set of cells:
- Just CDKN2A (p16) expression threshold
- Just MKI67 absence (no proliferation)
- Full SenMayo 125-gene signature score

SenMayo catches more true senescent cells with fewer false positives than any single marker. p16 is not expressed in all senescent cell types -- it misses therapy-induced and some oncogene-induced senescence. MKI67 absence just means "not dividing" -- quiescent cells also lack MKI67. The full signature captures the multi-dimensional phenotype: growth arrest, SASP, nuclear changes, and DNA damage response.

---

## Q6: What happens with a dataset you've never seen?

**Answer:** [Demo it live if possible.] The agent doesn't memorize datasets -- it runs real Scanpy analysis every time. Upload any .h5ad file, pick mouse or human, and the pipeline runs: QC, normalization, clustering, then whatever analysis you ask for. The SenMayo genes are checked against whatever genes are in the dataset. Coverage varies -- kidney might have 60% of SenMayo genes, brain might have 40% -- but the scoring adapts to what's available.

**Have a held-out dataset on your laptop** (not TMS) that you've pre-tested to make sure it works.

---

## Q7: How do you handle mouse vs. human gene names?

**Answer:** Every endpoint takes a species parameter. Human genes are uppercase (CDKN1A, IL6, TP53). Mouse orthologs are title-cased (Cdkn1a, Il6), but some are non-trivial -- TP53 maps to Trp53, not Tp53, and human IL8 has no direct mouse ortholog so we use Cxcl15 as a proxy. Our gene_utils module calls the MyGene API for accurate conversion at startup, with a hardcoded fallback dictionary for critical genes. This runs once when the server starts and is cached.

---

## Q8: What was the hardest part?

**Answer honestly. Pick one of these depending on what actually happened:**

- "Getting the LLM to reliably call tools in the right order. Early on, Gemini would skip QC or try to call senescence_score before clustering. We solved this with deterministic routing for common patterns and a strict system prompt that enforces tool ordering."

- "The statistical methodology. We initially tested per-cell comparisons, which gave wildly significant p-values because 7,000 cells isn't 7,000 independent observations -- it's maybe 6 mice. We had to redesign to use per-sample medians, which is statistically correct but gives much more conservative results."

- "Preventing the LLM from hallucinating conclusions. We built an entire inference state machine and deterministic renderer to ensure the user never sees LLM-generated biology. That was the hardest engineering decision but the most important for scientific integrity."

---

## Q9: What about privacy/HIPAA compliance?

**Answer:** The Scanpy analysis runs entirely locally -- no expression data leaves the server. The only data sent to the cloud is the user's question text and tool selection metadata. For full HIPAA compliance, you'd swap Gemini for a local LLM via Ollama. The architecture is designed for this -- since the LLM only routes tools, even a smaller local model works.

---

## Q10: How long does analysis take?

**Answer:** Upload and preprocessing takes 10-30 seconds depending on dataset size. Each tool call takes 2-5 seconds. A full analysis panel (markers + scoring + UMAP + annotation + age comparison) completes in about 20-30 seconds total. DESeq2 pseudobulk analysis is the slowest at 10-15 seconds for large datasets.

---

## Q11: Could this work for other biological signatures beyond senescence?

**Answer:** Yes, and that's a planned extension. The scoring mechanism uses Scanpy's `score_genes`, which accepts any gene list. You could swap in an apoptosis signature, a stem cell signature, or a custom panel from your own research. The inference state machine and reporting would work the same way. But for this project, we deliberately specialized -- depth over breadth.

---

## Q12: How is the report generated? Is it AI-written?

**Answer:** No. The report is generated deterministically from the tool execution log. Every tool call is recorded with its name, arguments, and JSON result. The report module converts this into structured Markdown with embedded plots. No LLM prose appears in the report. This means reports are reproducible -- run the same tools with the same data, get the same report.
