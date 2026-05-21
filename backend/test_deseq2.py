import os
import sys
import scanpy as sc

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agent.cache import get_adata, cache_adata
from agent.pipeline import ensure_pipeline
from tools.dataset_loader import load_kidney_dataset
from agent.tool_router import run_deseq2_wrapper

print("Loading dataset...")
adata = load_kidney_dataset()
print("Dataset loaded. Ensuring pipeline...")
ensure_pipeline(adata, "mouse")

print("Running deseq2 for macrophages...")
try:
    results = run_deseq2_wrapper(adata, cell_type="macrophage")
    print("Success! Results head:")
    print(results[:5])
except Exception as e:
    print("FAILED with exception:")
    import traceback
    traceback.print_exc()
