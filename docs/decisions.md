# Architectural & Methodological Decisions

Durable repository-wide decisions recorded so future contributors and agents understand *why* constraints exist rather than working around them.

## D-001 — Split license: MIT for code, CC BY 4.0 for documentation and figures (2026-11-25)

- **Decision:** Keep [`LICENSE`](../LICENSE) as verbatim MIT text for all executable code (`src/`, `tests/`, `tools/`, notebook code cells) and [`LICENSE-DOCS.md`](../LICENSE-DOCS.md) as CC BY 4.0 for documentation, protocols, and original figures.
- **Reason:** Pure MIT in `LICENSE` lets standard tooling (including GitHub's license detector) classify software permissions unambiguously, while CC BY 4.0 preserves attribution for scientific syntheses, protocols, and figures. Upstream datasets and third-party papers remain outside Git under their own licenses.

## D-002 — `uv` lockfile, CPU-first baseline, and explicit UTF-8 text I/O (2026-11-25)

- **Decision:** Manage Python dependencies via `pyproject.toml` and `uv.lock` (`python >= 3.11`), default to CPU-reproducible workflows, and enforce explicit `encoding="utf-8"` on every Python text read/write via `tools/check_declared_encoding.py`.
- **Reason:** Development spans Windows (`cp949` default locale) and Linux CI (`UTF-8`). Bare `open()` or `Path.read_text()` silently corrupts or crashes on non-ASCII characters (such as units `µg/L`, `sr⁻¹`, or accented author names) across platforms.

## D-003 — Four-lane exploration vs. promotion model (2026-11-25)

- **Decision:** Separate off-repo scratch, unmerged `sprint/*` branches, fresh `promote/*` branches, and standard `feat/*`/`fix/*`/`docs/*` branches ([`docs/lanes-and-promotion.md`](lanes-and-promotion.md)). Forbid merging `sprint/*` into `main` via `tools/check_repo_hygiene.py`.
- **Reason:** Hyperspectral band selection and EO feature engineering invite look-elsewhere bias. Re-implementing surviving methods on a fresh branch from `main` with disclosed prior exposure prevents sprint-tuned thresholds from masquerading as confirmatory findings.

## D-004 — External source manifests with `digest_verified` honesty and gitignored local paths (2026-11-25)

- **Decision:** Track external datasets via `manifests/sources/*.yaml` validated against [`schemas/source_manifest.schema.json`](../schemas/source_manifest.schema.json), referencing symbolic keys in gitignored `config/local_paths.yaml`. Keep `digest_verified: false` until the SHA-256 hash is recomputed on the local checkout.
- **Reason:** Keeps multi-hundred-megabyte archives (`.zip`, `.nc`) and workstation paths out of public Git history while distinguishing upstream/handoff checksums from locally verified files.

## D-005 — No empty stub scripts for unbuilt analyses (2026-11-25)

- **Decision:** Do not commit placeholder `.py` scripts or empty notebooks for `Q01`–`Q13`, `HS-R*`, `OPT-*`, or `EA-R*` before their real logic and tests exist. Track planned vs. implemented status explicitly in `README.md`.
- **Reason:** A stub script that exits 0 or returns an empty table is indistinguishable from a working analysis over an empty cohort. Every committed module or check must fail on broken or empty inputs (`tests/conftest.py`).

## D-006 — Explicit path staging (`git add <paths>`) over wildcard staging (2026-11-25)

- **Decision:** Stage files explicitly by path (`git add path/one path/two`), inspect `git diff --cached --stat` and `git diff --cached --check` immediately prior to `git commit`, and avoid `git add -A` / `git add .` (`AGENTS.md` rule 4).
- **Reason:** Prevents untracked files, temporary outputs, or concurrent session edits in a shared working directory from being swept into an unrelated public commit.

## D-007 — Key-gated comparisons (`cohort_key`, `render_key`), Crameri colormaps, and mutation-tested invariants (2026-11-26)

- **Decision:** Adopt deterministic comparison keys (`hydrospectral.provenance.compute_cohort_key` and `hydrospectral.palette.compute_render_key`, adapted from public [`espmap`](https://github.com/Azuromalachite/espmap)'s `analysis_key`/`render_key`), vendor frozen MIT-licensed Fabio Crameri colour maps (`batlow`, `vik`, `lajolla` in `src/hydrospectral/_bundled/crameri_colormaps.json`) for scalar geophysical maps while reserving CIE 1931 display sRGB exclusively for perceived water colour, and enforce mutation-tested invariants via `tools/mutants.tsv` + `tools/check_mutants.py` in CI.
- **Reason:** Rainbow/turbo colour scales distort scalar gradients and fail colour-vision-deficiency checks; unkeyed side-by-side comparisons invite apples-to-oranges errors across targets, wavelength windows, or stretches; and automated mutation killing proves core leakage/QC/ID-join tests can actually fail.

## D-008 — Decoupled public-repository integration contract & curriculum pedagogy (2026-11-26)

- **Decision:** Keep `hydrospectral-lab` decoupled from sibling public repositories ([`espmap`](https://github.com/Azuromalachite/espmap) and [`arrowfield`](https://github.com/Azuromalachite/arrowfield)), consuming upstream instruments or bundles only by pinned release tags/commits and verified SHA-256 checksums (never `main`/`master`). Structure `Q01`–`Q13` curriculum notebooks and retained `results/Q*/` packages around `arrowfield`'s five-step `Predict → Reveal → Explain → Control → Limits` pedagogy, enforced by `tests/test_pedagogy_contracts.py`.
- **Reason:** Clear fact ownership across repositories prevents silent drift, preserves independent release lifecycles, and guarantees every educational result displays its controls, units, denominators, prior exposure, and inferential limits.

## D-009 — Semantic `.dev0` versioning, measurement contracts, and tag release gate (2026-11-26)

- **Decision:** Follow public [`espmap`](https://github.com/Azuromalachite/espmap)'s versioning and release-evidence model:
  1. Keep `src/hydrospectral/__init__.py` (`__version__`) as the single source of truth via Hatch `dynamic = ["version"]`, use PEP 440 `.dev0` suffixes (e.g., `0.4.0.dev0`) on `main` between tagged releases so unreleased checkouts never impersonate a release, and keep `CITATION.cff` version in lockstep (tested in CI).
  2. Track numeric compatibility explicitly via `hydrospectral.provenance.MEASUREMENT_CONTRACT` (`hydrospectral.numeric/1`), embedded into `cohort_key` and `manifest.json`, with `CONTRACT_BY_RELEASE` populated at each `vX.Y.Z` release. Any change that alters a numerical output under an unchanged `cohort_key` must bump the measurement contract.
  3. Gate every pushed `v*` tag in CI via `tools/check_release.py`, requiring `results/releases/acceptance_v<version>.json` (`hydrospectral.acceptance/1`) generated on a clean commit whose diff to the tag touches only non-numerical files (`*.md`, `CITATION.cff`, and the acceptance JSON itself).
- **Reason:** Downstream repositories pinning a release tag (e.g., `v0.4.0`) can trust that the published acceptance evidence, mutation checks, and test results belong to the exact code tagged.
