import json
import os
import re
import textwrap
import uuid
from datetime import datetime
from typing import Any, Iterable, Optional

from google import genai
from google.genai import types
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt


REPORT_MODEL = os.getenv("REPORT_MODEL", os.getenv("GEMINI_MODEL", "gemini-flash-latest"))
REPORT_API_KEY = os.getenv("REPORT_GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))

MAX_DESEQ2_GENES_IN_REPORT = 15


REPORT_SYSTEM_PROMPT = """
You are a careful scientific report writer for single-cell RNA-seq aging analysis.
Write a structured Markdown report using only the supplied source material.

The primary source is the TOOL EXECUTION LOG: each entry is a tool name, its arguments, and the structured result returned by the pipeline.
Optional USER QUESTIONS list what the researcher asked; do not treat assistant chat prose as authoritative data.

Rules:
- Do not invent datasets, genes, p-values, plots, methods, or conclusions.
- If a requested detail is absent from the tool log, say it was not available in the supplied analysis.
- Distinguish descriptive SenMayo score trends from statistical differential expression.
- Treat global senescence scores as descriptive and potentially confounded by cell-type composition.
- For DESeq2, report the contrast direction and explain that positive log2FC means higher expression in the comparison group.
- Keep biological interpretation cautious and directly tied to the tool results.
- Do not claim absence of biological change. Say "not detected at the chosen threshold" or "not statistically significant".
- Each tool result may include inference_state (A–E). Use the deterministic strict_output_schema if present.
- LOW_POWER / NOT_SIGNIFICANT / DESCRIPTIVE_ONLY: numeric facts only; no biological mechanism.
- SIGNIFICANT_INFERENTIAL: may state statistical significance at sample/gene level only; no causality.
- If no genes pass FDR < 0.05, include at most 5 exploratory ranked genes from the DESeq2 tool result.
- Markdown tables must be valid GitHub-flavored Markdown: header row, separator row, and every data row must be on its own line.
- Avoid wide tables when prose or a short bullet list would be clearer.
"""


def _sanitize_result_for_report(result: Any) -> Any:
    if isinstance(result, dict):
        out = {}
        for key, value in result.items():
            if key in ("age_distribution_plot", "senescence_violin_plot", "plot_path"):
                out[key] = os.path.basename(str(value)) if value else value
                continue
            if key == "results" and isinstance(value, list) and len(value) > MAX_DESEQ2_GENES_IN_REPORT:
                out["results"] = value[:MAX_DESEQ2_GENES_IN_REPORT]
                out["results_note"] = (
                    f"Gene table truncated to top {MAX_DESEQ2_GENES_IN_REPORT} rows "
                    f"of {len(value)} returned by DESeq2."
                )
                continue
            if key == "cell_type_proportions" and isinstance(value, dict):
                out[key] = value
                continue
            out[key] = _sanitize_result_for_report(value)
        return out
    if isinstance(result, list):
        return [_sanitize_result_for_report(item) for item in result[:50]]
    return result


def _format_tool_runs(tool_runs: Iterable[dict]) -> str:
    runs = list(tool_runs)
    if not runs:
        return ""

    blocks = []
    for i, run in enumerate(runs, start=1):
        name = run.get("name", "unknown_tool")
        args = run.get("args") or {}
        result = _sanitize_result_for_report(run.get("result"))

        inf_state = None
        if isinstance(result, dict):
            inf_state = result.get("inference_state")

        blocks.append(f"### Tool run {i}: {name}")
        if inf_state:
            blocks.append(
                "Inference state:\n```json\n"
                + json.dumps(inf_state, indent=2, default=str)
                + "\n```"
            )
        if args:
            blocks.append(
                "Arguments:\n```json\n"
                + json.dumps(args, indent=2, default=str)
                + "\n```"
            )
        blocks.append(
            "Result:\n```json\n"
            + json.dumps(result, indent=2, default=str)
            + "\n```"
        )

    return "\n\n".join(blocks)


def _compact_user_questions(session_history: Optional[Iterable[dict]], max_messages: int = 12) -> str:
    if not session_history:
        return ""

    lines = []
    for msg in list(session_history)[-max_messages:]:
        if msg.get("role") != "user":
            continue
        content = str(msg.get("content", "")).strip()
        if content:
            lines.append(f"- {content}")

    return "\n".join(lines)


def generate_report(
    file_id: str,
    species: str,
    tool_runs: Optional[list] = None,
    session_history: Optional[list] = None,
) -> str:
    tool_runs = tool_runs or []
    tool_log = _format_tool_runs(tool_runs)
    user_questions = _compact_user_questions(session_history)

    if not tool_log:
        return (
            "# Single-cell Aging Analysis Report\n\n"
            "No tool results were available yet. Run one or more analyses in chat "
            "(e.g. senescence score, age comparison, DESeq2) before generating a report."
        )

    if not REPORT_API_KEY:
        return "Report generation failed: REPORT_GEMINI_API_KEY or GEMINI_API_KEY is not configured."

    user_section = (
        f"## User questions (context only)\n{user_questions}"
        if user_questions
        else "## User questions\n(none recorded)"
    )

    prompt = f"""
Create a concise but informative Markdown report from the tool execution log below.

Dataset metadata:
- file_id: {file_id}
- species: {species}
- tools executed: {len(tool_runs)}

Required sections:
1. Title
2. Executive Summary
3. Analyses Performed (list each tool run and its purpose)
4. Key Results (quantitative facts from tool results only)
5. Differential Expression Findings (from run_deseq2 if present)
6. Senescence and Age Trends (from senescence_score / compare_across_age if present)
7. Caveats and Interpretation Limits
8. Reproducibility Notes (tools run, contrasts used, cell types filtered)

{user_section}

## Tool execution log (authoritative)
{tool_log}
"""

    client = genai.Client(api_key=REPORT_API_KEY)
    response = client.models.generate_content(
        model=REPORT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=REPORT_SYSTEM_PROMPT,
            temperature=0.1,
        ),
    )
    return (response.text or "").strip() or "Report generation completed, but the model returned an empty report."


