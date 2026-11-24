# Notebooks

Reproducible Jupyter notebooks for the educational curriculum (`Q01`–`Q13`) and targeted exploratory analyses.

## Conventions

- **Naming:** Prefix curriculum notebooks with their identifier from [docs/aquatic-hyperspectral-handoff-2026-11-25.md](../docs/aquatic-hyperspectral-handoff-2026-11-25.md) (for example, `Q01_water_colour_and_owts.ipynb`, `Q02_alphaearth_landscape_clustering.ipynb`).
- **Compute:** Default to CPU-friendly execution (`NumPy`, `scipy`, `pandas`, `h5py`, `matplotlib`, `scikit-learn`) unless GPU inference is explicitly required.
- **Data paths:** Read upstream inputs from `../data/raw/` rather than hardcoding machine-specific or Colab-only paths; verify input filenames and SHA-256 hashes at the top of each notebook.
- **Rigor:** State the question, cohort filters, validation split strategy, baseline comparison, and key limitations explicitly inside each notebook.
