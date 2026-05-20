import mygene

from tools.dataset_loader import load_senmayo_genes

DEFAULT_MG_CLIENT = mygene.MyGeneInfo()

DEFAULT_HUMAN_TO_MOUSE_FALLBACK = {
    "CDKN1A":   "Cdkn1a",
    "CDKN2A":   "Cdkn2a",
    "IL6":      "Il6",
    "IL8":      "Cxcl15",   # mouse proxy for human IL8
    "LMNB1":    "Lmnb1",
    "TP53":     "Trp53",    # critical: NOT Tp53
    "MKI67":    "Mki67",
    "SERPINE1": "Serpine1",
    "GLB1":     "Glb1",
    "HMGA1":    "Hmga1",
}

SENESCENCE_GENES = load_senmayo_genes()

# =========================
# Gene name normalization
# =========================

def normalize_gene_names(
    genes: list,
    species: str = "mouse",
    mg_client=None,
    fallback_dict=None
) -> list:
    """
    Convert human gene symbols to species orthologs.

    Uses MyGene API for accurate conversion.
    Falls back to custom mappings + capitalization rules.

    Dependency injection:
    - mg_client can be replaced with mock/test client
    - fallback_dict can be customized per dataset/species

    Examples:
        CDKN1A -> Cdkn1a
        TP53   -> Trp53
        IL6    -> Il6
    """

    # No conversion needed
    if species != "mouse":
        return genes

    # Inject defaults if none provided
    mg_client = mg_client or DEFAULT_MG_CLIENT
    fallback_dict = (
        fallback_dict
        or DEFAULT_HUMAN_TO_MOUSE_FALLBACK
    )

    converted = []

    try:

        result = mg_client.querymany(
            genes,
            scopes="symbol",
            fields="symbol",
            species="mouse",
            returnall=True
        )

        hits = result.get("out", [])

        for i, gene in enumerate(genes):

            # Successful API mapping
            if i < len(hits) and "symbol" in hits[i]:

                converted.append(hits[i]["symbol"])

            else:

                # Custom fallback mapping
                fallback = fallback_dict.get(gene)

                if fallback:

                    converted.append(fallback)

                # Generic capitalization fallback
                elif len(gene) > 1:

                    converted.append(
                        gene[0].upper() + gene[1:].lower()
                    )

                else:

                    converted.append(gene.upper())

    except Exception as e:

        print(f"MyGene lookup failed: {e}")
        print("Using fallback dictionary + capitalization.")

        for gene in genes:

            fallback = fallback_dict.get(gene)

            if fallback:

                converted.append(fallback)

            elif len(gene) > 1:

                converted.append(
                    gene[0].upper() + gene[1:].lower()
                )

            else:

                converted.append(gene.upper())

    return converted


# Run once at module load — cached for all function calls
# Avoids repeated API calls during demo
print("Converting SenMayo genes to mouse orthologs...")
SENESCENCE_GENES_MOUSE = normalize_gene_names(
    SENESCENCE_GENES,
    species="mouse"
)
print(f"Loaded {len(SENESCENCE_GENES_MOUSE)} SenMayo mouse genes.")