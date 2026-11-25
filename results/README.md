# Results & Retained Packages (`results/`)

Compact, version-controllable outputs from completed benchmarks and curriculum exercises (summary CSVs, figures, and provenance manifests). Large prediction arrays, intermediate features, and binary checkpoints stay out of Git (stage locally in `data/processed/` or attach to versioned GitHub Releases with SHA-256 checksums).

## Evidence statuses

Every result directory must state one of three statuses in its `README.md` and `manifest.json`:

- **`provenance-incomplete`** — historical or imported run missing one or more required provenance fields (exact commit, input SHA-256, environment versions, RNG pairing, or exclusion counts).
- **`exploratory`** — complete provenance recorded, or post-hoc/educational analysis, rerun only by its author.
- **`reproduced`** — rerun from the recorded inputs and manifest by someone other than the author (or an independent clean-room verification) matching within documented numerical tolerances.

## Deterministic `manifest.json` contract

Every retained package `manifest.json` follows these rules:

- **No wall-clock timestamps** inside `manifest.json` so deterministic reruns rewrite the file byte-for-byte; execution timing belongs in Git commit metadata or PR notes.
- **Repository-relative paths** from the repository root for all scripts, configs, inputs, and outputs.
- **Checksums & versions:** SHA-256 of every input archive/granule and analysis script, plus `CPython` version, OS platform, and exact library versions (`numpy`, `scipy`, `pandas`, `scikit-learn`, `h5py`, etc.).
- **Denominator accounting:** Explicit counts of `attempted`, `completed`, `failed`, and `excluded` observations (with exclusion reasons) per cohort/fold.
- **Units dictionary:** Explicit physical units (`sr^-1`, `ug/L`, `mg/L`, `m^-1`, `m`, `NTU`, or `log10` transformed) for every reported target and metric.
