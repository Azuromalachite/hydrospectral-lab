# AGENTS.md

Conventions for AI agents and humans working in `hydrospectral-lab`. Keep this file and [`README.md`](README.md) lean: durable scientific background lives in [`docs/aquatic-hyperspectral-handoff-2026-11-25.md`](docs/aquatic-hyperspectral-handoff-2026-11-25.md), architectural rationale in [`docs/decisions.md`](docs/decisions.md), and experiment-specific details in each experiment's own protocol or manifest.

## What this repo is

An open research and educational workspace on aquatic hyperspectral remote sensing, Earth observation, environmental foundation models, and microbial ecology. Default to **CPU-first, reproducible Python scripts and notebooks** managed with `uv`:

```bash
uv sync
uv run pytest -q
```

Allocate GPUs only when justified for foundation-model inference or training. On Windows (`cp949` console), set `PYTHONIOENCODING=utf-8` when running Python scripts, keep CLI logs plain ASCII unless Unicode is required, and declare `encoding="utf-8"` on every text `open()`, `.read_text()`, and `.write_text()` (`tools/check_declared_encoding.py`).

## Layout (one home per artifact)

- `docs/` — foundational research handoff, [`docs/references-access.md`](docs/references-access.md), [`docs/lanes-and-promotion.md`](docs/lanes-and-promotion.md), and [`docs/decisions.md`](docs/decisions.md). Never create overlapping summary reports.
- `config/` — [`config/qc_thresholds.yaml`](config/qc_thresholds.yaml) (committed physical/QC constants) and [`config/local_paths.example.yaml`](config/local_paths.example.yaml) (`config/local_paths.yaml` is gitignored).
- `manifests/` & `schemas/` — [`manifests/sources/*.yaml`](manifests/README.md) validated against [`schemas/source_manifest.schema.json`](schemas/source_manifest.schema.json) for external datasets kept out of Git.
- `pre-registrations/` — dated confirmatory experiment protocols committed *before* execution, with append-only deviation sections.
- `notebooks/` — reproducible educational (`Q01`–`Q13`) and exploratory notebooks (no empty placeholder notebooks; see `D-005`).
- `src/hydrospectral/` — tested Python package for provenance, thresholds, radiometry, SRFs, and leakage-free splitters.
- `tools/` — self-testing repository guards (`--self-test` required on each guard).
- `results/` — compact retained benchmark tables, figures, and byte-deterministic `manifest.json` provenance records.
- `tests/` — fast `pytest` suite (`tests/conftest.py` fails on empty collection).
- `data/` — [`data/README.md`](data/README.md) local staging guide; raw archives live outside Git.
- `LICENSE` & `LICENSE-DOCS.md` — MIT for code (`LICENSE`) and CC BY 4.0 for documentation, protocols, and original figures (`LICENSE-DOCS.md`).

## Rules

1. **Epistemic and status hygiene.**
   - Keep **proposed work**, **provenance-incomplete** legacy runs, **exploratory** runs (author-only or post-hoc), and **reproduced** results (independently rerun from recorded inputs by someone other than the author) strictly distinct. Never label an unverified output "verified" or "confirmed".
   - Separate physical **observation**, bio-optical **retrieval**, model **reconstruction**, and ecological **prediction**. Satellite-derived products (e.g., PACE chlorophyll, IOPs, MOANA) are model estimates, never independent field ground truth.
   - Preserve historical experiment ID namespaces (`Q01`–`Q13`, `HS-R01`–`HS-R08`, `GL-R00`–`GL-R15`, `OPT-01`–`OPT-25`, `EA-R01`–`EA-R12`, `EA-01`–`EA-11`); do not silently renumber, and do not add empty stub scripts for unbuilt tasks (`D-005`).

2. **Radiometric, sensor, and ecological invariants.**
   - Join GLORIA tables strictly on `GLORIA_ID`, never row position. Keep corrected `Chla` separate from uncorrected chlorophyll + phaeopigments, and isolate optically inferred targets (e.g., Lake Geneva Thetis line-height Chla) to avoid target circularity.
   - Preserve negative $R_{rs}$ values for baseline-shift and QC diagnostics rather than silently clipping to zero. Distinguish missing QC flags (unmeasured wavelengths) from passed tests. Load QC constants from `config/qc_thresholds.yaml` rather than inventing silent defaults.
   - Convolve spectra with official sensor spectral response functions (SRFs) when claiming sensor simulation; 1 nm interpolation in GLORIA is not 1 nm native spectrometer resolution.
   - Respect foundation-model input domains (e.g., do not feed 339–719 nm PACE OCI cubes directly into Sentinel-3 OLCI + SLSTR checkpoints).
   - Handle 16S/18S and metagenomic data compositionally; distinguish copy counts, relative abundance, absolute abundance, diversity, and optical cross-section.

