---
name: experiment-review
description: Use when designing, implementing, packaging, or reviewing computational experiments, notebooks, bio-optical retrievals, foundation-model evaluations, or retained benchmark packages in hydrospectral-lab. Covers lean documentation, pre-registration and disclosing seen results, checks that can fail, leakage-free validation, byte-deterministic manifests, keeping scratch work outside Git, and independent review.
---

# Designing, Packaging, or Reviewing an Experiment

Code, scripts, and `manifest.json` files are the source of truth for what an analysis actually computed. Read the code and manifest rather than writing prose that restates constants or pipeline steps.

## 1. Write down only what the code cannot tell you

| Write it down | Why the code cannot say it |
| --- | --- |
| The scientific or educational question (`Q01`-`Q13`, `HS-R*`, `OPT-*`, `EA-R*`) and what a negative result means | Scientific intent is not in the code |
| Results already seen on the dataset before this run | You cannot un-see prior exploratory metrics; any new protocol must disclose them |
| Cohort exclusions and domain hazards (e.g., Lake Geneva optically derived Chla circularity, NRT granule processing limits) | Filter code shows *what* was dropped, not *why* keeping it invalidates inference |
| Provenance status (`provenance-incomplete`, `exploratory`, `reproduced`) | Passing a script run does not mean independent reproduction |
| Upstream dataset licenses, versions, and SHA-256 hashes | Arrays in memory carry no legal or archival provenance |

**Do not duplicate:** wavelength tables, hyperparameter dicts, or status boards already recorded in [`docs/aquatic-hyperspectral-handoff-2026-11-25.md`](../../../docs/aquatic-hyperspectral-handoff-2026-11-25.md) or `manifest.json`. Put task-local reasoning in the PR description and durable outputs in their single home (`AGENTS.md`).

## 2. Enforce physical and statistical baselines

Before claiming any benefit from hyperspectral resolution, deep learning, or foundation-model embeddings:

- **Verify joins and units:** Join GLORIA strictly on `GLORIA_ID`. State whether metrics (e.g., $R^2$, RMSE, MAE, MdSA) are computed in `log10` space or native physical units (`sr^-1`, `ug/L`, `mg/L`, `m^-1`, `m`, `NTU`).
- **Preserve physical diagnostics:** Do not clip negative $R_{rs}$ values before QC inspection. Distinguish unmeasured wavelengths (missing QC flags) from passed QC tests.
- **Prevent leakage:** Report waterbody-held-out, study/dataset-held-out (`Dataset_ID`), and temporal splits alongside random K-fold splits. Ensure identical observations and identical fold pairings across compared feature sets (e.g., hyperspectral vs. official SRF multispectral; `M0` vs. `M1` vs. `M2` vs. `M3`). Check observation dates against annual embedding windows (e.g., AlphaEarth) so future observations never leak into prospective tasks.
- **Include interpretable baselines and OOD diagnostics:** Compare against 2-band ratios (e.g., 705/665 nm), AVW, Spyrakos/pyOWT water types, PCA, and location/season baselines (`M0`). Report spectral-angle or embedding nearest-neighbour distance so out-of-distribution waters (such as underrepresented tropical rivers) are flagged rather than silently extrapolated.

## 3. Show the code works with a check that can fail

- **Independent expected values:** Test radiometric and statistical functions against hand-worked analytical spectra (flat spectrum, two-wavelength Dirac/step, exact linear/nonlinear synthetic mixtures), never by copying the implementation formula into the test.
- **Boundary coverage:** Test values immediately below and immediately above every QC or applicability threshold you name (e.g., $|\text{QWIP}| = 0.199$ and $0.201$).
- **Planted defects:** Temporarily break one critical assumption (e.g., shuffle metadata rows relative to `GLORIA_Rrs.csv`, leak one `Dataset_ID` across train/test, or mis-align wavelength centres) and verify your test suite catches it. A check that cannot fail proves nothing.
- **Report honestly:** State which checks were executed and their exact exit status, and which checks were not run.

## 4. Package durable results without bloating Git

- **Keep scratch outside the repo (`AGENTS.md` rule 4):** Run exploratory sweeps, debugging plots, and bulk downloads in a scratch/temp folder outside the repository.
- **Byte-deterministic `manifest.json`:** Record `schema_version`, status (`exploratory` until someone else reruns it), repository commit, script path and SHA-256, input dataset SHA-256s, runtime (`CPython`, OS, package versions), RNG seeds and fold-pairing rules, `attempted` / `completed` / `failed` / `excluded` counts with denominators, and a units dictionary. Omit wall-clock timestamps so reruns produce identical bytes.
- **History policy:** Never edit a committed pre-registration's predictions or retroactively alter a dated result report; record deviations append-only and add follow-ups as new dated records.

## 5. Independent review & Git hygiene

- For any non-trivial change, request review from a person or a fresh agent given the diff, claims, and files (without the author's reasoning). Ask the reviewer to run the checks and hunt for spatial/temporal leakage, target circularity, sensor-domain mismatches, and overclaims.
- Keep LF line endings (`.gitattributes`), inspect `git status` and diff size before committing, run `git diff --check` to prevent conflict markers, and use `PYTHONIOENCODING=utf-8` on Windows consoles.
