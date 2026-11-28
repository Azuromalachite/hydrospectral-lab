# Pre-registration: Official SRF Compression vs. Full Hyperspectral Bio-Optical Retrieval on GLORIA (`HS-R02` / `OPT-13`)

- **Date:** 2026-11-26
- **Experiment ID(s):** `HS-R02`, `OPT-13` (paired with `HS-R01` radiometric error-budget audit)
- **Author:** Thanakrit Wongsatit
- **Status:** `PURSUE` (frozen protocol committed prior to executing official-SRF confirmatory evaluations)

## 1. Scientific question

On the globally compiled, locally verified GLORIA aquatic hyperspectral archive (`src.gloria-2022`), does full 1 nm hyperspectral remote-sensing reflectance (`400–800 nm`) yield a statistically and practically meaningful out-of-sample improvement over:
1. Official sensor spectral response function (SRF) convolutions of **ESA Sentinel-2 MSI** and **ESA Sentinel-3 OLCI** restricted strictly to bands whose full non-zero SRF support lies inside `[400, 800]` nm (enforced by `hydrospectral.srf.build_srf_weight_matrix`; e.g., expected `B1–B6`—and `B7` only if its upper tail stays within `800 nm`—plus `Oa02–Oa16`, excluding `Oa01` whose 400 nm centre extends below 400 nm), and
2. Interpretable physical/statistical baselines (2-band red-edge ratio `Rrs(705)/Rrs(665)`, Apparent Visible Wavelength `AVW`, and geographic/seasonal baseline `M0`)

when predicting `log10(Chla)`, `log10(TSS)`, and `log10(aCDOM440)` under **waterbody-held-out** (`Country|Site_name`) and **study-held-out** (`Dataset_ID`) 5-fold cross-validation?

## 2. Seed observation & prior exposure (disclosed)

You cannot un-see prior exploratory runs. Before committing this protocol, the following results on `GLORIA-2022.zip` have already been observed:
- `docs/aquatic-hyperspectral-handoff-2026-11-25.md` §4 (`HS-R01`, `HS-R02`, `GL-R00`–`GL-R04`): exploratory 6-band rectangular boxcar baseline (`provenance-incomplete`) showing modest or negative gains for naive full-spectrum models relative to compact band ratios under site-held-out splits, and large optimism gaps between random K-fold and waterbody/dataset holdouts.
- `results/Q01_water_colour/` (`status: exploratory`): GLORIA 400–700 nm CIE chromaticity, AVW, QWIP, and `Water_body_type`/`Water_type` distributions (`n = 5,719` unflagged complete 400–700 nm spectra), plus real-archive metadata audit pinning `Dataset_ID = "OdermattD_CH_Eawag"` (`n = 290`, `Chl_method = "Eawag Chl - aLH"`).
- **Not yet seen:** Official ESA Sentinel-2 MSI / Sentinel-3 OLCI SRF convolutions (`hydrospectral.srf`), paired equal-group RMSE / whole-site cluster bootstrap CIs (`hydrospectral.splits`), or the `OdermattD_CH_Eawag`-isolated confirmatory folds specified below.

## 3. Cohort & QC rules (frozen)

- **Primary input archive:** `src.gloria-2022` (`GLORIA-2022.zip`, `58,956,647` bytes, verified SHA-256 `f5ad5106d5fd74f0d874085a23e4189302e7409aed9f82d629ae6cdb47d21f14`).
- **Official SRF inputs (to be staged and digest-verified in `manifests/sources/` before execution):**
  - ESA Sentinel-2A MSI official SRF table (bands whose support lies strictly within `[400, 800]` nm; verified by `hydrospectral.srf.build_srf_weight_matrix`).
  - ESA Sentinel-3A OLCI official SRF table (bands whose support lies strictly within `[400, 800]` nm; verified by `hydrospectral.srf.build_srf_weight_matrix`).
- **Join & target invariants (`hydrospectral.gloria`):**
  - Join strictly one-to-one on `GLORIA_ID` (never row position).
  - Targets evaluated independently on their own complete-case cohorts:
    - `Chla` (`ug/L`, transformed to `log10(Chla)`): strictly corrected `Chla` only (never `Chla_plus_phaeo`); **exclude optically derived Chla** (`exclude_optically_derived_chla=True`, isolating `OdermattD_CH_Eawag` from `config/qc_thresholds.yaml`).
    - `TSS` (`mg/L`, transformed to `log10(TSS)`).
    - `aCDOM440` (`m^-1`, transformed to `log10(aCDOM440)`).
  - Spectral window: `400–800 nm` at 1 nm step (`complete_benchmark_window_nm` in `config/qc_thresholds.yaml`), finite across all 401 wavelengths.
  - QC policy: `require_unflagged=True` (no flag in the 7 GLORIA QC columns), `require_all_qc_tested=False` (distinguishing unmeasured wavelengths from failures); **preserve negative $R_{rs}$ values unclipped** and report `n_with_negative_rrs`.
  - Grouping validity: non-empty `Country|Site_name` for waterbody splits; non-empty `Dataset_ID` for study splits.
