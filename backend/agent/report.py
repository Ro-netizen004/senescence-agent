import os
import re
import textwrap
import uuid
from datetime import datetime
from typing import Iterable

import google.generativeai as genai
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt


REPORT_MODEL = os.getenv("REPORT_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
REPORT_API_KEY = os.getenv("REPORT_GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))


REPORT_SYSTEM_PROMPT = """
You are a careful scientific report writer for single-cell RNA-seq aging analysis.
Write a structured Markdown report using only the supplied source material.

Rules:
- Do not invent datasets, genes, p-values, plots, methods, or conclusions.
- If a requested detail is absent, say it was not available in the supplied analysis.
- Distinguish descriptive SenMayo score trends from statistical differential expression.
- Treat global senescence scores as descriptive and potentially confounded by cell-type composition.
- For DESeq2, report the contrast direction and explain that positive log2FC means higher expression in the comparison group.
- Keep biological interpretation cautious and directly tied to the supplied results.
- Do not claim absence of biological change. Say "not detected at the chosen threshold" or "not statistically significant".
- If no genes pass FDR < 0.05, include at most 5 exploratory ranked genes.
- Markdown tables must be valid GitHub-flavored Markdown: header row, separator row, and every data row must be on its own line.
- Avoid wide tables when prose or a short bullet list would be clearer.
"""


def _compact_history(session_history: Iterable[dict], max_messages: int = 18) -> str:
    messages = list(session_history)[-max_messages:]
    lines = []

    for msg in messages:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"{role.upper()}:\n{content}")

    return "\n\n---\n\n".join(lines)


def generate_report(
    session_history: list,
    file_id: str,
    species: str,
) -> str:
    source_material = _compact_history(session_history)

    if not source_material:
        return (
            "# Single-cell Aging Analysis Report\n\n"
            "No completed analysis messages were available yet. Run one or more analyses first, then generate a report."
        )

    if not REPORT_API_KEY:
        return "Report generation failed: REPORT_GEMINI_API_KEY or GEMINI_API_KEY is not configured."

    genai.configure(api_key=REPORT_API_KEY)

    model = genai.GenerativeModel(
        model_name=REPORT_MODEL,
        system_instruction=REPORT_SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(temperature=0.1),
    )

    prompt = f"""
Create a concise but informative Markdown report from the supplied analysis transcript.

Dataset metadata:
- file_id: {file_id}
- species: {species}

Required sections:
1. Title
2. Executive Summary
3. Analyses Performed
4. Key Results
5. Differential Expression Findings
6. Senescence and Age Trends
7. Caveats and Interpretation Limits
8. Reproducibility Notes

Source material:
{source_material}
"""

    response = model.generate_content(prompt)
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
