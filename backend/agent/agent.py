import os
import json
import tempfile
import scanpy as sc
import google.generativeai as genai
 
from dotenv import load_dotenv
 
from tools.visualization import generate_umap
from tools.senescence import find_senescence_markers, senescence_score, get_cluster_annotations
from tools.age_analysis import compare_across_age
 
from agent.cache import get_adata, cache_adata
from agent.pipeline import ensure_pipeline
from agent.tool_schema import TOOLS
from agent.tool_router import build_tool_map
from agent.system_prompt import SYSTEM_PROMPT
 
 
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))
 
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
 
 
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
 
    for i in range(4):
        print(f"Agent iteration {i + 1}")
 
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
 
        # Send all tool results back in one message
        current_message = function_responses
 
    return {
        "reply": "Analysis complete.",
        "plots": plots,
        "tool_calls": tool_calls_log
    }
 