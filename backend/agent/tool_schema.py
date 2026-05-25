from google.generativeai.types import FunctionDeclaration, Tool

TOOLS = Tool(function_declarations=[

    FunctionDeclaration(
        name="generate_umap",
        description="Generate 2D UMAP visualization of cell clusters.",
        parameters={
            "type": "object",
            "properties": {}
        }
    ),

    FunctionDeclaration(
        name="find_senescence_markers",
        description=(
            "Checks which SenMayo senescence genes are present in the dataset. "
            "This is a descriptive gene-set overlap analysis and NOT a measure of biological aging severity."
        ),
        parameters={
            "type": "object",
            "properties": {}
        }
    ),

    FunctionDeclaration(
        name="senescence_score",
        description=(
            "Scores each cell using the SenMayo 125-gene signature. "
            "IMPORTANT: This is a per-cell metric and should only be compared within the same cell type. "
            "Do NOT interpret global differences across mixed cell populations as biological aging hierarchy."
        ),
        parameters={
            "type": "object",
            "properties": {}
        }
    ),

    FunctionDeclaration(
        name="get_cluster_annotations",
        description=(
            "Returns mapping of clusters to most common cell types. "
            "Used for identifying cell type composition of clusters."
        ),
        parameters={
            "type": "object",
            "properties": {}
        }
    ),

    FunctionDeclaration(
        name="run_deseq2",
        description=(
            "Performs gene-level differential expression analysis using pseudobulk + DESeq2. "
            "Requires a specific cell type. Compares age groups using sample-level aggregation. "
            "Returns log2 fold changes, adjusted p-values, and ranked gene list."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cell_type": {
                    "type": "string",
                    "description": "Cell type to analyze (e.g., macrophage, T cell)"
                },
                "sample_column": {
                    "type": "string",
                    "description": "Sample ID column (default: sample_id)"
                },
                "age_column": {
                    "type": "string",
                    "description": "Age column (default: age)"
                },
                "reference_age": {
                    "type": "string",
                    "description": "Reference/control age group for the contrast, e.g. '3m'. If omitted, the youngest age is used."
                },
                "comparison_age": {
                    "type": "string",
                    "description": "Comparison age group for the contrast, e.g. '18m' or '24m'. Positive log2 fold change means higher expression in this group. If omitted, the oldest age is used."
                }
            },
            "required": ["cell_type"]
        }
    ),

    FunctionDeclaration(
        name="test_senescence_difference",
        description=(
            "Statistical test for SenMayo score change between two age groups in one cell type. "
            "Uses Mann-Whitney U on per-sample (mouse/donor) median scores — NOT per cell. "
            "Use when the user asks for p-value, significance, or statistical evidence of "
            "senescence score differences. Requires sample_id (or mouse.id / mouse_id)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cell_type": {
                    "type": "string",
                    "description": "Cell type to test (e.g. 'T cell', 'macrophage')",
                },
                "reference_age": {
                    "type": "string",
                    "description": "Reference/younger age group, e.g. '3m'",
                },
                "comparison_age": {
                    "type": "string",
                    "description": "Comparison/older age group, e.g. '24m'",
                },
                "age_column": {
                    "type": "string",
                    "description": "Age column name (default: age)",
                },
                "sample_column": {
                    "type": "string",
                    "description": "Sample/donor column (default: sample_id)",
                },
            },
            "required": ["cell_type"],
        },
    ),

    FunctionDeclaration(
        name="compare_across_age",
        description=(
            "Analyzes senescence across age groups with cell-type stratification. "
            "Set cell_type when the user asks for one cell type only (e.g. macrophage, T cell). "
            "IMPORTANT: Global averages across all cells are NOT biologically valid for ranking aging. "
            "Only cell-type-specific trends should be used for biological interpretation."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cell_type": {
                    "type": "string",
                    "description": (
                        "Optional. Restrict analysis and plots to this cell type "
                        "(e.g. 'macrophage', 'T cell'). Omit to summarize all cell types."
                    ),
                },
                "age_column": {
                    "type": "string",
                    "description": "Column name for age in dataset, usually 'age'"
                },
                "cell_type_column": {
                    "type": "string",
                    "description": "Column name for cell type, usually 'cell_ontology_class'"
                },
                "reference_age": {
                    "type": "string",
                    "description": "Reference (younger) age group, e.g. '3m'. Use for young vs old comparisons."
                },
                "comparison_age": {
                    "type": "string",
                    "description": "Comparison (older) age group, e.g. '24m'. Use for young vs old comparisons."
                }
            }
        }
    ),

])
