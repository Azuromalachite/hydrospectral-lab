# Notebooks

Reproducible Jupyter notebooks for the educational curriculum (`Q01`–`Q13`) and targeted exploratory analyses. Do not add empty placeholder notebooks (`docs/decisions.md` D-005).

## Conventions

- **Naming:** Prefix curriculum notebooks with their identifier from [`docs/aquatic-hyperspectral-handoff-2026-11-25.md`](../docs/aquatic-hyperspectral-handoff-2026-11-25.md) (for example, `Q01_water_colour_and_owts.ipynb`, `Q02_alphaearth_landscape_clustering.ipynb`).
- **Compute & encoding:** Default to CPU-friendly execution (`NumPy`, `scipy`, `pandas`, `h5py`, `matplotlib`, `scikit-learn`) unless GPU inference is explicitly required, and pass explicit `encoding="utf-8"` on all text file reads/writes (`tools/check_declared_encoding.py` inspects `.ipynb` code cells as well as `.py` files).
- **Data paths:** Resolve external datasets via gitignored `config/local_paths.yaml` (copied from [`config/local_paths.example.yaml`](../config/local_paths.example.yaml)) and verify SHA-256 digests against [`manifests/sources/`](../manifests/README.md) rather than hardcoding workstation or Colab-specific paths.
- **Rigor:** State the question, cohort filters, validation split strategy, baseline comparison, and key limitations explicitly inside each notebook.
