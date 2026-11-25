# hydrospectral-lab

Exploring aquatic ecosystems through hyperspectral imaging, Earth observation, environmental foundation models, and reproducible computational experiments.

## Central Question

> To what extent can the optical phenotype of an aquatic ecosystem, together with environmental context and hydrological connectivity, reveal its underlying microbial organisation and dynamics?

`hydrospectral-lab` follows a physics-first learning and research progression before attempting large integrated models or field hardware deployments:

**Radiometry → spectral quality → colour science → optical water types → measurement uncertainty → bio-optical inversion → geographical and temporal context → microbial ecology.**

Core records:
- [Aquatic hyperspectral research handoff & roadmap (2026-11-25)](docs/aquatic-hyperspectral-handoff-2026-11-25.md)
- [Reference access & reading status inventory](docs/references-access.md)
- [Lanes & promotion policy](docs/lanes-and-promotion.md) · [Architectural decisions](docs/decisions.md)

## Status & What Is Executable Today

Seed specification, provenance infrastructure, and tested configuration/manifest guards. **No confirmatory ecological or Thai field validation claim is made here**; benchmark numbers recorded in the [2026-11-25 handoff](docs/aquatic-hyperspectral-handoff-2026-11-25.md) retain their stated `exploratory` or `provenance-incomplete` status until packaged and independently rerun.

| Component | Does | Does not |
| --- | --- | --- |
| `hydrospectral.thresholds` | Loads committed radiometric and QC constants from [`config/qc_thresholds.yaml`](config/qc_thresholds.yaml) | Invent silent fallback defaults for undeclared thresholds |
| `hydrospectral.manifests` | Validates [`manifests/sources/*.yaml`](manifests/README.md) against [`schemas/source_manifest.schema.json`](schemas/source_manifest.schema.json) and refuses `example: true` templates | Claim a dataset digest is verified locally until `digest_verified` is earned on disk |
| `tools/check_conflict_markers.py` | Scans tracked files for leftover Git conflict markers (with `--self-test`) | Flag legitimate Markdown `=======` setext headings or pass on an empty tree |
| `tools/check_declared_encoding.py` | Verifies explicit `encoding=` on every Python text read/write across OS locales (with `--self-test`) | Skip `.github/` scripts or rely on directory names instead of `pyvenv.cfg` |
| `tools/check_repo_hygiene.py` | Blocks tracked raw binaries/publisher PDFs, `config/local_paths.yaml`, `sprint/*` merges, and invalid source manifests (with `--self-test`) | Replace scientific review of cohort selection or validation splits |

### Workstream Stages

*Completion means computational completion only; no field or ecological validity is inferred.*

| Workstream | Status | Notes |
| --- | --- | --- |
| Repository guards, QC config & source manifest schema | `IMPLEMENTED_AND_TESTED` | Enforced via `uv run pytest -q` and `tools/check_*.py --self-test` in CI |
| GLORIA initial audit & 6-band rectangular baseline (`HS-R01`, `HS-R02`, `GL-R00`–`GL-R04`, `GL-R06`) | `EXPLORATORY_HANDOFF_ONLY` | Summarised in handoff §4; retained package import and independent rerun pending |
| PACE-01 Gulf of Mexico introductory reconstructions | `EXPLORATORY_HANDOFF_ONLY` | Summarised in handoff §7 (V2.0 NRT educational granule) |
| Level 1 — Observation (`Q01`–`Q03`: CIE colour, OWTs, AlphaEarth clustering/analogues) | `PLANNED` | Next active queue starts with `Q01` and `Q02` |
| Level 2 — Quantification (`Q04`–`Q06`: PARDIG rainfall, PACE products, Granite Ocean) | `PLANNED` | Verify PARDIG access and native Sentinel-3 Granite interface before execution |
| Level 3 — Integration (`Q07`–`Q09`: plume lags, `GLORIA-Context` ablations, OWT embeddings) | `PLANNED` | Requires pre-registered cohorts and waterbody/study/temporal holdouts |
| Level 4 — Thailand applications (`Q10`–`Q13`: Gulf plumes, Songkhla, blooms, drifter design) | `PLANNED` | Longer-term case studies; field deployment is proposed only |

## Seven Things This Repository Refuses to Conflate

| Not the same as | |
| --- | --- |
| bulk chlorophyll or colour index | microbial diversity or taxonomic composition |
| satellite-derived model product (e.g., PACE Chla, IOPs, MOANA) | independent in situ field ground truth |
| optical water type or unsupervised embedding cluster | biological community class or causal regime |
| 1 nm interpolated wavelength grid | 1 nm native spectrometer optical resolution |
| environmental proxy correlation (lat/lon, photoperiod, SST) | direct optical detection of organisms |
| random K-fold cross-validation score | waterbody-, dataset-, or temporally held-out generalisation |
| masked-pixel or multispectral-to-hyperspectral reconstruction | measured hyperspectral water-leaving reflectance |

## Quickstart (`uv`)

```bash
uv sync
PYTHONIOENCODING=utf-8 uv run pytest -q
PYTHONIOENCODING=utf-8 uv run python tools/check_conflict_markers.py --self-test
PYTHONIOENCODING=utf-8 uv run python tools/check_declared_encoding.py --self-test
PYTHONIOENCODING=utf-8 uv run python tools/check_repo_hygiene.py --self-test
```

Copy [`config/local_paths.example.yaml`](config/local_paths.example.yaml) to `config/local_paths.yaml` (gitignored) to point local notebooks and scripts at external archives staged outside Git.

## Structure

```text
AGENTS.md                 Epistemic, radiometric, validation, staging, and review rules
CITATION.cff              Citation metadata for software and retained packages
LICENSE                   MIT License (code, scripts, and tests)
LICENSE-DOCS.md           CC BY 4.0 License (documentation, protocols, and original figures)
pyproject.toml / uv.lock  Python >= 3.11 package metadata and locked dependencies
.claude/skills/           Checklists for experiment review and scientific evidence audit
.github/workflows/ci.yml  Automated repository guards, self-tests, and pytest checks
config/                   Committed QC thresholds + local_paths.example.yaml template
manifests/ & schemas/     External dataset provenance manifests and JSON Schema
docs/                     Handoff roadmap, reference access ledger, lanes policy, decisions
pre-registrations/        Dated confirmatory protocols (append-only deviations)
notebooks/                Reproducible CPU-first curriculum (Q01-Q13) notebooks
src/hydrospectral/        Importable, tested Python core
tools/                    Self-testing repository hygiene and encoding guards
results/                  Compact retained benchmark outputs and deterministic manifests
tests/                    Analytical, boundary, schema, and planted-defect tests
data/                     Local data staging notes (raw binaries gitignored)
```

## License

| Scope | License | Details |
| --- | --- | --- |
| Source code (`src/`, `tests/`, `tools/`, scripts, notebook code cells) | MIT License | [LICENSE](LICENSE) |
| Documentation, protocols, notes, and original figures (`docs/`, `pre-registrations/`, `results/`, prose) | CC BY 4.0 | [LICENSE-DOCS.md](LICENSE-DOCS.md) |
| External datasets, satellite granules, and cited literature | Upstream licenses | Not redistributed in Git; see [manifests/README.md](manifests/README.md) and [docs/references-access.md](docs/references-access.md) |
