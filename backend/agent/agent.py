import os
import json
import tempfile
import scanpy as sc
import google.generativeai as genai
 
from dotenv import load_dotenv
 
from tools.visualization import generate_umap
from tools.senescence import find_senescence_markers, senescence_score, get_cluster_annotations
from tools.age_analysis import compare_across_age
from tools.run_deseq2 import run_deseq2_pseudobulk
from agent.cache import get_adata, cache_adata
from agent.pipeline import ensure_pipeline
from agent.tool_schema import TOOLS
from agent.tool_router import build_tool_map
from agent.system_prompt import SYSTEM_PROMPT
 
 
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))
 
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

DEFAULT_AGENT_ITERATIONS = int(os.getenv("DEFAULT_AGENT_ITERATIONS", "2"))
FULL_PIPELINE_AGENT_ITERATIONS = int(os.getenv("FULL_PIPELINE_AGENT_ITERATIONS", "4"))


def _agent_iteration_limit(message: str) -> int:
    """
    Keep routine tool requests cheap, but allow broader exploratory workflows
    to use more than one tool/result exchange.
    """
    text = message.lower()
    full_pipeline_phrases = (
        "full pipeline",
        "entire pipeline",
        "complete pipeline",
        "comprehensive analysis",
        "full analysis",
        "analyze everything",
        "run everything",
        "multi-step",
        "end-to-end",
    )

    if any(phrase in text for phrase in full_pipeline_phrases):
        return FULL_PIPELINE_AGENT_ITERATIONS

    return DEFAULT_AGENT_ITERATIONS


DIRECT_SUMMARY_TOOLS = {
    "generate_umap",
    "find_senescence_markers",
    "senescence_score",
    "get_cluster_annotations",
    "run_deseq2",
    "compare_across_age",
}


def _fmt(value, digits=4):
    if value is None:
        return "NA"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number != number:
        return "NA"
    return f"{number:.{digits}g}"


