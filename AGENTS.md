# AGENTS.md

Conventions for AI agents and humans working in `hydrospectral-lab`. Keep this file and [`README.md`](README.md) lean: durable scientific background lives in [`docs/aquatic-hyperspectral-handoff-2026-11-25.md`](docs/aquatic-hyperspectral-handoff-2026-11-25.md), and experiment-specific details belong in each experiment's own protocol or manifest rather than duplicated here.

## What this repo is

An open research and educational workspace on aquatic hyperspectral remote sensing, Earth observation, environmental foundation models, and microbial ecology. Default to **CPU-first, reproducible Python scripts and notebooks**; allocate GPUs only when justified for foundation-model inference or training.

## Layout (one home per artifact)

- `docs/` — foundational research handoffs, synthesis notes, and [`docs/references-access.md`](docs/references-access.md) (source reading depth and access barriers). Never create overlapping summary reports.
- `pre-registrations/` — dated confirmatory experiment protocols committed *before* execution, with append-only deviation sections.
- `notebooks/` — reproducible educational (`Q01`–`Q13`) and exploratory notebooks.
- `src/` — reusable Python helpers extracted only after proving useful across at least two experiments.
- `results/` — compact retained benchmark outputs, figures, and byte-deterministic `manifest.json` provenance records.
- `tests/` — fast checks that guard durable contracts (radiometry, QC thresholds, `GLORIA_ID` joins, group splitters, manifest schemas, and planted defects).
- `data/` — [`data/README.md`](data/README.md) checksum inventory; raw archives and granules live locally in gitignored `data/raw/`.
- `LICENSE` & `LICENSE-DOCS.md` — MIT for code/scripts (`LICENSE`) and CC BY 4.0 for documentation, notes, and original figures (`LICENSE-DOCS.md`).

## Rules

1. **Epistemic and status hygiene.**
   - Keep **proposed work**, **provenance-incomplete** legacy runs, **exploratory** runs (author-only or post-hoc), and **reproduced** results (independently rerun from recorded inputs by someone other than the author) strictly distinct. Never label an unverified output "verified" or "confirmed".
   - Separate physical **observation**, bio-optical **retrieval**, model **reconstruction**, and ecological **prediction**. Satellite-derived products (e.g., PACE chlorophyll, IOPs, MOANA) are model estimates, never independent field ground truth.
   - Preserve historical experiment ID namespaces (`Q01`–`Q13`, `HS-R01`–`HS-R08`, `GL-R00`–`GL-R15`, `OPT-01`–`OPT-25`, `EA-R01`–`EA-R12`, `EA-01`–`EA-11`); do not silently renumber.

2. **Radiometric, sensor, and ecological invariants.**
   - Join GLORIA tables strictly on `GLORIA_ID`, never row position. Keep corrected `Chla` separate from uncorrected chlorophyll + phaeopigments, and isolate optically inferred targets (e.g., Lake Geneva Thetis line-height Chla) to avoid target circularity.
   - Preserve negative $R_{rs}$ values for baseline-shift and QC diagnostics rather than silently clipping to zero. Distinguish missing QC flags (unmeasured wavelengths) from passed tests.
   - Convolve spectra with official sensor spectral response functions (SRFs) when claiming sensor simulation; 1 nm interpolation in GLORIA is not 1 nm native spectrometer resolution.
   - Respect foundation-model input domains (e.g., do not feed 339–719 nm PACE OCI cubes directly into Sentinel-3 OLCI + SLSTR checkpoints).
   - Handle 16S/18S and metagenomic data compositionally; distinguish copy counts, relative abundance, absolute abundance, diversity, and optical cross-section.

3. **Validation, pre-registration, and checks that can fail.**
   - Fix target, QC cohort, grouping keys, and metrics before model selection; never select a cohort on model performance. Disclose any already-seen exploratory results in new protocols (rerunning deterministic code after seeing results is not a blind test).
   - Evaluate site-held-out, study/dataset-held-out (`Dataset_ID`), and temporal splits alongside random splits; guard against temporal leakage when pairing historical samples with annual embeddings (e.g., AlphaEarth).
   - Benchmark complex or pretrained models against interpretable physical/statistical baselines (2-band ratios, AVW, pyOWT/Spyrakos OWTs, PCA, and location/season `M0`), reporting applicability domain / OOD distance and `attempted`, `completed`, `failed`, and `excluded` counts with explicit denominators.
   - Guard core calculations and splitters in `tests/` using hand-worked cases (never copying the formula under test), boundary values just below and just above thresholds, and planted defects that prove the check can fail.

4. **Commit only what the repo needs (scratch stays outside).**
   - Run one-off sweeps, throwaway scripts, ad-hoc plots, logs, and bulk downloads **outside the repository** in a temp/scratch directory; summarize task-local reasoning in the PR description.
   - Never commit raw archives or large binaries (`.zip`, `.nc`, `.h5`, `.tif`, `.zarr`, checkpoints), third-party publisher PDFs, or credentials (`.env`, `.netrc`, Earth Engine / GCP keys).
   - Keep line endings LF (`.gitattributes`), check diff size before committing, and run `git diff --check` after merges to catch conflict markers. On Windows (`cp949` console), set `PYTHONIOENCODING=utf-8` when running Python scripts.

5. **Branch and review workflow.**
   - Default branch is `main`. Use a feature branch and PR for non-trivial changes (experiments, code, protocols, literature claims, or repo policy).
   - Before merging non-trivial changes, obtain an independent review from someone other than the author (a person, or a fresh review agent given the diff, claims, and files without the author's reasoning). Treat fixes as "addressed, awaiting review" until confirmed. Push directly to `main` only for trivial fixes (typos, broken links).

## Agent guidance

Load [experiment-review](.claude/skills/experiment-review/SKILL.md) as the primary workflow guide when writing or reviewing experiments, benchmarks, notebooks, or retained result packages. Load the evidence checklist alongside it whenever literature or scientific claims are involved:

| Task | Guide / Checklist |
| --- | --- |
| Designing, running, packaging, or reviewing computational experiments and code | [experiment-review](.claude/skills/experiment-review/SKILL.md) |
| Auditing remote-sensing, bio-optical, Earth-AI, or microbial-ecology literature and claims | [scientific-evidence-audit](.claude/skills/scientific-evidence-audit/SKILL.md) |
