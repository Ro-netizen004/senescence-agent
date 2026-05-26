import os
import json
import scanpy as sc
import google.generativeai as genai
 
from dotenv import load_dotenv
 
from tools.visualization import generate_umap
from tools.senescence import find_senescence_markers, senescence_score, get_cluster_annotations
from tools.age_analysis import compare_across_age
from tools.statistics import test_senescence_difference
from tools.run_deseq2 import run_deseq2_pseudobulk
from agent.cache import get_adata, cache_adata
from agent.pipeline import ensure_pipeline
from agent.tool_schema import TOOLS
from agent.tool_router import build_tool_map
from agent.system_prompt import SYSTEM_PROMPT
from dataset_paths import resolve_dataset_path
from tools.dataset_info import build_dataset_summary, format_dataset_context
from agent.inference_state import apply_inference_state
from agent.output_renderer import render_tool_calls_with_schema
from agent.scientific_validation import wrap_result_for_llm
 
 
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))
 
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

DEFAULT_AGENT_ITERATIONS = int(os.getenv("DEFAULT_AGENT_ITERATIONS", "3"))
FULL_PIPELINE_AGENT_ITERATIONS = int(os.getenv("FULL_PIPELINE_AGENT_ITERATIONS", "5"))


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

    multi_step_phrases = (" then ", " and then ", " also ", "after that", "first ", "second ")
    if any(p in text for p in multi_step_phrases) or text.count(",") >= 2:
        return max(DEFAULT_AGENT_ITERATIONS, FULL_PIPELINE_AGENT_ITERATIONS - 1)

    return DEFAULT_AGENT_ITERATIONS


def _wants_multi_step(message: str) -> bool:
    text = f" {message.lower()} "
    if _wants_analysis_panel(message):
        return True
    if any(
        p in text
        for p in (" then ", " and then ", " also ", "after that", "first ", "second ")
    ):
        return True
    return message.count(",") >= 2


def _wants_analysis_panel(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in (
            "run everything",
            "run all",
            "run the full",
            "full analysis",
            "analyze everything",
            "complete analysis",
            "comprehensive analysis",
            "end-to-end",
            "what's interesting",
            "whats interesting",
            "what is interesting",
            "tell me what's interesting",
        )
    )


def _needs_pvalue_clarification(message: str) -> bool:
    text = message.lower()
    return any(
        w in text
        for w in (
            "p-value",
            "p value",
            "pvalue",
            "p-values",
            "statistical significance",
            "significant difference",
            "exact p",
        )
    )


def _plot_basename(path) -> str:
    if not path:
        return ""
    return os.path.basename(str(path))


def _execute_tool(
    tool_map: dict,
    name: str,
    args: dict,
    user_message: str = "",
) -> dict:
    """Run tool and attach scientific_validation before any formatting or LLM handoff."""
    if name not in tool_map:
        return {"error": f"Unknown tool: {name}"}
    try:
        result = tool_map[name](args)
    except Exception as e:
        result = {"error": str(e)}
        print(f"Tool error in {name}: {e}")
    if isinstance(result, dict):
        result = apply_inference_state(name, result, args)
    return result


def _deterministic_reply(tool_calls_log: list) -> str:
    """Final user text from tool facts only — no LLM narration."""
    reply, _ = render_tool_calls_with_schema(tool_calls_log)
    return reply


def _panel_highlights(tool_calls_log: list) -> str:
    lines = []
    for entry in tool_calls_log:
        name = entry.get("name")
        result = entry.get("result")
        if not isinstance(result, dict) or result.get("error"):
            continue
        inf = result.get("inference_state") or {}
        if inf.get("state") in ("DESCRIPTIVE_ONLY", "LOW_POWER") and name == "compare_across_age":
            lines.append(
                "- Age comparison: descriptive medians only (no statistical conclusion)."
            )
            continue
        if name == "find_senescence_markers":
            lines.append(
                f"- SenMayo coverage: {result.get('coverage_pct', 'NA')}% "
                f"({len(result.get('found_markers', []))} genes detected)."
            )
        elif name == "senescence_score":
            lines.append(
                f"- Highest-scoring cluster (descriptive): {result.get('top_senescent_cluster')} "
                f"({result.get('top_senescent_cell_type')})."
            )
        elif name == "compare_across_age":
            top_by_type = result.get("most_senescent_per_celltype") or {}
            if top_by_type:
                preview = list(top_by_type.items())[:3]
                for ct, info in preview:
                    lines.append(
                        f"- {ct}: highest median score at age {info.get('age')} "
                        f"({_fmt(info.get('score'))}) — descriptive, not tested."
                    )
    return "\n".join(lines) if lines else "- See detailed sections above."


