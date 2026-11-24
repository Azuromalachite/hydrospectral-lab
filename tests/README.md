# Checks & Regression Tests (`tests/`)

Fast, deterministic Python checks guarding reusable scientific logic in [`src/`](../src/), data-hygiene rules, and retained result manifests.

## Principles (adapted from `kvis-econ-games-2026`)

1. **Every check must be able to fail.** Verify new checks by introducing a deliberate planted defect in a temporary copy (e.g., shuffling `GLORIA_ID` row order, leaking a `Site_name` across train/test folds, or dropping an illuminant weight in CIE XYZ integration) and confirming the test fails.
2. **Never copy the formula under test.** Compute expected values from independent analytical cases (e.g., flat equiradiance spectrum -> CIE illuminant white point; constant $R_{rs}$ -> exact analytical harmonic-mean AVW; synthetic step spectrum -> exact trapezoidal SRF integral) rather than duplicating implementation expressions.
3. **Test both sides of every threshold.** When testing QC flags or applicability filters (e.g., $|\text{QWIP}| > 0.2$, negative UV slope, complete 400-800 nm coverage), test values immediately below and immediately above the boundary, not just extreme cases.
4. **Keep fixtures tiny and synthetic.** Commit only small, inspectable synthetic spectra or toy tables in `tests/fixtures/`; never commit subsets of restricted files or large archives.
