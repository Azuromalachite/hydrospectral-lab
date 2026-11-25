# Source Package (`src/hydrospectral/`)

Importable, tested Python core for `hydrospectral-lab`. Keep one-off exploration in off-repo scratch or `notebooks/` until a calculation, schema check, or splitter is needed across at least two analyses, and never add empty stub modules (`docs/decisions.md` D-005).

Current modules:
- `hydrospectral.thresholds` — loads committed radiometric and QC parameters from [`config/qc_thresholds.yaml`](../config/qc_thresholds.yaml) without silent fallback defaults.
- `hydrospectral.manifests` — validates external dataset manifests in [`manifests/sources/`](../manifests/README.md) against [`schemas/source_manifest.schema.json`](../schemas/source_manifest.schema.json) and rejects `example: true` template records as active evidence.
- `hydrospectral.provenance` — computes file SHA-256 digests, enforces `CohortCounts` denominator accounting, and writes byte-deterministic `manifest.json` files without wall-clock timestamps.
- `hydrospectral.radiometry` — above-water $L_w$ and $R_{rs} = L_w / E_s$ (preserving negative reflectance), AVW harmonic mean, NDI/QWIP (using published Dierssen et al. 2022 coefficients in `config/qc_thresholds.yaml`), band ratios, unit-$L_2$/SNV/derivatives, and Spectral Angle Mapper (SAM).
- `hydrospectral.color` — official ISO/CIE 11664-1 1931 2° XYZ tristimulus integration (`colour-science`), chromaticity $(x, y)$, van der Woerd & Wernand (2015) hue angle, Bradford-adapted display sRGB, and magnitude-preserving SAM optical water type classification.
- `hydrospectral.pace` — NASA PACE OCI Level-2 AOP HDF5/NetCDF4 (`h5py`) reader, CF-1.8 packed variable unpacking (preserving negative $R_{rs}$), unsigned 32-bit `l2_flags` decoding, RGB/false-colour composites, and CPU Gram/SVD swath PCA.
- `hydrospectral.srf` — loads measured sensor SRF CSVs, refuses nonzero out-of-range support, and performs trapezoidal reflectance-only or Burggraaff (2020) irradiance-weighted band convolution.
- `hydrospectral.geometry` — computes conservative single-pixel and $k\times k$ footprint screening widths and projected water-mask Euclidean distance-transform eligibility (`HS-R03`).
- `hydrospectral.gloria` — `GLORIA_ID` one-to-one zip/directory loader, QC-flag untested-vs-passed summary, negative-$R_{rs}$ diagnostics, and optically derived Chla circularity isolation.
- `hydrospectral.splits` — leakage-free `GroupKFold` (`Site`, `Dataset_ID`), causal temporal holdouts, pooled/equal-group regression metrics, whole-group paired cluster bootstrap CIs, and SAM nearest-neighbour OOD diagnostics.