def _strip_markdown_for_pdf(markdown: str) -> list[str]:
    lines = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            text = line.lstrip("#").strip()
            lines.append(text.upper() if level == 1 else text)
            lines.append("")
            continue

        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"\*(.*?)\*", r"\1", line)
        line = re.sub(r"`(.*?)`", r"\1", line)
        line = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", line)
        lines.append(line)

    return lines


def _append_plot_markdown(report_text: str, plot_urls: list[str] | None) -> str:
    if not plot_urls:
        return report_text

    lines = [report_text.rstrip(), "", "## Generated Plots", ""]

    for i, url in enumerate(plot_urls, start=1):
        label, description = _describe_plot(url)
        lines.extend([
            f"### Figure {i}. {label}",
            "",
            description,
            "",
            f"![{label}]({url})",
            "",
        ])

    return "\n".join(lines).strip()


def _describe_plot(path_or_url: str) -> tuple[str, str]:
    text = path_or_url.lower()

    if "senescence_score" in text:
        return (
            "SenMayo Senescence Score UMAP",
            "Cells embedded by UMAP and colored by SenMayo signature score.",
        )

    if "age_distribution" in text:
        return (
            "Cell Counts by Age Group",
            "Number of cells represented in each age group.",
        )

    if "senescence_violin" in text:
        return (
            "Senescence Score Distribution by Age",
            "Distribution of SenMayo scores across age groups.",
        )

    if "umap" in text:
        return (
            "Cell Cluster UMAP",
            "Two-dimensional UMAP embedding colored by Leiden cluster.",
        )

    filename = os.path.basename(path_or_url)
    label = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
    return label, "Generated analysis plot."


def save_report_files(
    report_text: str,
    output_dir: str,
    plot_paths: list[str] | None = None,
    plot_urls: list[str] | None = None,
) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    report_text = _append_plot_markdown(report_text, plot_urls)
    report_id = f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    markdown_path = os.path.join(output_dir, f"{report_id}.md")
    pdf_path = os.path.join(output_dir, f"{report_id}.pdf")

    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    lines = _strip_markdown_for_pdf(report_text)

    with PdfPages(pdf_path) as pdf:
        page_lines = []
        max_lines = 46

        def flush_page():
            if not page_lines:
                return

            fig = plt.figure(figsize=(8.5, 11))
            fig.patch.set_facecolor("white")
            fig.text(
                0.07,
                0.95,
                "\n".join(page_lines),
                ha="left",
                va="top",
                fontsize=9.5,
                family="DejaVu Sans Mono",
                linespacing=1.25,
            )
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
            page_lines.clear()

        for line in lines:
            wrapped = textwrap.wrap(line, width=92, replace_whitespace=False) if line else [""]
            for wrapped_line in wrapped:
                page_lines.append(wrapped_line)
                if len(page_lines) >= max_lines:
                    flush_page()

        flush_page()

        for i, plot_path in enumerate(plot_paths or [], start=1):
            if not os.path.exists(plot_path):
                continue

            image = plt.imread(plot_path)
            fig = plt.figure(figsize=(8.5, 11))
            fig.patch.set_facecolor("white")
            ax = fig.add_axes([0.08, 0.12, 0.84, 0.78])
            ax.imshow(image)
            ax.axis("off")

            label, description = _describe_plot(plot_path)
            fig.text(
                0.08,
                0.93,
                f"Figure {i}. {label}",
                ha="left",
                va="top",
                fontsize=13,
                weight="bold",
                family="DejaVu Sans",
            )
            fig.text(
                0.08,
                0.9,
                description,
                ha="left",
                va="top",
                fontsize=9.5,
                family="DejaVu Sans",
            )
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    return {
        "report_id": report_id,
        "markdown_path": markdown_path,
        "pdf_path": pdf_path,
    }
