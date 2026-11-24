# Pre-registrations (`pre-registrations/`)

Confirmatory experiments (such as `HS-R02` official SRF compression, `OPT-19` global vs. OWT-specific retrieval, or `Q08` / `EA-R04` `GLORIA-Context` landscape ablations) commit a dated protocol here **before** running test evaluations. Purely educational walkthroughs (`Q01`–`Q05`) do not need formal pre-registration unless making a comparative performance claim, and remain labelled `exploratory`.

## Required sections (adapted from `kvis-econ-games-2026`)

1. **Header:** Date, experiment ID(s) (preserving handoff namespaces), author, and status (`PURSUE` / `DRAFT`).
2. **Seed observation & prior exposure:** What motivated the test, and an explicit disclosure of any exploratory runs, tutorials, or summary statistics already seen on the same dataset ("you cannot un-see prior results").
3. **Cohort & QC rules (frozen):** Exact input dataset SHA-256, join keys (`GLORIA_ID`), target column, unit, exclusions (e.g., optically derived Chla circularity filter, QC flags), and expected complete-case sample size.
4. **Conditions / ablations & splits:** Exact model cells (e.g., `M0` geographic/seasonal baseline, `M1` reflectance, `M2` context, `M3` reflectance + context) and independent split definitions (waterbody-held-out, `Dataset_ID`-held-out, temporal holdout).
5. **Outcomes & decision rules:**
   - *Interesting* — quantitative threshold showing meaningful out-of-sample gain over physical/contextual baselines.
   - *Boring / null* — gain within noise or zero; explicitly state why a null result is scientifically informative (e.g., bounding what spaceborne optics cannot resolve without in situ drifters).
   - *Failure / artifact* — evidence of spatial/temporal leakage, target circularity, or sensor mismatch.
6. **Forking-paths guard:** Hyperparameter tuning inner loop, random seeds, paired fold assignments, and metrics fixed in advance; nothing selected on held-out folds.
7. **Deviations (append-only, dated):** Never rewrite predictions after observing outputs. Append dated deviation notes if data barriers or bugs force changes, and keep failed predictions recorded as failed.
