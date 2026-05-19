import shutil, tempfile

src = r"C:\Users\Tech moon\AppData\Local\GitHubDesktop\app-3.5.8\Desktop\senescence-agent\backend\data\tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"
dst = tempfile.gettempdir() + "\\test-kidney-001.h5ad"

shutil.copy(src, dst)
print("Done:", dst)