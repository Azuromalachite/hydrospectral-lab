# Source & Artifact Manifests (`manifests/`)

Large external archives, satellite granules, and intermediate arrays stay out of Git and are tracked here by compact, diffable YAML manifests validated against [`schemas/source_manifest.schema.json`](../schemas/source_manifest.schema.json).

## `sources/` — one record per external dataset

Three fields carry specific epistemic discipline:

1. **`version_string`** records *what the file or archive metadata declares about itself* (e.g., `V2_0.NRT`), never a guess inferred from a folder name. Use `not declared` when absent and document why in `notes`.
2. **`digest_verified`** stays `false` until the SHA-256 digest is recomputed against actual bytes staged on disk for this checkout. A hash carried over from a handoff note or provider page is a recorded expectation, not a local verification.
3. **`notes`** is mandatory and records known hazards the file does **not** declare about itself (sampling skews, NRT vs. science processing, optical target circularity, unmeasured QC columns).

Machine-specific filesystem paths never appear in `manifests/sources/*.yaml`; each manifest references a `local_path_key` (`datasets.<name>`) configured locally in gitignored `config/local_paths.yaml` (see [`config/local_paths.example.yaml`](../config/local_paths.example.yaml)).

## Worked example rejection

[`sources/example-source.yaml`](sources/example-source.yaml) carries `example: true`. It passes JSON Schema validation to keep the template honest, and `hydrospectral.manifests` + `tools/check_repo_hygiene.py` explicitly **refuse** any `example: true` record when loading active evidence sources.