3. **Validation, lanes, pre-registration, and checks that can fail.**
   - Follow [`docs/lanes-and-promotion.md`](docs/lanes-and-promotion.md): exploratory `sprint/*` branches relax evidence gates (never safety/data gates) and **never merge into `main`**; surviving methods are re-implemented cleanly on a fresh `promote/*` branch from `main`.
   - Fix target, QC cohort, grouping keys, and metrics before model selection; disclose any already-seen exploratory or sprint results in new protocols. Sensitivity ranges are declared up front so they cannot become a post-hoc menu.
   - Evaluate site-held-out, study/dataset-held-out (`Dataset_ID`), and temporal splits alongside random splits; guard against temporal leakage when pairing historical samples with annual embeddings (e.g., AlphaEarth).
   - Benchmark complex or pretrained models against interpretable physical/statistical baselines (2-band ratios, AVW, pyOWT/Spyrakos OWTs, PCA, and location/season `M0`), reporting applicability domain / OOD distance and `attempted`, `completed`, `failed`, and `excluded` counts with explicit denominators.
   - Every check in `tests/` and `tools/` must be able to fail: use hand-worked analytical cases, boundary values just below and just above thresholds, and planted defects (`--self-test`). Prefer an automated check or schema constraint over another warning in prose.

4. **Staging, commits, and repository hygiene (scratch stays outside).**
   - Run one-off sweeps, throwaway scripts, ad-hoc plots, logs, and bulk downloads **outside the repository** (`workspace.scratch_dir` in `config/local_paths.yaml`).
   - Never commit raw archives or large binaries (`.zip`, `.nc`, `.h5`, `.tif`, `.zarr`, checkpoints), third-party publisher PDFs, machine-specific paths (`config/local_paths.yaml`), or credentials (`.env`, `.netrc`, Earth Engine / GCP keys).
   - **Never run `git add -A` or `git add .`.** Stage paths explicitly by name and inspect what is staged immediately before committing so every staged file is intentionally owned by the session:
     ```bash
     git status --short
     git add path/one path/two
     git diff --cached --stat
     git diff --cached --check
     git commit
     ```
   - Batch related edits into coherent commits rather than pushing after every single file, and validate workflow/guard edits locally (`tools/check_*.py --self-test`) rather than debugging via push loops.

5. **Branch and independent review workflow.**
   - Default branch is `main`. Use a feature or promotion branch and PR for non-trivial changes (experiments, code, protocols, schemas, literature claims, or repo policy).
   - Before merging non-trivial changes, obtain an independent review from someone other than the author (a person, or a fresh review agent given the diff, claims, and files without the author's reasoning). Treat fixes as "addressed, awaiting review" until confirmed. Push directly to `main` only for trivial fixes (typos, broken links).

## Agent guidance

Load [experiment-review](.claude/skills/experiment-review/SKILL.md) as the primary workflow guide when writing or reviewing experiments, benchmarks, notebooks, guards, or retained result packages. Load the evidence checklist alongside it whenever literature or scientific claims are involved. Load [adversarial-research-review](.claude/skills/adversarial-research-review/SKILL.md) when the artifact is research prose (a handoff, pre-registration, proposal, review outline, manuscript, or preprint) rather than code:

| Task | Guide / Checklist |
| --- | --- |
| Designing, running, packaging, or reviewing computational experiments and code | [experiment-review](.claude/skills/experiment-review/SKILL.md) |
| Auditing remote-sensing, bio-optical, Earth-AI, or microbial-ecology literature and claims | [scientific-evidence-audit](.claude/skills/scientific-evidence-audit/SKILL.md) |
| Adversarial review of research prose (handoffs, pre-registrations, proposals, manuscripts) | [adversarial-research-review](.claude/skills/adversarial-research-review/SKILL.md) |

For this repository, references to `adversarial-notebook-review` in the imported `adversarial-research-review` skill mean the existing [experiment-review](.claude/skills/experiment-review/SKILL.md) skill. Use `scientific-evidence-audit` alongside either review workflow when auditing domain or literature claims. Repository rules above, including evidence status, single artifact ownership, and independent review, take precedence over generic skill guidance.
