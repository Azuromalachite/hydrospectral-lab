# Reference Access & Reading Status

Snapshot: **25 November 2026**. A public landing page, a bibliographic export, a downloaded PDF, and a read full text are distinct states. HTTP 403 or API pagination failure records a retrieval barrier, not proof that a work is paywalled or absent.

Third-party publisher PDFs are held privately outside the repository and are never committed to Git.

## Reading-status levels

- **`discovered`** — identified via citation index, search, or bibliography; text not yet inspected.
- **`metadata/abstract read`** — title, abstract, and bibliographic record checked; body text and methods unverified.
- **`relevant passages read`** — named sections, tables, or figures read directly; full-paper verification not claimed.
- **`full work read`** — complete text read directly.
- **`independently verified`** — claims, equations, or numerical tables independently recomputed or cross-checked against raw data/code.

## Core local references (held privately, not in Git)

| Work | Identifier | Local file (gitignored) | Status at handoff | Notes & remaining checks |
| --- | --- | --- | --- | --- |
| Lehmann et al. (2023), GLORIA data descriptor | [10.1038/s41597-023-01973-y](https://doi.org/10.1038/s41597-023-01973-y) | `s41597-023-01973-y.pdf` | `full work read` (key figures/tables audited against `GLORIA-2022.zip`) | Real-archive audit completed (2026-11-26): CSV has 30 distinct non-null ISO-3166 `Country`/`Country_code` labels (`France`/`FR` subsumes 254 South American rows at `Site_name='Guiana'`, plausibly accounting for the paper's 31-country count); Lake Geneva optically derived Chla pinned from `GLORIA_variables_and_methods.xlsx` as `Dataset_ID='OdermattD_CH_Eawag'` (`Chl_method='Eawag Chl - aLH'`, n=290) in `config/qc_thresholds.yaml`. |
| Hong et al. (2026), Hyperspectral imaging primer | [10.1038/s43586-026-00470-x](https://doi.org/10.1038/s43586-026-00470-x) | `s43586-026-00470-x.pdf` | `relevant passages read` (Figs. 2, 4, 5; Table 3) | Used as pedagogical structure for preprocessing, dimensionality reduction, and unmixing cautions. |
| Kaneko et al. (2023), Eukaryotic plankton from satellite data | [10.1038/s43705-023-00308-7](https://doi.org/10.1038/s43705-023-00308-7) | `43705_2023_article_308.pdf` | `relevant passages read` (Table 1, sample filtering, spatial buffering) | Code/archive links recorded; full computational reproduction (`HS-R04`) not yet executed. |
| Dierssen et al. (2022), QWIP v1.1 | [10.3389/frsen.2022.869611](https://doi.org/10.3389/frsen.2022.869611) / [Zenodo 7373840](https://doi.org/10.5281/zenodo.7373840) | Public open access | `relevant passages read` (QWIP v1.1 coefficients cross-checked against `GLORIA_qc_ancillary.csv` & `GLORIA_qc_flags.csv`) | Coefficients pinned in `config/qc_thresholds.yaml`; cross-check on real `GLORIA-2022.zip` matches `Apparent_visible_wavelength` to 0.000000 nm (n=7,487) and `QWIP_fail` on 7,397/7,397 (100.0%, median |delta QWIP| = 0.000124). Full Zenodo R/Python archive reproduction (`OPT-06`) remains planned. |
| van der Woerd & Wernand (2015), True Colour Classification of Natural Waters | [10.3390/s151025663](https://doi.org/10.3390/s151025663) | Public open access | `relevant passages read` (CIE chromaticity white point `(1/3, 1/3)` and `atan2` hue-angle convention) | Implemented in `hydrospectral.color.chromaticity_to_hue_angle_deg`; sensor-specific polynomial $\Delta$ corrections for multispectral bands not yet implemented. |

## Open access gaps & verification queue from handoff

| Item / Study | Identifier / Source | Current status | Gap to resolve |
| --- | --- | --- | --- |
| Kaneko (2023) forward citations (`kaneko2023_citing_works.csv`) | 24-record bibliographic export (9 in 2024, 6 in 2025, 9 in 2026 incl. 6 preprints & paratext) | `discovered` / `metadata/abstract read` | Export is a bibliographic snapshot, not 24 read peer-reviewed papers; inspect priority full texts individually before citing specific methods or numbers. |
| GLORIA forward citation graph | Article DOI `10.1038/s41597-023-01973-y` + Dataset DOI `10.1594/PANGAEA.948492` | Partial (`discovered` / `relevant passages read` on selected works) | Earlier exhaustive API retrieval failed (publisher count 167 vs OpenAlex 143); run deduplicated union query across both DOIs when auditing literature coverage. |
| Benchmarking Hyperspectral Transfer and Graph Learning with PACE OCI (2026) | [10.1109/JSTARS.2026.3726801](https://doi.org/10.1109/JSTARS.2026.3726801) | `metadata/abstract read` | Full text and validation protocol were inaccessible during handoff review; obtain and audit full text before adopting its KNN/graph transfer setup. |
| Hyperspectral inversion framework (2023) | [10.1016/j.rse.2023.113706](https://doi.org/10.1016/j.rse.2023.113706) / [NASA NTRS manuscript](https://ntrs.nasa.gov/api/citations/20240007762/downloads/Hyperspectral_inversion_framework3.pdf) | `metadata/abstract read` | Confirm open access to the extended phycocyanin/absorption dataset before planning `OPT-21` / `OPT-23` around it. |
| Balasubramanian et al. (2025), Historical ocean-colour MDNs | [10.3389/frsen.2025.1488565](https://doi.org/10.3389/frsen.2025.1488565) | `metadata/abstract read` | Single public archive access for the 9,956-observation augmented dataset is not yet established. |
| AquaCorr-Global matchup dataset | `zenodo.org/records/21927415` (from earlier search) | `discovered` (unverified) | Verify Zenodo record existence, schema, and license before relying on it. |
| PARDIG (2026) | [arXiv:2611.13941](https://arxiv.org/abs/2611.13941) / WeatherNext docs | `metadata/abstract read` | Verify public release endpoints, units, temporal coverage, and whether native Earth Engine ingestion exists before `Q04`. |
| Granite-Geospatial-Ocean (2025) | [arXiv:2509.21273](https://arxiv.org/abs/2509.21273) / [Hugging Face](https://huggingface.co/ibm-granite/granite-geospatial-ocean) | `metadata/abstract read` | Verify exact released Sentinel-3 checkpoint bands, patch dimensions, and whether masked-reconstruction decoder weights are exposed before `Q06`. |
