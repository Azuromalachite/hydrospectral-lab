# Source Package (`src/hydrospectral/`)

Importable, tested Python core for `hydrospectral-lab`. Keep one-off exploration in off-repo scratch or `notebooks/` until a calculation, schema check, or splitter is needed across at least two analyses, and never add empty stub modules (`docs/decisions.md` D-005).

Current modules:
- `hydrospectral.thresholds` — loads committed radiometric and QC parameters from [`config/qc_thresholds.yaml`](../config/qc_thresholds.yaml) without silent fallback defaults.
- `hydrospectral.manifests` — validates external dataset manifests in [`manifests/sources/`](../manifests/README.md) against [`schemas/source_manifest.schema.json`](../schemas/source_manifest.schema.json) and rejects `example: true` template records as active evidence.
