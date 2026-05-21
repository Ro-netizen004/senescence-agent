import os
import json
import tempfile
import scanpy as sc

from groq import Groq
from dotenv import load_dotenv

from tools.visualization import generate_umap
from tools.age_analysis import compare_across_age
from tools.senescence import find_senescence_markers, senescence_score, get_cluster_annotations

from agent.cache import get_adata, cache_adata
from agent.pipeline import ensure_pipeline
from agent.tool_schema import TOOLS
from agent.tool_router import build_tool_map
from agent.system_prompt import SYSTEM_PROMPT


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def run_agent(
    session_history: list,
    message: str,
    file_id: str,
    species: str
) -> dict:

    adata = get_adata(file_id)

    if adata is None:
        file_path = os.path.join(
            tempfile.gettempdir(),
            f"{file_id}.h5ad"
        )

        if not os.path.exists(file_path):
            return {
                "reply": "Dataset not found. Please upload your file again.",
                "plots": [],
                "tool_calls": []
            }

        print(f"Loading dataset {file_id} into memory...")
        adata = sc.read_h5ad(file_path)
        cache_adata(file_id, adata)

    # ── pipeline (must happen AFTER loading) ─────────────────────────
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
            "compare_across_age": compare_across_age
        }
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *session_history,
        {"role": "user", "content": message}
    ]

    plots = []
    tool_calls_log = []
    called_tools = set()

    for i in range(4):

        print(f"Agent iteration {i + 1}")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature = 0,
            max_tokens=1024
        )

        msg = response.choices[0].message

        # final answer
        if not msg.tool_calls:
            return {
                "reply": msg.content,
                "plots": plots,
                "tool_calls": tool_calls_log
            }

        new_tools = [tc.function.name for tc in msg.tool_calls]

        if all(t in called_tools for t in new_tools):
            return {
                "reply": msg.content or "Analysis complete.",
                "plots": plots,
                "tool_calls": tool_calls_log
            }

        called_tools.update(new_tools)

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in msg.tool_calls
            ]
        })

        # ── tool execution ─────────────────────────────────────────────
        for tc in msg.tool_calls:

            name = tc.function.name

            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}

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

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str)
            })

    return {
        "reply": "Analysis complete.",
        "plots": plots,
        "tool_calls": tool_calls_log
    }