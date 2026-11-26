# HS-R02 GLORIA preflight (`provenance-incomplete`)

Imported real-archive cohort audit for the frozen protocol in [`pre-registrations/2026-11-26-hs-r02-official-srf-retrieval.md`](../../pre-registrations/2026-11-26-hs-r02-official-srf-retrieval.md). No retrieval model was fitted. No held-out scores exist in this package. This is not a confirmatory `HS-R02` result.

**Evidence status:** `provenance-incomplete`. The numbers were produced outside this repository by `audit_gloria.py` and were not recomputed here: `GLORIA-2022.zip` is not in the workspace. `author_run_manifest.json` is that external run record. `manifest.json` is the repository import record and does not claim a clean-tree rerun.

## What was checked on import

Sequential exclusion counts in `exclusions.csv` sum to `excluded` for Chla (4,732), TSS (4,534), and aCDOM440 (4,863). Water-body type counts in `waterbody_counts.csv` sum to each primary `completed` value. `completed - negative_rrs` matches the `no_negative` rows in `sensitivity_counts.csv`. The Chla primary denominator matches the protocol's expected 2,840 / 7,572 with 308 negative-\(R_{rs}\) rows.

On this 400–800 nm primary cohort the sequential `optically_derived_chla_circularity` exclusion is **0**. The frozen Lake Geneva / line-height control removes nobody after the completeness and QC filters. Matching 2,840 does not show that the circularity sensitivity was exercised. That comparison stays outstanding on the declared 400–700 nm window (protocol deviation, 2026-11-26).

`candidate_all_arm_paired` (Chla 2,764, TSS 2,982, aCDOM440 2,644) is a proposed intersection of ratio, AVW, coordinates, date, and study membership. It is not an approved replacement for the primary cohort.

`radiometry.json` is an algebraic \(|R_{rs} - L_w/E_s|\) diagnostic on finite pairs with \(E_s > 0\). It is not a glint or atmospheric-correction validation. Quantiles are wavelength-point weighted and include flagged and incomplete spectra.

The archive worksheet claim that water-body type code 4 means river was not reopened in this import.

## Files

| File | Role |
| --- | --- |
| `audit_gloria_as_run.txt` | Exact script that produced the tables. Its SHA-256 is `author_run_manifest.json` `code_sha256` |
| `audit_gloria.py` | Same audit, with `ZipFile.read` instead of `ZipFile.open`, so the repository encoding guard accepts it. It was not rerun on the archive |
| `cohorts.csv`, `exclusions.csv`, `sensitivity_counts.csv`, `waterbody_counts.csv` | Denominator tables |
| `radiometry.json` | Pointwise \(R_{rs}\) versus \(L_w/E_s\) discrepancy |
| `author_run_manifest.json` | External run record (Python 3.13.5, numpy 2.3.5, pandas 2.2.3) |
| `manifest.json` | Repository import manifest (`hydrospectral.provenance`) |
| `candidate/` | Unapproved group-CV kernel, its five synthetic tests, and an SRF staging helper |

`candidate/benchmark_kernel.py` does not call `hydrospectral.splits` or `hydrospectral.gloria`. Its five synthetic tests passed in this review (2.51 s) under an ad hoc scikit-learn install. scikit-learn is not in the locked development environment, so CI does not collect those tests. `candidate/stage_inputs.py` writes outside Git. Its Sentinel-2 and Sentinel-3 URLs are unverified candidates; only the GLORIA SHA-256 is frozen.
