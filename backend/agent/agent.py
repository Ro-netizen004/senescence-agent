import os
import json
import time
import tempfile
import scanpy as sc

from groq import Groq
from dotenv import load_dotenv

from tools.preprocessing import quality_control, normalize
from tools.clustering import cluster_cells
from tools.visualization import generate_umap
from tools.senescence import find_senescence_markers, senescence_score
from tools.age_analysis import compare_across_age

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

MODEL  = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── In-memory dataset cache ────────────────────────────────────────────────
# Keeps adata alive between chat turns so pipeline state persists.
# Structure: { file_id: { "adata": adata, "timestamp": float } }
_adata_cache: dict = {}
CACHE_TTL_SECONDS = 3600  # evict datasets unused for 1 hour

def _cache_adata(file_id: str, adata) -> None:
    """
    Store adata in memory cache.
    Evicts expired entries first, then oldest if still at limit of 3.
    """
    now = time.time()

    # Evict expired
    expired = [
        k for k, v in _adata_cache.items()
        if now - v["timestamp"] > CACHE_TTL_SECONDS
    ]
    for k in expired:
        del _adata_cache[k]
        print(f"Evicted expired dataset: {k}")

    # Evict oldest if at limit
    if len(_adata_cache) >= 3:
        oldest = min(_adata_cache, key=lambda k: _adata_cache[k]["timestamp"])
        del _adata_cache[oldest]
        print(f"Evicted oldest dataset: {oldest}")

    _adata_cache[file_id] = {
        "adata": adata,
        "timestamp": time.time()
    }

def _get_adata(file_id: str):
    """
    Retrieve adata from cache.
    Returns None if missing or expired.
    Refreshes timestamp on access.
    """
    entry = _adata_cache.get(file_id)

    if not entry:
        return None

    if time.time() - entry["timestamp"] > CACHE_TTL_SECONDS:
        del _adata_cache[file_id]
        print(f"Cache expired for dataset: {file_id}")
        return None

    # Refresh timestamp on access
    entry["timestamp"] = time.time()
    return entry["adata"]


# ── Deterministic pipeline ─────────────────────────────────────────────────
# QC → normalize → cluster runs exactly once per dataset.
# State stored in adata.uns so it survives cache retrieval.
# LLM never controls this — code does.

def ensure_pipeline(adata, species: str) -> None:
    """
    Guarantee preprocessing runs in correct order exactly once.
    Called automatically before any LLM tool execution.

    Uses adata.uns["pipeline_state"] for safe persistence —
    this survives cache lookups unlike Python object attributes.
    """
    state = adata.uns.get("pipeline_state", {})

    if not state.get("qc"):
        print("Auto-running: quality_control")
        quality_control(adata, species)
        state["qc"] = True

    if not state.get("norm"):
        print("Auto-running: normalize")
        normalize(adata)
        state["norm"] = True

    if not state.get("cluster"):
        print("Auto-running: cluster_cells")
        cluster_cells(adata)
        state["cluster"] = True

    adata.uns["pipeline_state"] = state


# ── System prompt ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a bioinformatics assistant specializing in aging and senescence analysis.

Preprocessing (QC, normalization, clustering) is already complete.
Do NOT call quality_control, normalize, or cluster_cells.

Use tools ONLY for analysis:
- generate_umap: visualize cell structure
- find_senescence_markers: check which senescence genes are present
- senescence_score: score cells using SenMayo 125-gene signature
- compare_across_age: compare cell populations across age groups

Rules:
- Never answer biology questions from memory
- Always use tools for biological conclusions
- Explain results in plain English without jargon
- Name the cell type, not just the cluster number
- Call one tool per response unless the user explicitly asks for multiple things
"""


# ── Tool schemas (analysis only — preprocessing removed) ──────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_umap",
            "description": "Generate 2D UMAP visualization of cell clusters.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_senescence_markers",
            "description": "Check which SenMayo senescence genes are present in the dataset.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "senescence_score",
            "description": "Score each cell against the SenMayo 125-gene signature. Use when user asks about senescent cells or aging.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_across_age",
            "description": "Compare cell type composition and senescence scores across age groups.",
            "parameters": {
                "type": "object",
                "properties": {
                    "age_column": {
                        "type": "string",
                        "description": "Column name for age in dataset, usually 'age'"
                    },
                    "cell_type_column": {
                        "type": "string",
                        "description": "Column name for cell type, usually 'cell_ontology_class'"
                    }
                },
                "required": []
            }
        }
    }
]


# ── Main agent ─────────────────────────────────────────────────────────────
def run_agent(
    session_history: list,
    message: str,
    file_id: str,
    species: str
) -> dict:
    """
    Run the senescence analysis agent.

    Architecture:
    - Layer 1 (deterministic): ensure_pipeline() runs QC/norm/cluster once
    - Layer 2 (LLM): analysis tools only — umap, markers, scoring, age comparison

    Species always comes from the caller — LLM never decides species.
    adata is cached in memory so pipeline state persists across chat turns.
    """

    # Load from cache or disk
    adata = _get_adata(file_id)

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
        _cache_adata(file_id, adata)

    # Layer 1 — deterministic preprocessing
    # Runs QC → normalize → cluster exactly once, code-enforced
    ensure_pipeline(adata, species)

    # Layer 2 — LLM analysis tools only
    # Species always injected here — LLM never controls it
    tool_map = {
        "generate_umap":           lambda args: generate_umap(adata),
        "find_senescence_markers": lambda args: find_senescence_markers(adata, species),
        "senescence_score":        lambda args: senescence_score(adata, species),
        "compare_across_age":      lambda args: compare_across_age(
            adata,
            args.get("age_column", "age"),
            args.get("cell_type_column", "cell_ontology_class")
        )
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *session_history,
        {"role": "user", "content": message}
    ]

    plots          = []
    tool_calls_log = []
    called_tools   = set()  # track called tools to detect redundant loops

    for i in range(4):

        print(f"Agent iteration {i + 1}")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=1024
        )

        msg = response.choices[0].message

        # LLM gave a final text answer — done
        if not msg.tool_calls:
            return {
                "reply": msg.content,
                "plots": plots,
                "tool_calls": tool_calls_log
            }

        # Detect redundant loop — stop if LLM only requests already-called tools
        new_tools = [tc.function.name for tc in msg.tool_calls]
        if all(t in called_tools for t in new_tools):
            print("LLM requested only already-called tools — stopping loop")
            return {
                "reply": msg.content or "Analysis complete.",
                "plots": plots,
                "tool_calls": tool_calls_log
            }

        called_tools.update(new_tools)

        # Append assistant message with tool call list
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

        # Execute each tool call and collect plots
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

                    # Collect plot paths for frontend display
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

    # Hit iteration limit
    return {
        "reply": "Analysis complete.",
        "plots": plots,
        "tool_calls": tool_calls_log
    }