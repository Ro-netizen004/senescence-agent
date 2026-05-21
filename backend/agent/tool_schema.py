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
        name="compare_across_age",
        description=(
            "Analyzes senescence across age groups with cell-type stratification. "
            "IMPORTANT: Global averages across all cells are NOT biologically valid for ranking aging. "
            "Only cell-type-specific trends should be used for biological interpretation."
        ),
        parameters={
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
            }
        }
    ),

])