- **Expected primary `Chla` cohort denominator (from `build_target_cohort` audit):** `attempted = 7,572`, `completed = 2,840`, `excluded = 4,732` (`n_with_negative_rrs = 308`).
- **Key gating:** Every compared feature arm within a target/split cell must carry an identical `cohort_key` (`hydrospectral.provenance.assert_matching_cohort_keys`) and identical fold index arrays (`hydrospectral.splits.assert_paired_splits`).

## 4. Conditions, ablations & splits

### Feature arms (identical observations & paired folds per target)
1. **`B0_ratio` (physical baseline):** 2-band log-ratio `log10(Rrs(705)/Rrs(665))` for `Chla` (plus `Rrs(665)` for `TSS`, `log10(Rrs(560)/Rrs(443))` for `aCDOM440`) and `AVW` (where strictly non-negative; missingness handled explicitly via complete-case sub-cohort comparison so denominators stay paired).
2. **`M0_context` (non-optical baseline):** Latitude, longitude, and circular day-of-year (`sin/cos`) only — measures how much predictability comes purely from geography and season.
3. **`S2_SRF`:** Official ESA Sentinel-2 MSI SRF-convolved bands within `400–800 nm`.
4. **`S3_SRF`:** Official ESA Sentinel-3 OLCI SRF-convolved bands within `400–800 nm`.
5. **`HS_401`:** Full 1 nm GLORIA reflectance (`400–800 nm`, 401 bands) with standardized preprocessing (raw reflectance and L2-normalized shape + log-magnitude as two fixed sub-arms).

### Fixed estimator family (CPU-reproducible, grids locked prior to test evaluation)
- **Linear regularized (`Ridge`):** `alpha` selected strictly inside training folds over the 17-point log-spaced grid `np.logspace(-4, 4, 17)`.
- **Nonlinear tree ensemble (`HistGradientBoostingRegressor`):** `max_iter=300`, `random_state=2026`, tuning strictly inside training folds over `max_depth in {3, 6}`, `learning_rate in {0.03, 0.1}`, `min_samples_leaf in {10, 30}`, and `l2_regularization in {0.0, 1.0}`.

### Splits (all four reported side-by-side)
1. **Primary:** 5-fold waterbody-held-out `GroupKFold` on `Country|Site_name`.
2. **Primary (transfer):** 5-fold study-held-out `GroupKFold` on `Dataset_ID`.
3. **Primary (prospective temporal):** Chronological holdout via `hydrospectral.splits.make_temporal_split` on `Date_Time_UTC` (cutoff fixed at the 80th percentile timestamp of dated cohort observations per target; undated rows reported explicitly in exclusion accounting).
4. **Diagnostic reference only:** 5-fold random K-fold (reported strictly to quantify validation-inflation gap, never used for model selection).

### Committed radiometric error budget (analogous to `espmap/bench/`)
Report paired delta sensitivity on the primary split for:
- Official SRF convolution vs. rectangular boxcar bandpass approximation;
- Preserving negative $R_{rs}$ vs. excluding negative-$R_{rs}$ spectra;
- Isolating `OdermattD_CH_Eawag` vs. retaining it (on `400–700 nm` window where `286` rows enter).

## 5. Outcomes & decision rules

Primary metric: **equal-group `log10` RMSE** (`compute_regression_metrics(..., groups=...)`) alongside pooled `log10` RMSE, raw-unit MAE, and raw-unit MdSA. Paired differences between arms use whole-group cluster bootstrapping (`paired_group_bootstrap_delta`, `n_bootstrap = 2000`, `seed = 2026`).

- **Interesting (hyperspectral advantage supported):** `HS_401` improves equal-group `log10` RMSE over **both** `S3_SRF` and `B0_ratio` by at least `0.03` log10 units (~7% multiplicative error reduction) on at least one target under **both** `Country|Site_name` and `Dataset_ID` holdouts, with the 95% cluster-bootstrap CI strictly below `0` AND larger than the measured SRF-vs-boxcar radiometric budget.
- **Boring / null (scientifically informative):** `HS_401` vs. `S3_SRF` (or `S2_SRF`) 95% cluster-bootstrap CI spans `0` or shows $< 0.03$ log10-unit improvement under study holdout. *Why informative:* bounds the standalone value of 1 nm interpolated reflectance without OWT stratification (`OPT-19`), derivative/unmixing physics, or riverine/tropical domain coverage (noting rivers are only 3.3% of GLORIA with zero Thai observations).
- **Failure / artifact:** Any `cohort_key` mismatch, `SplitLeakageError`, non-zero overlap of `Site_name`/`Dataset_ID` across train/test, or gain that disappears once `M0_context` or `OdermattD_CH_Eawag` circularity is controlled.

## 6. Forking-paths guard