def _to_float(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number


def _format_deseq2_summary(args: dict, result: dict) -> str:
    rows = result.get("results", [])
    cell_type = args.get("cell_type") or "the selected cell type"
    youngest = result.get("youngest_group") or "young"
    oldest = result.get("oldest_group") or "old"
    valid_rows = [r for r in rows if _to_float(r.get("padj")) is not None]
    significant = [
        r for r in valid_rows
        if _to_float(r.get("padj"), 1) < 0.05
    ]
    up = [r for r in significant if _to_float(r.get("log2FoldChange"), 0) > 0]
    down = [r for r in significant if _to_float(r.get("log2FoldChange"), 0) < 0]
    top_rows = valid_rows[:10]

    lines = [
        f"Differential expression analysis completed for {cell_type}.",
        "",
        f"Comparison: {oldest} vs {youngest}. Positive log2 fold change means higher expression in {oldest}; negative means higher expression in {youngest}.",
        f"Returned genes: top {len(rows)} ranked by adjusted p-value.",
        f"Significant genes at FDR < 0.05: {len(significant)} ({len(up)} higher in {oldest}, {len(down)} higher in {youngest}).",
    ]

    if top_rows:
        if significant:
            lines.extend(["", "Top significant/ranked genes:"])
        else:
            lines.extend([
                "",
                "No genes passed FDR < 0.05. The genes below are the lowest-adjusted-p-value ranked genes, not statistically significant hits:",
            ])
        for i, row in enumerate(top_rows, start=1):
            direction = (
                f"higher in {oldest}"
                if _to_float(row.get("log2FoldChange"), 0) > 0
                else f"higher in {youngest}"
            )
            lines.append(
                f"{i}. {row.get('gene', 'unknown')}: log2FC {_fmt(row.get('log2FoldChange'))}, "
                f"padj {_fmt(row.get('padj'))}, baseMean {_fmt(row.get('baseMean'))} ({direction})"
            )

    lines.extend([
        "",
        "Interpretation note: DESeq2 was run on sample-level pseudobulk counts, which is the right level for age comparisons because it avoids treating individual cells as independent biological replicates.",
    ])
    return "\n".join(lines)


def _format_age_summary(result: dict) -> str:
    ages = result.get("age_groups", [])
    age_counts = result.get("age_counts", {})
    most_senescent = result.get("most_senescent_per_celltype", {})
    global_scores = result.get("global_senescence_by_age", {})

    lines = [
        "Age-stratified senescence analysis completed.",
        "",
        f"Total cells analyzed: {result.get('total_cells', 'NA')}",
        f"Age groups: {', '.join(map(str, ages)) if ages else 'NA'}",
    ]

    if age_counts:
        lines.append("Cell counts by age: " + ", ".join(f"{age}: {count}" for age, count in age_counts.items()))

    if global_scores:
        lines.extend([
            "",
            "Global senescence by age, descriptive only:",
            ", ".join(f"{age}: {_fmt(score)}" for age, score in global_scores.items()),
            "Do not use the global values alone to rank aging, because cell-type composition can confound them.",
        ])

    if most_senescent:
        lines.extend(["", "Highest-scoring age within each cell type:"])
        for cell_type, info in list(most_senescent.items())[:12]:
            lines.append(f"- {cell_type}: {info.get('age')} (median score {_fmt(info.get('score'))})")

    plots = [
        result.get("age_distribution_plot"),
        result.get("senescence_violin_plot"),
    ]
    plots = [p for p in plots if p]
    if plots:
        lines.extend(["", "Generated plots: " + ", ".join(plots)])

    return "\n".join(lines)


def _format_senescence_score_summary(result: dict) -> str:
    cluster_scores = result.get("cluster_scores", {})
    lines = [
        "SenMayo senescence scoring completed.",
        "",
        f"Genes used: {result.get('genes_used', 'NA')} of {result.get('total_senmayo_genes', 'NA')} SenMayo genes present in the dataset.",
        f"Mean cell score: {_fmt(result.get('mean_score'))}",
        f"Maximum cell score: {_fmt(result.get('max_score'))}",
        f"Top senescent cluster: {result.get('top_senescent_cluster', 'NA')}",
        f"Top senescent cell type: {result.get('top_senescent_cell_type', 'NA')}",
    ]

    if cluster_scores:
        lines.extend(["", "Highest-scoring clusters:"])
        for cluster, score in list(cluster_scores.items())[:10]:
            lines.append(f"- {cluster}: {_fmt(score)}")

    if result.get("plot_path"):
        lines.extend(["", f"Generated plot: {result['plot_path']}"])

    return "\n".join(lines)


def _format_marker_summary(result: dict) -> str:
    found = result.get("found_markers", [])
    missing = result.get("missing_markers", [])
    lines = [
        "SenMayo marker coverage check completed.",
        "",
        f"Species setting: {result.get('species', 'NA')}",
        f"Coverage: {len(found)} found, {len(missing)} missing ({_fmt(result.get('coverage_pct'), 3)}%).",
    ]

    if found:
        lines.append("Found markers: " + ", ".join(found[:30]) + ("..." if len(found) > 30 else ""))
    if missing:
        lines.append("Missing markers: " + ", ".join(missing[:30]) + ("..." if len(missing) > 30 else ""))

    return "\n".join(lines)


def _format_cluster_summary(result: dict) -> str:
    annotations = result.get("cluster_annotations", {})
    distributions = result.get("cluster_distributions", {})
    lines = [
        "Cluster annotation summary completed.",
        "",
        f"Total clusters: {result.get('total_clusters', len(annotations))}",
        "Dominant cell type by cluster:",
    ]

    for cluster, cell_type in list(annotations.items())[:20]:
        dist = distributions.get(cluster, {})
        purity = dist.get(cell_type)
        purity_text = f", {round(purity * 100, 1)}% of cells" if isinstance(purity, (int, float)) else ""
        lines.append(f"- Cluster {cluster}: {cell_type}{purity_text}")

    return "\n".join(lines)


def _format_direct_tool_summary(name: str, args: dict, result) -> str:
    if isinstance(result, dict) and result.get("error"):
        return f"{name} could not complete: {result['error']}"

    if name == "run_deseq2" and isinstance(result, dict):
        return _format_deseq2_summary(args, result)
    if name == "compare_across_age" and isinstance(result, dict):
        return _format_age_summary(result)
    if name == "senescence_score" and isinstance(result, dict):
        return _format_senescence_score_summary(result)
    if name == "find_senescence_markers" and isinstance(result, dict):
        return _format_marker_summary(result)
    if name == "get_cluster_annotations" and isinstance(result, dict):
        return _format_cluster_summary(result)
    if name == "generate_umap":
        return (
            "UMAP generation completed.\n\n"
            f"Generated plot: {result}\n"
            "The plot is colored by Leiden cluster, so it is useful for checking whether the dataset has coherent cell populations before interpreting downstream senescence or age analyses."
        )

    return f"{name} completed successfully."
 
 
def _to_gemini_history(session_history: list) -> list:
    """Convert flat role/content history to Gemini parts format."""
    converted = []
    for msg in session_history:
        role = msg["role"]
        # Gemini only accepts 'user' and 'model' roles
        if role == "assistant":
            role = "model"
        elif role not in ("user", "model"):
            continue
        converted.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })
    return converted
 
 
