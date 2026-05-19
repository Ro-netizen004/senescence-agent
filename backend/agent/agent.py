import os
import json
import tempfile
import scanpy as sc
from groq import Groq
from dotenv import load_dotenv
from tools.scanpy_tools import (
    quality_control,
    normalize,
    cluster_cells,
    generate_umap,
    find_senescence_markers,
    senescence_score,
    compare_across_age
)

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """
You are a bioinformatics assistant specializing in 
aging and cell senescence analysis.

MANDATORY: You MUST ALWAYS call these three tools 
first, in this exact order, before anything else:
1. quality_control
2. normalize
3. cluster_cells

You CANNOT call senescence_score, generate_umap, 
find_senescence_markers, or compare_across_age 
until all three have been called first.
No exceptions. Even if the user only asks about 
senescence, run all three first.

After the first three, call additional tools based 
on the user request:
- generate_umap: if user wants to see cells
- find_senescence_markers: if user asks about senescence genes
- senescence_score: if user asks about senescent cells
- compare_across_age: if user asks about age differences

Rules:
- NEVER answer biology questions from memory
- ALWAYS use tools to get real results
- Explain results in plain English without jargon
- Name the cell type, not just the cluster number
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "quality_control",
            "description": "Remove low quality cells and genes. ALWAYS call this first before any other tool.",
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
            "name": "normalize",
            "description": "Normalize and log transform cell counts. Call after quality_control.",
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
            "name": "cluster_cells",
            "description": "Group similar cells into clusters. Call after normalize.",
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
            "description": "Check which SenMayo senescence genes are present in dataset.",
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
            "description": "Score each cell against SenMayo 125-gene signature. Use when user asks about senescent cells or aging.",
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
            "description": "Summarize cell populations across age groups.",
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


def run_agent(session_history: list, message: str,
              file_id: str, species: str) -> dict:
    """
    Agent using Groq + llama-3.3-70b-versatile.
    Species is always taken from the user upload — never from LLM.
    """

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

    adata = sc.read_h5ad(file_path)

    # Species always comes from user upload parameter
    # Never trust the LLM to decide species
    tool_map = {
        "quality_control": lambda args: _run_qc(adata, species),
        "normalize": lambda args: _run_normalize(adata),
        "cluster_cells": lambda args: _run_cluster(adata),
        "generate_umap": lambda args: generate_umap(adata),
        "find_senescence_markers": lambda args: find_senescence_markers(adata, species),
        "senescence_score": lambda args: senescence_score(adata, species),
        "compare_across_age": lambda args: compare_across_age(
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

    plots = []
    tool_calls_log = []

    for i in range(8):

        print(f"Agent iteration {i+1}")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=1024
        )

        response_message = response.choices[0].message

        if not response_message.tool_calls:
            return {
                "reply": response_message.content,
                "plots": plots,
                "tool_calls": tool_calls_log
            }

        messages.append({
            "role": "assistant",
            "content": response_message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in response_message.tool_calls
            ]
        })

        for tool_call in response_message.tool_calls:
            name = tool_call.function.name

            try:
                args = json.loads(tool_call.function.arguments)
            except:
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
                    print(f"Tool error: {e}")

            tool_calls_log.append({
                "name": name,
                "args": args,
                "result_summary": str(result)[:300]
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            })

    return {
        "reply": "Analysis complete.",
        "plots": plots,
        "tool_calls": tool_calls_log
    }


# Helpers — handle adata mutation cleanly

def _run_qc(adata, species):
    result, _ = quality_control(adata, species)
    adata.obs = result.obs
    adata.var = result.var
    adata.X = result.X
    return {
        "status": "QC complete",
        "cells": adata.shape[0],
        "genes": adata.shape[1]
    }

def _run_normalize(adata):
    normalize(adata)
    return {"status": "Normalization complete"}

def _run_cluster(adata):
    cluster_cells(adata)
    return {
        "status": "Clustering complete",
        "clusters": int(adata.obs["leiden"].nunique())
    }