- Fixed random seed: `2026` across splits and bootstrap resampling.
- All inner hyperparameter tuning runs exclusively inside training folds using nested group splits (`Country|Site_name` or `Dataset_ID`), never peeking at held-out test folds.
- No band subset, outlier cutoff, or target transform may be altered after viewing held-out fold metrics; any post-hoc exploration moves to an unmerged `sprint/*` branch (`docs/lanes-and-promotion.md`).
- Applicability domain: report nearest-neighbor SAM OOD distance (`nearest_neighbor_sam_ood`) per held-out fold and stratify test error by in-domain vs. OOD spectra and by `Water_body_type` (explicitly reporting river sample size `n`).

## 7. Deviations (append-only, dated)

### 2026-11-26 — Real-archive preflight observed; confirmatory run still blocked

An external audit of `GLORIA-2022.zip` (58,956,647 bytes, SHA-256 `f5ad5106d5fd74f0d874085a23e4189302e7409aed9f82d629ae6cdb47d21f14`) was imported as `results/HS-R02_gloria_preflight/` with status `provenance-incomplete`. No retrieval model was fitted and no held-out score was inspected. The audit script is not `hydrospectral.gloria.build_target_cohort`. This workspace did not contain the archive, so the counts below were checked for internal arithmetic consistency and were not recomputed from the zip.

Primary cohorts reported by that audit, using the same sequential filters as section 3 (positive target, finite 400–800 nm \(R_{rs}\), unflagged on the seven QC columns, Chla optical-circularity mask, non-empty `Country|Site_name`):

| Target | Attempted | Completed | Excluded | Negative \(R_{rs}\) in the completed cohort |
| --- | ---: | ---: | ---: | ---: |
| Chla | 7,572 | 2,840 | 4,732 | 308 |
| TSS | 7,572 | 3,038 | 4,534 | 31 |
| aCDOM440 | 7,572 | 2,709 | 4,863 | 264 |

The Chla row matches the expected denominator in section 3. The optical-circularity step removed **0** Chla rows after the preceding filters, and the audit reports 290 optical-Chla marker rows in the whole archive. The section 3 isolate-`OdermattD_CH_Eawag` control is therefore not exercised by the 400–800 nm primary cohort. A 400–700 nm retain-versus-exclude count is still required before any claim that circularity was stress-tested. These preflight counts are now prior exposure for every later confirmatory run.

The following clarifications were proposed with the import and are **not adopted**. Sections 4–6 are unchanged. No threshold, feature arm, estimator, or success rule moves because these counts were seen.

| ID | Proposal left unresolved |
| --- | --- |
| A01 | Call the existing cluster bootstrap as RMSE(HS) − RMSE(reference) when the decision rule needs a negative interval to favor hyperspectral reflectance. Record that sign in the result manifest. |
| A02 | Report raw-unit MdSA, \(100(\exp(\mathrm{median}(\|\ln(\hat y/y)\|))-1)\), in addition to raw MAE and raw median absolute error. `compute_regression_metrics` does not yet return MdSA. |
| A03 | `build_srf_weight_matrix` treats response above `1e-8` times the band maximum as support. The candidate kernel treats any sampled \(R>0\), including a \(10^{-12}\) table endpoint, as support. Freeze one rule before SRF conversion. |
| A04 | Ratio and AVW are undefined on some retained spectra. The audit's all-arm intersection (Chla 2,764, TSS 2,982, aCDOM440 2,644) is not the primary cohort. Do not drop rows for one arm only. |
| A05 | Primary cohorts in the audit had no missing `Dataset_ID`. Three aCDOM440 rows had missing or unparseable timestamps. Exact `GLORIA_ID` order and fold indices still have to be compared with `build_target_cohort` before scoring. |
| A06 | Inner-fold count, inner loss, temporal inner scheme, and `HistGradientBoostingRegressor` early stopping are still unspecified. The candidate kernel is not approved and is not wired into CI. |
| A07 | This protocol's `OPT-13` label collides with the handoff's pigment-concentration task. Keep `HS-R02` and `GL-R08` as the canonical IDs. Do not renumber. |
| A08 | Two hyperspectral sub-arms and two estimators across three targets can be selected after seeing scores. No primary cell is frozen by this deviation. |
| A09 | "Gain disappears once M0 is controlled" is not defined by reporting the context-only arm. No context-plus-optics ablation is added. |
| A10 | Recompute optical-Chla retain versus exclude on 400–700 nm without changing the 400–800 nm primary cohort. |

Official Sentinel-2 MSI and Sentinel-3 OLCI SRF bytes are still unpinned. `results/HS-R02_gloria_preflight/candidate/stage_inputs.py` only names candidate URLs. Confirmatory evaluation stays blocked until those files are staged outside Git, digest-verified, and converted under the frozen support rule. Published MDN or BNN weights (`GL-R07`) stay out of this protocol until a separate, pre-result specification audits training overlap.