def run_agent(
    session_history: list,
    message: str,
    file_id: str,
    species: str
) -> dict:
 
    adata = get_adata(file_id)
 
    if adata is None:
        file_path = os.path.join(tempfile.gettempdir(), f"{file_id}.h5ad")
 
        if not os.path.exists(file_path):
            return {
                "reply": "Dataset not found. Please upload your file again.",
                "plots": [],
                "tool_calls": []
            }
 
        print(f"Loading dataset {file_id} into memory...")
        adata = sc.read_h5ad(file_path)
        cache_adata(file_id, adata)
 
    # ── pipeline ──────────────────────────────────────────────────────
    ensure_pipeline(adata, species)
 
    # ── tool map ──────────────────────────────────────────────────────
    tool_map = build_tool_map(
        adata,
        species,
        {
            "generate_umap": generate_umap,
            "find_senescence_markers": find_senescence_markers,
            "senescence_score": senescence_score,
            "get_cluster_annotations": get_cluster_annotations,
            "compare_across_age": compare_across_age,
            "run_deseq2": run_deseq2_pseudobulk,
        }
    )
 
    # ── Gemini client ─────────────────────────────────────────────────
    model = genai.GenerativeModel(
        model_name=MODEL,
        tools=TOOLS,
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(temperature=0)
    )
 
    # Convert history and start chat
    gemini_history = _to_gemini_history(session_history)
    chat = model.start_chat(history=gemini_history)
 
    plots = []
    tool_calls_log = []
    called_tools = set()
 
    # Send initial user message
    current_message = message
    max_iterations = _agent_iteration_limit(message)
 
    for i in range(max_iterations):
        print(f"Agent iteration {i + 1}/{max_iterations}")
 
        response = chat.send_message(current_message)
        candidate = response.candidates[0]
        parts = candidate.content.parts
 
        # Check for text-only final answer
        tool_call_parts = [p for p in parts if hasattr(p, "function_call") and p.function_call.name]
        text_parts = [p for p in parts if hasattr(p, "text") and p.text]
 
        if not tool_call_parts:
            reply = " ".join(p.text for p in text_parts).strip()
            return {
                "reply": reply or "Analysis complete.",
                "plots": plots,
                "tool_calls": tool_calls_log
            }
 
        # Deduplication check
        new_tools = [p.function_call.name for p in tool_call_parts]
        if all(t in called_tools for t in new_tools):
            reply = " ".join(p.text for p in text_parts).strip()
            return {
                "reply": reply or "Analysis complete.",
                "plots": plots,
                "tool_calls": tool_calls_log
            }
 
        called_tools.update(new_tools)
 
        # ── execute tools and build response parts ─────────────────────
        function_responses = []
        executed_tools = []

        for part in tool_call_parts:
            fc = part.function_call
            name = fc.name
            args = dict(fc.args) if fc.args else {}
 
            print(f"Calling tool: {name}")
 
            if name not in tool_map:
                result = {"error": f"Unknown tool: {name}"}
            else:
                try:
                    result = tool_map[name](args)
 
                    if isinstance(result, str) and result.endswith(".png"):
                        plots.append({
                            "url": f"/plots/{os.path.basename(result)}",
                            "caption": name
                        })
                    elif isinstance(result, dict) and "plot_path" in result:
                        plots.append({
                            "url": f"/plots/{os.path.basename(result['plot_path'])}",
                            "caption": name
                        })
 
                except Exception as e:
                    result = {"error": str(e)}
                    print(f"Tool error in {name}: {e}")

            executed_tools.append({
                "name": name,
                "args": args,
                "result": result,
            })

            tool_calls_log.append({
                "name": name,
                "args": args,
                "result_summary": str(result)[:300]
            })
 
            function_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=name,
                        response={"result": json.loads(json.dumps(result, default=str))}
                    )
                )
            )

        if executed_tools and all(item["name"] in DIRECT_SUMMARY_TOOLS for item in executed_tools):
            reply = "\n\n".join(
                _format_direct_tool_summary(item["name"], item["args"], item["result"])
                for item in executed_tools
            )
            return {
                "reply": reply,
                "plots": plots,
                "tool_calls": tool_calls_log
            }

        # Send all tool results back in one message
        current_message = function_responses
 
    return {
        "reply": (
            "I could not complete the request because the agent did not produce a final answer "
            "within the available tool iterations. Try making the request more explicit, for example: "
            "'Run DESeq2 for mesangial cell, 24m vs 3m.'"
        ),
        "plots": plots,
        "tool_calls": tool_calls_log
    }
 
