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