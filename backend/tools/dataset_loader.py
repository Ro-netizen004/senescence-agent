import os
import json
import scanpy as sc

from tools.config import BASE_DIR

def load_kidney_dataset():

    path = os.path.join(
        BASE_DIR,
        "data",
        "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"
    )

    print(f"Loading dataset from: {path}")

    return sc.read_h5ad(path)


def load_senmayo_genes():

    path = os.path.join(
        BASE_DIR,
        "data",
        "senmayo.json"
    )

    with open(path, "r") as f:
        data = json.load(f)

    return data["SAUL_SEN_MAYO"]["geneSymbols"]