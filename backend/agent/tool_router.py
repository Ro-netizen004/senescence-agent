def build_tool_map(adata, species, tools):
    return {
        "generate_umap": lambda args: tools["generate_umap"](adata),
        "find_senescence_markers": lambda args: tools["find_senescence_markers"](adata, species),
        "senescence_score": lambda args: tools["senescence_score"](adata, species),
        "get_cluster_annotations": lambda args: tools["get_cluster_annotations"](adata),
        "compare_across_age": lambda args: tools["compare_across_age"](
            adata,
            args.get("age_column", "age"),
            args.get("cell_type_column", "cell_ontology_class"),
            species
        )
    }