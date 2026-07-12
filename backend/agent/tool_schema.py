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
            "Returns the cell type of each Leiden cluster. Uses the dataset's own "
            "annotations when present; otherwise PREDICTS the cell type of each "
            "cluster from its marker genes (deterministic, descriptive-only). "
            "Use this whenever the user asks to name, label, annotate, or identify "
            "the cell types of clusters, or asks why the UMAP shows unlabeled clusters."
        ),
        parameters={
            "type": "object",
            "properties": {}
        }
    ),

    FunctionDeclaration(
        name="run_deseq2",
        description=(
            "Performs gene-level differential expression using pseudobulk + DESeq2 for one "
            "cell type, between two groups of a grouping variable (age, condition, treatment, "
            "genotype, ...) via sample-level aggregation. Provide reference_group and "
            "comparison_group naming exact values that exist in the dataset. For an aging "
            "dataset the grouping variable is 'age' and the groups can be omitted to default "
            "to youngest vs oldest. Returns log2 fold changes, adjusted p-values, ranked genes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cell_type": {
                    "type": "string",
                    "description": "Cell type to analyze (e.g., macrophage, hepatocyte)"
                },
                "group_column": {
                    "type": "string",
                    "description": "Grouping variable column to compare on (e.g. 'condition', 'treatment', 'age'). Defaults to the dataset's primary grouping column."
                },
                "reference_group": {
                    "type": "string",
                    "description": "Reference/control group value (e.g. 'CTRL', '3m'). Must exist in group_column. If omitted for an age contrast, the youngest age is used."
                },
                "comparison_group": {
                    "type": "string",
                    "description": "Comparison group value (e.g. 'ETO', '24m'). Positive log2 fold change means higher expression in this group. If omitted for an age contrast, the oldest age is used."
                },
                "sample_column": {
                    "type": "string",
                    "description": "Sample ID column (default: sample_id)"
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
