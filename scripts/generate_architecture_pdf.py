"""Generate PDF from docs/senescence_agent_architecture.md (matplotlib, same style as reports)."""
import os
import re
import sys
import textwrap

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
MD_PATH = os.path.join(DOCS_DIR, "senescence_agent_architecture.md")
PDF_PATH = os.path.join(DOCS_DIR, "senescence_agent_architecture.pdf")


def strip_markdown_for_pdf(markdown: str) -> list[str]:
    lines = []
    in_code = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("```"):
            in_code = not in_code
            if in_code:
                lines.append("[code block]")
            continue

        if in_code:
            lines.append("  " + line)
            continue

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            text = line.lstrip("#").strip()
            lines.append(text.upper() if level == 1 else text)
            lines.append("")
            continue

        if line.startswith("|") and "|" in line[1:]:
            line = re.sub(r"\s*\|\s*", " | ", line.strip("| "))

        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"\*(.*?)\*", r"\1", line)
        line = re.sub(r"`(.*?)`", r"\1", line)
        line = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", line)
        lines.append(line)

    return lines


def markdown_to_pdf(md_path: str, pdf_path: str, max_lines: int = 46, wrap_width: int = 92) -> str:
    with open(md_path, encoding="utf-8") as f:
        markdown = f.read()

    lines = strip_markdown_for_pdf(markdown)
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    with PdfPages(pdf_path) as pdf:
        page_lines: list[str] = []

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
                fontsize=9,
                family="DejaVu Sans Mono",
                linespacing=1.2,
            )
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
            page_lines.clear()

        for line in lines:
            wrapped = (
                textwrap.wrap(line, width=wrap_width, replace_whitespace=False)
                if line
                else [""]
            )
            for wrapped_line in wrapped:
                page_lines.append(wrapped_line)
                if len(page_lines) >= max_lines:
                    flush_page()
        flush_page()

    return pdf_path


if __name__ == "__main__":
    if not os.path.isfile(MD_PATH):
        print(f"Missing: {MD_PATH}", file=sys.stderr)
        sys.exit(1)
    out = markdown_to_pdf(MD_PATH, PDF_PATH)
    print(f"Wrote {out}")
