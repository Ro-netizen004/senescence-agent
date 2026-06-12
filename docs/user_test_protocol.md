# User Test Protocol -- Senescence Agent

**Target date:** Week 6 (June 15-21, 2026)
**Duration:** 20-30 minutes per participant
**Participants:** Fei He (mentor) or a lab graduate student working on aging biology
**Owners:** Aviral (protocol + quote capture), Rodela (technical support)

---

## Objectives

1. Validate that a non-computational biologist can use the tool to get meaningful results
2. Identify the top 3 usability issues
3. Capture a quotable endorsement for the final slide

---

## Pre-Test Setup (Aviral)

- [ ] Backend running and tested within 1 hour of the session
- [ ] Frontend running at localhost:5173
- [ ] TMS kidney dataset pre-loaded as example data
- [ ] A second dataset (TMS lung or spleen) available for the user to upload themselves
- [ ] Screen recording software running (OBS or built-in)
- [ ] Notebook ready for handwritten observations
- [ ] Browser cleared of history/tabs -- clean state

---

## Test Script

### Introduction (2 minutes)

Read this exactly:

> "Thank you for helping us test our tool. We've built an AI agent that helps biologists analyze single-cell RNA-seq data for senescence without programming. We'd like you to try using it for about 20 minutes.
>
> Please think aloud as you work -- tell us what you're trying to do, what you expect to happen, and anything that confuses you. There are no wrong answers. We're testing the tool, not you.
>
> We will not help you unless you're completely stuck. We want to see where the tool succeeds and fails on its own."

### Task 1: Explore Example Data (5 minutes)

**Prompt to user:**

> "We've pre-loaded a mouse kidney dataset from Tabula Muris Senis. This dataset has cells from mice aged 3 months to 24 months. Can you find out if any cell types become more senescent with age?"

**Observe and record:**
- How long before first interaction?
- Does the user understand what to type?
- Does the user understand the response?
- Any confusion about plots or results?

### Task 2: Ask a Specific Question (5 minutes)

**Prompt to user:**

> "Can you find out whether the senescence difference in T cells between young and old mice is statistically significant?"

**Observe and record:**
- Does the user know how to phrase the question?
- Does the user understand the p-value result?
- Does the user understand the inference state (e.g., LOW_POWER)?
- Any confusion about "per-sample" vs "per-cell"?

### Task 3: Upload New Data (5 minutes)

**Prompt to user:**

> "Here's a different dataset -- mouse lung. Can you upload it and run a quick senescence analysis?"

**Give them the .h5ad file on a USB drive or shared folder.**

**Observe and record:**
- Is the upload flow intuitive?
- Does the species selector make sense?
- How long until they see results?
- Any errors or loading issues?

### Task 4: Generate Report (3 minutes)

**Prompt to user:**

> "Can you download a report of what you've found so far?"

**Observe and record:**
- Can the user find the Download Report button?
- Does the report make sense to them?
- Would they share this with a collaborator?

---

## Post-Test Interview (5-10 minutes)

Ask these questions in order. Write down answers verbatim.

1. "What was the most useful thing about this tool?"
2. "What was the most confusing part?"
3. "Is there anything you expected to be able to do but couldn't?"
4. "If you had a dataset from your own research, would you use this tool to analyze it?"
5. "How does this compare to your current workflow for single-cell analysis?"

### The Quote Question (Critical)

After question 4, if the answer is positive:

> "Would you mind if we used a quote from you in our presentation? It can be anonymous -- just something like 'I would use this for my aging dataset analysis.' Is that okay?"

**Record their exact words. Get verbal permission.**

Example quotes to hope for:
- "I would actually use this for my aging dataset analysis."
- "This would save me hours of programming."
- "I didn't know you could do this without coding."

---

## Observation Template

Use this for each task:

```
Task #: ___
Time to first action: ___
Hesitations/confusion: ___
Errors encountered: ___
User's verbal comments: ___
Completed successfully? Y/N
```

---

## After the Test

### Same day:
1. Review notes with Rodela
2. Identify top 3 issues by severity
3. File issues or fix them directly

### Within 48 hours:
1. Fix the top 3 issues
2. Update the presentation with any quote captured
3. If the user approved a quote, add it to the results slide:

```
Pull-quote box format:
+----------------------------------------------+
|                                               |
|  "I would actually use this for my           |
|   aging dataset analysis."                    |
|                                               |
|  -- Graduate Student, Aging Biology Lab       |
|                                               |
+----------------------------------------------+
```

---

## Fallback Plan

If Fei He is unavailable:
- Ask a graduate student in any computational biology lab
- Ask a fellow hackathon participant who works with scRNA-seq
- Last resort: ask a biology undergraduate to test basic usability (upload + chat flow)