def run_analysis_panel(tool_map: dict, message: str = "") -> dict:
    """Run standard senescence panel without relying on multi-turn LLM tool chaining."""
    panel_steps = [
        ("find_senescence_markers", {}),
        ("senescence_score", {}),
        ("generate_umap", {}),
        ("get_cluster_annotations", {}),
        ("compare_across_age", {}),
    ]

    plots = []
    tool_calls_log = []
    sections = []

    for name, args in panel_steps:
        if name not in tool_map:
            continue
        result = _execute_tool(tool_map, name, args, message)

        for plot_entry in _collect_plots_from_result(result, name):
            if not any(p["url"] == plot_entry["url"] for p in plots):
                plots.append(plot_entry)

        serializable_result = json.loads(json.dumps(result, default=str))
        tool_calls_log.append({
            "name": name,
            "args": args,
            "result": serializable_result,
        })
    reply = _deterministic_reply(tool_calls_log)
    header = "Standard senescence analysis panel completed.\n\n"
    highlights = _panel_highlights(tool_calls_log)
    reply = f"{header}{reply}\n\n---\n\nPanel summary:\n{highlights}"

    if _needs_pvalue_clarification(message):
        reply += (
            "\n\n[System] Score p-values require test_senescence_difference; "
            "gene padj requires run_deseq2."
        )

    return {"reply": reply, "plots": plots, "tool_calls": tool_calls_log}


def _collect_plots_from_result(result, tool_name: str) -> list:
    plots = []
    if isinstance(result, str) and result.endswith(".png"):
        plots.append({
            "url": f"/plots/{os.path.basename(result)}",
            "caption": tool_name,
        })
        return plots

    if not isinstance(result, dict):
        return plots

    if result.get("plot_path"):
        plots.append({
            "url": f"/plots/{os.path.basename(result['plot_path'])}",
            "caption": tool_name,
        })

    for key, label in (
        ("age_distribution_plot", "age_distribution"),
        ("senescence_violin_plot", "senescence_violin"),
    ):
        path = result.get(key)
        if path:
            plots.append({
                "url": f"/plots/{os.path.basename(path)}",
                "caption": label,
            })

    return plots


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
        file_path = resolve_dataset_path(file_id)

        if not file_path:
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
            "test_senescence_difference": test_senescence_difference,
            "run_deseq2": run_deseq2_pseudobulk,
        }
    )

    if _wants_analysis_panel(message):
        return run_analysis_panel(tool_map, message)

    system_instruction = SYSTEM_PROMPT
    if not session_history:
        summary = build_dataset_summary(adata, species)
        adata.uns["dataset_summary"] = summary
        system_instruction = (
            f"{SYSTEM_PROMPT}\n\n{format_dataset_context(summary)}"
        )

    # ── Gemini client ─────────────────────────────────────────────────
    model = genai.GenerativeModel(
        model_name=MODEL,
        tools=TOOLS,
        system_instruction=system_instruction,
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
            if tool_calls_log:
                return {
                    "reply": _deterministic_reply(tool_calls_log),
                    "plots": plots,
                    "tool_calls": tool_calls_log,
                }
            return {
                "reply": (
                    "Quantitative results are produced only by analysis tools. "
                    "Ask for a specific tool action (e.g. test_senescence_difference for T cell, 3m vs 24m)."
                ),
                "plots": plots,
                "tool_calls": tool_calls_log,
            }

        # Deduplication check
        new_tools = [p.function_call.name for p in tool_call_parts]
        if all(t in called_tools for t in new_tools):
            if tool_calls_log:
                return {
                    "reply": _deterministic_reply(tool_calls_log),
                    "plots": plots,
                    "tool_calls": tool_calls_log,
                }
            return {
                "reply": "Analysis step already completed for this request.",
                "plots": plots,
                "tool_calls": tool_calls_log,
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
 
            result = _execute_tool(tool_map, name, args, message)
            for plot_entry in _collect_plots_from_result(result, name):
                if not any(p["url"] == plot_entry["url"] for p in plots):
                    plots.append(plot_entry)

            executed_tools.append({
                "name": name,
                "args": args,
                "result": result,
            })

            serializable_result = json.loads(json.dumps(result, default=str))
            tool_calls_log.append({
                "name": name,
                "args": args,
                "result": serializable_result,
            })
 
            llm_payload = wrap_result_for_llm(name, result, args)
            function_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=name,
                        response=json.loads(json.dumps(llm_payload, default=str)),
                    )
                )
            )

        # Deterministic renderer — never LLM prose for tool results
        if not _wants_multi_step(message):
            reply = _deterministic_reply(tool_calls_log)
            if _needs_pvalue_clarification(message) and any(
                e["name"] == "compare_across_age" for e in tool_calls_log
            ) and not any(
                e["name"] == "test_senescence_difference" for e in tool_calls_log
            ):
                reply += (
                    "\n\n---\n\n[System] compare_across_age has no p-value. "
                    "Use test_senescence_difference (score) or run_deseq2 (genes)."
                )
            return {
                "reply": reply,
                "plots": plots,
                "tool_calls": tool_calls_log,
            }

        current_message = function_responses

    if tool_calls_log:
        return {
            "reply": _deterministic_reply(tool_calls_log),
            "plots": plots,
            "tool_calls": tool_calls_log,
        }

    return {
        "reply": (
            "No analysis tools completed. Try an explicit request, e.g. "
            "'test_senescence_difference for T cell, 3m vs 24m'."
        ),
        "plots": plots,
        "tool_calls": tool_calls_log,
    }
 
