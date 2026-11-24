# hydrospectral-lab

Exploring aquatic ecosystems through hyperspectral imaging, Earth observation, environmental foundation models, and reproducible computational experiments.

## Central Question

> To what extent can the optical phenotype of an aquatic ecosystem, together with environmental context and hydrological connectivity, reveal its underlying microbial organisation and dynamics?

`hydrospectral-lab` follows a physics-first learning and research progression before attempting large integrated models or field hardware deployments:

**Radiometry → spectral quality → colour science → optical water types → measurement uncertainty → bio-optical inversion → geographical and temporal context → microbial ecology.**

Foundational synthesis, baseline audit, and 13-question curriculum:
- [Aquatic hyperspectral research handoff & roadmap (2026-11-25)](docs/aquatic-hyperspectral-handoff-2026-11-25.md)
- [Reference access & reading status inventory](docs/references-access.md)

## Observational Stack

1. **Field spectroscopy & lab chemistry:** [GLORIA](https://doi.org/10.1594/PANGAEA.948492) (Lehmann et al., 2023) paired $R_{rs}$ spectra, radiometric components, QC flags, and water-quality measurements.
2. **Satellite observations & Earth-science AI (frozen priority portfolio):**
   - **AlphaEarth Foundations** — annual 10 m, 64-D environmental context embeddings
   - **Google Earth Engine** — scalable multi-sensor geospatial extraction
   - **PARDIG** — historical precipitation and watershed perturbation series
   - **Granite-Geospatial-Ocean** — pretrained Sentinel-3 OLCI + SLSTR representations
   - **NASA PACE derived products** — hyperspectral OCI apparent/inherent optical properties and model-derived biological products
3. **Future coordinated field campaigns:** Recoverable scientific drifters, calibrated radiometry, and time-matched molecular sampling in Thai riverine and coastal waters.

## Curriculum Queue

Detailed in [Section 10 of the handoff](docs/aquatic-hyperspectral-handoff-2026-11-25.md#10-educational-mock-research-questions-full-current-curriculum):

- **Level 1 — Observation (`Q01`–`Q03`):** Water colour & optical water types (GLORIA + PACE), unsupervised AlphaEarth landscape clustering, and waterway environmental analogues.
- **Level 2 — Quantification (`Q04`–`Q06`):** Spaceborne rainfall reconstruction (PARDIG), PACE derived-product comparisons, and masked Sentinel-3 ocean-colour reconstruction (Granite Ocean).
- **Level 3 — Integration (`Q07`–`Q09`):** Post-rainfall coastal plumes, landscape context vs. reflectance ablations (`GLORIA-Context`), and foundation-model vs. physical OWT representations.
- **Level 4 — Thailand applications (`Q10`–`Q13`):** Upper Gulf river plumes, Songkhla Lake zonation, phytoplankton bloom emergence, and recoverable drifter sampling design.

**First five exercises in execution order:** `Q01` → `Q02` → `Q05` → `Q04` → `Q06`.

## Structure

```text
AGENTS.md                 Epistemic, radiometric, validation, and Git workflow rules
CITATION.cff              Citation metadata for code and retained packages
LICENSE                   MIT License (code, notebooks, and tests)
LICENSE-DOCS.md           CC BY 4.0 License (documentation, notes, and original figures)
.claude/skills/           Agent checklists for experiment review and scientific evidence audit
data/                     Dataset checksum inventory (raw archives staged locally, gitignored)
docs/                     Research handoff and reference reading/access ledger
pre-registrations/        Dated confirmatory protocols (committed prior to runs; append-only deviations)
notebooks/                Reproducible CPU-first curriculum (Q01-Q13) and exploratory notebooks
src/                      Reusable Python modules for radiometry, QC, SRFs, and splitters
results/                  Compact benchmark tables, figures, and deterministic manifest.json files
tests/                    Analytical, threshold-boundary, and planted-defect checks
```

## Contributing & Rigor

Read [`AGENTS.md`](AGENTS.md) before modifying code, running benchmarks, or adding claims. Scratch explorations and large raw binaries stay outside Git; non-trivial changes use feature branches, checks that can fail, and independent review.

## License

| Scope | License | Details |
| --- | --- | --- |
| Source code (`src/`, `tests/`, scripts, notebook code cells) | MIT License | [LICENSE](LICENSE) |
| Documentation, protocols, notes, and original figures (`docs/`, `pre-registrations/`, `results/`, prose) | CC BY 4.0 | [LICENSE-DOCS.md](LICENSE-DOCS.md) |
| External datasets, satellite granules, and cited literature | Upstream licenses | Not redistributed in Git; see [data/README.md](data/README.md) and [docs/references-access.md](docs/references-access.md) |
