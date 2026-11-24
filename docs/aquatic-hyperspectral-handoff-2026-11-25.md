# Aquatic hyperspectral research: from field spectra to Earth observation and microbial ecology

**Research handoff and educational roadmap**  
**Snapshot:** 25 November 2026 (KST)  
**Scope:** The hyperspectral portion of the Loy Krathong / recoverable scientific drifter discussion, beginning with the question of what microbial dynamics can be observed from space and ending with the five-technology priority portfolio and thirteen educational questions.

This document consolidates the thread into a reusable research record, rather than reproducing the chat verbatim. It retains the scientific rationale, literature, experiments, numerical findings, files, unresolved issues and proposed curriculum. The retained GLORIA benchmark metrics and artifact names were checked against the local files when assembling this handoff. Other previously reported results are identified as such; the experiments and literature searches were not rerun for this compilation. A proposed experiment is not an established finding.

## 0. Executive synthesis

The central research question is:

> To what extent can the optical phenotype of an aquatic ecosystem, together with environmental context and hydrological connectivity, reveal its underlying microbial organisation and dynamics?

The project grew out of a proposal to turn Loy Krathong into an annual coordinated citizen-science campaign using reusable, recoverable drifting instruments. The immediate aim is now **to learn aquatic hyperspectral analysis**, not to build hardware or train a large model prematurely.

The research stack has three complementary observational scales:

- **Field spectroscopy and laboratory ground truth:** GLORIA and related datasets teach us how measured spectra relate to water properties.
- **Satellite observations and Earth-science AI:** PACE, AlphaEarth, PARDIG and Granite-Geospatial-Ocean allow us to examine spatial patterns, environmental context, temporal forcing and learned representations.
- **Future field campaigns:** recoverable drifters, calibrated radiometry and molecular measurements would supply local observations that remote sensing cannot directly provide.

The five technologies selected as the current highest-priority portfolio are **AlphaEarth Foundations, Google Earth Engine, PARDIG, Granite-Geospatial-Ocean and NASA PACE derived products**. GLORIA is the reference dataset underpinning the learning programme, not an additional technology priority.

The key intellectual progression is:

**Radiometry → spectral quality → colour science → optical water types → measurement uncertainty → bio-optical inversion → geographical and temporal context → microbial ecology.**

The central caution is that predicting chlorophyll or reconstructing a visually convincing image is not equivalent to measuring microbial diversity, inferring taxonomic composition or establishing ecological causation.

## 1. Scientific motivation: what can be observed from space?

Aquatic remote sensing relies on the wavelength-dependent absorption and scattering of light. Photosynthetic microorganisms are substantially more accessible to optical observation than heterotrophic microbes.

| Phenomenon | Observable or proxy | Feasibility / limitation |
|---|---|---|
| Phytoplankton blooms | Chlorophyll and accessory pigments | Established under suitable optical conditions |
| Cyanobacterial blooms | Phycocyanin, chlorophyll-a, red-edge features | Established in favourable environments; not uniquely diagnostic in every waterbody |
| Photosynthetic functional groups | Differences in pigment composition and spectral shape | Model-based, emerging to established depending on group and setting |
| Surface microbial mats | Pigments, surface reflectance | Possible for sufficiently extensive exposed or near-surface patches |
| Anoxygenic phototrophs | Bacteriochlorophylls and carotenoids | Experimental; NIR attenuation in water makes this difficult |
| Microbial decomposition | CDOM and other optical proxies | Indirect, not specific to microbial activity |
| Heterotrophic bacteria and archaea | Covariance with environmental or optical variables | Statistical prediction; no routine direct taxonomic detection |
| Hypoxia and ecosystem metabolism | Associated changes in pigments, organic matter, environmental forcing | Indirect; requires oxygen and other in situ measurements |
| Functional genes, plasmids and viruses | No generally distinctive optical signal | Not directly observable from orbit |

Characteristic spectral regions to learn (approximate, not isolated molecular signatures):

| Wavelength | Interpretation |
|---|---|
| 400–450 nm | CDOM absorption, pigment absorption and scattering |
| ~440 nm | Chlorophyll-a blue absorption region |
| ~550–570 nm | Green reflectance maximum in many productive waters |
| ~555 nm | Phycoerythrin absorption region (pigment dependent) |
| ~620 nm | Phycocyanin absorption region |
| ~665–680 nm | Chlorophyll-a red absorption |
| ~685 nm | Potential chlorophyll fluorescence contribution |
| ~700–710 nm | Red-edge feature in productive waters |
| 750–900 nm | Strong water absorption, residual scattering and correction artefacts |
| ~805–870 nm | Some bacteriochlorophyll-a absorption bands; highly conditional detectability |

A spectrum is a mixture of these effects, not a barcode that assigns individual peaks unambiguously to organisms. Water-leaving reflectance is also not equivalent to a purified pigment absorption spectrum.

A particularly interesting future hypothesis is whether observable phytoplankton bloom dynamics can help predict the succession of associated heterotrophic microbes. Testing it requires time-matched molecular data, appropriate physicochemical covariates and independent validation; the existing GLORIA and PACE files alone cannot answer it.

### 1.1. From floating objects to environmental processes

Drifters can provide transport trajectories, retention, dispersion, recirculation and hydrological connectivity. With chemical and molecular sampling, they can help investigate environmental changes along transport pathways. GPS-only trajectories do not necessarily represent water parcels exactly; windage, buoy geometry, tides and trapping matter.

The relevant Thai precedents discussed before the hyperspectral work were:

- Mani et al. (2023), Chao Phraya floating macroplastic transport and retention: [DOI](https://doi.org/10.1016/j.envpol.2023.121124). Five GPS drifters; substantial trapping and remobilisation.
- *The tidal trap* (2025), seasonal transport in the bidirectional Chao Phraya network: [DOI](https://doi.org/10.1016/j.marpolbul.2025.117605). The thread reported that only one of 63 drifters reached the sea during observation; this is not a universal probability of waste reaching the ocean.
- Richter et al. (2022), [Genomic evidence for global ocean plankton biogeography shaped by large-scale current systems](https://doi.org/10.7554/eLife.78129), connects microbial biogeography to circulation.

A future scientific campaign should emphasise recovery of instruments, calibrated sensing and coordinated observations rather than make biodegradation a prerequisite for early engineering. Optical satellite observations are normally daytime observations, whereas Loy Krathong is a night festival. Daytime overpass matchups and evening deployments would need to be planned separately.

## 2. The literature connecting satellites to microbial communities

### 2.1. Kaneko et al. (2023): a key starting point

[Predicting global distributions of eukaryotic plankton communities from satellite data](https://doi.org/10.1038/s43705-023-00308-7), *ISME Communications*. Local paper: `43705_2023_article_308.pdf`.

The study predicts six DNA-defined community types using 18S V4 metabarcoding, community network analysis and satellite-derived predictors. It uses MODIS reflectance bands rather than modern PACE hyperspectral data.

Reported Table 1 results (classification accuracy, percent):

| Predictor set | Leave-one-out | Spatially buffered validation (2,000 km exclusion) |
|---|---:|---:|
| All 17 satellite parameters | 67 | 54 |
| Latitude and longitude | 68 | 29 |
| Seven environmental parameters | 58 | 50 |
| Temperature + chlorophyll-a | 52 | 47 |
| Chlorophyll-a | 43 | 23 |
| Temperature | 40 | 28 |

Adding ten reflectance bands to environmental variables produced a modest improvement in buffered accuracy (50% to 54%); the reported micro-average ROC-AUC was 0.83 in both cases. Geographical predictors alone looked impressive under ordinary validation but failed to transfer well. The usable dataset shrank from 15,562 EukBank samples through multiple selection and matching steps to 177 analysis samples. This highlights the value of coordinated molecular–optical matchups.

Resources: [analysis repository](https://github.com/hirotokaneko/plankton-from-satellite), [GenomeNet archive](https://www.genome.jp/ftp/db/community/tara/Satellite/), [PRJEB6610](https://www.ebi.ac.uk/ena/browser/view/PRJEB6610), [PRJEB9737](https://www.ebi.ac.uk/ena/browser/view/PRJEB9737).

### 2.2. Foundational studies and methodological ancestry

| Reference | Contribution |
|---|---|
| [Alvain et al., 2005](https://doi.org/10.1016/j.dsr.2005.06.015); [2008](https://doi.org/10.1029/2007GB003036) | PHYSAT; phytoplankton group classification and seasonal succession |
| [Bracher et al., 2009](https://doi.org/10.5194/bg-6-751-2009); [Sadeghi et al., 2012](https://doi.org/10.5194/os-8-1055-2012) | PhytoDOAS and hyperspectral pigment-group retrieval |
| [Mouw et al., 2017](https://doi.org/10.3389/fmars.2017.00041); [Bracher et al., 2017](https://doi.org/10.3389/fmars.2017.00055) | Phytoplankton remote-sensing approaches and roadmap |
| [Larsen et al., 2012](https://doi.org/10.1038/nmeth.1975) | Predict bacterial assemblages using environmental parameters and associations |
| [Faust & Raes, 2012](https://doi.org/10.1038/nrmicro2832) | Microbial networks and models |
| [Ibarbalz et al., 2019](https://doi.org/10.1016/j.cell.2019.10.008) | Global plankton diversity across kingdoms |
| [Logares et al., 2020](https://doi.org/10.1186/s40168-020-00827-8) | Microbial community assembly and dispersal |
| [Chaffron et al., 2021](https://doi.org/10.1126/sciadv.abg1921) | Global plankton interactome and environmental niche modelling |
| [Richter et al., 2022](https://doi.org/10.7554/eLife.78129); [Frémont et al., 2022](https://doi.org/10.1038/s41558-022-01339-y) | Ocean transport and future microbial biogeography |
| [Endo et al., 2020](https://doi.org/10.1038/s41559-020-01288-w); [Prodinger et al., 2021](https://doi.org/10.1093/femsec/fiab167) | Giant viruses and cross-domain seasonal dynamics |
| [Gloor et al., 2017](https://doi.org/10.3389/fmicb.2017.02224); [Roberts et al., 2017](https://doi.org/10.1111/ecog.02881) | Compositionality and spatial/temporal validation |
| [Mahé et al., 2022](https://doi.org/10.1093/bioinformatics/btab493); [Tackmann et al., 2019](https://doi.org/10.1016/j.cels.2019.08.002); [Traag et al., 2019](https://doi.org/10.1038/s41598-019-41695-z) | Swarm v3, FlashWeave, Leiden community detection |
| [Werdell et al., 2019](https://doi.org/10.1175/BAMS-D-18-0056.1) | PACE mission scientific rationale |

### 2.3. Forward citations and related developments

The supplied `kaneko2023_citing_works.csv` contains 24 indexed records (2024: 9, 2025: 6, 2026: 9), including six 2026 preprints, dissertations and a paratext entry. This is a bibliographic snapshot, not 24 independently verified peer-reviewed studies. Earlier searches located fewer records. The CSV is the preferred complete record of that export.

| Priority | Work | Relevance |
|---|---|---|
| High | [El Hourany et al., 2024](https://doi.org/10.5194/os-20-217-2024), Linking satellites to genes | Parallel research using `psbO` metagenomic marker to infer seven photosynthetic groups; 145 Tara stations; cites Kaneko but initially submitted before its publication |
| High | [Kramer et al., 2024](https://doi.org/10.1364/OE.529906), Phytoplankton communities quantified from hyperspectral ocean reflectance correspond to pigment-based communities | Matched reflectance and HPLC pigments; fine spectral features; [code](https://github.com/sashajane19/Rrs_pigments) |
| High | [Hyperspectral ocean color encodes global eukaryotic phytoplankton community structure](https://doi.org/10.64898/2026.09.09.750502), 2026 preprint | Direct relationship between hyperspectral reflectance and community structure |
| High | [Inferring plankton biodiversity combining meta-omics and pigment data](https://doi.org/10.2139/ssrn.7624673), 2026 preprint | 19 photosynthetic groups, markers/MAGs; ecosystem transferability concerns |
| High | [Satellite-gene abundance fusion reveals global hotspots of ocean ecosystem services](https://doi.org/10.64898/2026.09.23.753815), 2026 preprint | Functional diversity, productivity and carbon export |
| Medium | [From objective discovery to prediction of global ocean eco-provinces](https://arxiv.org/abs/2609.13206), 2026 preprint | Interpretable ecological provinces |

`psbO` is generally a single-copy photosystem II marker, useful as a relative cell-abundance proxy, but a large diatom and a tiny cyanobacterium can contribute similar copy counts while having very different optical contributions.

Closely related literature (not all confirmed as direct Kaneko citations):

- [Marchese et al., May 2026](https://doi.org/10.1016/j.ecoinf.2026.103747): prokaryotic Shannon diversity prediction in the Mediterranean from ~600 samples, remote sensing and oceanographic data. Reported test R² 0.70; photoperiod ~42% SHAP importance. This is an environmental proxy, not direct detection. Assembled dataset reportedly available on request; public sources include [PRJEB60871](https://www.ebi.ac.uk/ena/browser/view/PRJEB60871), [PRJNA380761](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA380761) and [processing code](https://doi.org/10.5281/zenodo.12801913).
- [Marchese et al., July 2026](https://doi.org/10.3389/fmars.2026.1875929): eukaryotic Shannon-diversity prediction, R² falling from 0.44 (ordinary K-fold) to 0.09 (leave-one-dataset-out). This reinforces the danger of unevenly structured data.
- [The marine microbiome can accurately predict its chemical and biological environment (2026)](https://doi.org/10.1038/s43247-026-03715-5): reverse prediction from 16S/18S composition to environmental variables, 397 samples from 18 stations.
- [PETRI-MED consortium](https://www.spaceclimateobservatory.org/petri-med): integrates Earth observation, omics, physical and biogeochemical modelling in the Mediterranean.

Potential extensions: reproduce Kaneko and Larsen; test whether spectra improve prediction beyond environmental variables; integrate transport; assess functional genes and tropical freshwater transfer. All require independent spatial, temporal and study-level validation.

## 3. The original HS-R research programme

| ID | Question | Priority / status |
|---|---|---|
| HS-R01 | Which water-quality variables can reliably be inferred from hyperspectral reflectance? | P0; exploratory GLORIA benchmark completed |
| HS-R02 | How much information is lost when hyperspectral measurements are reduced to Sentinel-2 bands? | P0; approximate six-band benchmark completed, true SRF simulation pending |
| HS-R03 | Which Thai waterways are sufficiently wide for reliable satellite observations? | P0; literature and geometric screening only |
| HS-R04 | Reproduce satellite-based phytoplankton community predictions using Tara Oceans | P1; proposed |
| HS-R05 | Do spectra improve heterotrophic community prediction beyond environmental covariates? | P1; proposed |
| HS-R06 | How many field/drifter observations improve local retrieval algorithms? | P1; proposed |
| HS-R07 | Does hydrological connectivity improve microbial prediction? | P1; proposed |
| HS-R08 | Can repeated campaigns reveal bloom-associated microbial succession? | P2; proposed |

### 3.1. Thai remote-sensing context

Literature identified in the earlier search:

- [Remote sensing of tropical riverine water quality using Sentinel-2 (2022)](https://doi.org/10.1016/j.ecolind.2022.109472): 65 images, six stations, ~130 km of Chao Phraya; locally calibrated Chla, turbidity and transparency retrievals, weaker CDOM.
- [Water turbidity determination in the Chao Phraya (2022)](https://doi.org/10.32526/ennrj/20/202100237): study sites reported as 200–500 m wide.
- [Tropical chlorophyll algorithms (2026)](https://doi.org/10.52939/ijg.v22i3.4873): local model reported R² 0.73 and RMSE 39.19 µg/L.
- [Nitrogen and phosphorus dynamics (2026)](https://doi.org/10.3390/environments13010057): 264 samples across 50 Thai waterbodies; cross-validated R² 0.63 for TN and 0.69 for TP; April–May sampling and ±3-day satellite matchups limit transfer claims.
- [PRISMA tropical urban reservoir cyanobacteria mapping (2023)](https://www.sciencedirect.com/science/article/pii/S0924271623002617): hyperspectral freshwater precedent.
- Thai molecular ecology: [upper Gulf 16S (2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6979385/), [Gulf coast bacterial communities (2024)](https://pubmed.ncbi.nlm.nih.gov/38868067/), [Arcobacter in Bangkok waterways (2021)](https://pubmed.ncbi.nlm.nih.gov/34371501/), [tropical river sediment microbiology (2016)](https://pubmed.ncbi.nlm.nih.gov/27671140/). Temporal/spatial compatibility with optical data is untested.

Geometric screening: for a square pixel of width p and an illustrative bank buffer b on either side, use W_min = sqrt(2)p + 2b for a centred pixel, or 3sqrt(2)p + 2b for a centred 3×3 neighbourhood. With b = 20 m:

| Sensor | Pixel size | Single-pixel screening width | 3×3 screening width |
|---|---:|---:|---:|
| Sentinel-2 visible | 10 m | 54 m | 82 m |
| Sentinel-2 red edge | 20 m | 68 m | 125 m |
| EnMAP / PRISMA | 30 m | 82 m | 167 m |
| Sentinel-3 OLCI | 300 m | 464 m | 1,313 m |
| PACE OCI | ~1,200 m | 1,737 m | 5,131 m |

These thresholds are conservative footprint geometry for an idealised centred square, not validated minimum widths or guarantees of a usable pixel. Atmospheric adjacency, alignment, point-spread function, clouds, shallow water, glint and bank contamination matter.

Candidate sites: lower Chao Phraya, Tha Chin, Bang Pakong, Mekong, Songkhla Lake, Ubol Ratana Reservoir and upper Gulf of Thailand. Only the Chao Phraya example has the documented width range cited above; no nationwide GIS audit has been completed. Use [GRWL](https://zenodo.org/records/1297434), [JRC Global Surface Water](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater), and [Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1) to estimate contiguous water area and distance from land, then audit actual satellite coverage.

## 4. GLORIA: dataset, physical interpretation and actual analysis

### 4.1. Source and structure

**Lehmann et al. (2023). [GLORIA — A globally representative hyperspectral in situ dataset for optical sensing of water quality](https://doi.org/10.1038/s41597-023-01973-y).** *Scientific Data* 10:100. [Dataset DOI](https://doi.org/10.1594/PANGAEA.948492), CC BY 4.0. Local paper `s41597-023-01973-y.pdf`; archive `GLORIA-2022.zip`.

GLORIA is a spectral library, not a hyperspectral image cube. Each observation has a measured Rrs spectrum and at least one matched core water-quality attribute; observations are discrete in space and time. It contains 7,572 spectra, 551 interpolated wavelengths (350–900 nm at 1 nm spacing), ~450 water bodies and contributions from researchers affiliated with 59 institutions. The original paper reports 31 countries; our CSV audit found 30 country labels, a discrepancy still to reconcile. There are 54 contributing dataset IDs and 496 country/site labels in the retained audit; these labels are not unique physical water bodies.

| File in archive | Role |
|---|---|
| `GLORIA_Rrs.csv` | Remote sensing reflectance (sr⁻¹) |
| `GLORIA_Es.csv` | Above-water downwelling irradiance |
| `GLORIA_Lw.csv` | Water-leaving radiance just above surface |
| `GLORIA_Lt.csv` | Total above-water upwelling radiance |
| `GLORIA_Lsky.csv` | Sky radiance |
| `GLORIA_Lu.csv` | Upwelling radiance just below surface |
| `GLORIA_Rrs_mean.csv`, `GLORIA_Rrs_std.csv` | Replicate statistics for subset |
| `GLORIA_qc_flags.csv`, `GLORIA_qc_ancillary.csv` | Individual flags and diagnostic metrics |
| `GLORIA_meta_and_lab.csv` | Coordinates, time, instrument/method, environmental measurements |
| `GLORIA_variables_and_methods.xlsx` | Data dictionary and original measurement-method descriptions |
| `GLORIA_waterqual_uncert` | Replicate laboratory/field measurement uncertainty where available |

Join on `GLORIA_ID`, not on row position. The original Colab notebook stopped at a deliberately unfilled metadata-mapping assertion. Correct mapping: ID `GLORIA_ID` in both tables, site grouping `Country` + `Site_name`, target columns `Chla`, `TSS`, `aCDOM440`, `Secchi_depth`, `Turbidity`.

### 4.2. Computed data audit (from supplied archive)

| Waterbody type | Observations |
|---|---:|
| Lake | 4,510 |
| Coastal ocean | 2,426 |
| Estuary | 311 |
| River | 249 |
| Other | 76 |

Rivers comprise only 3.3% of GLORIA. The earlier audit identified 270 Vietnamese observations (181 coastal, 49 lake, 40 river), one Malaysian observation and none from Thailand. The 40 Vietnamese river observations are from the Red River and are useful as a candidate regional transfer test, not a substitute for Thai validation.

| Target | Available | Positive and unflagged, complete 400–800 nm | Contributing datasets in usable cohort | River samples in cohort |
|---|---:|---:|---:|---:|
| Chlorophyll-a | 5,132 | 2,840 | 34 | 38 |
| TSS | 4,623 | 3,038 | 32 | 193 |
| CDOM absorption at 440 nm | 4,393 | 2,709 | 31 | 162 |
| Secchi depth | 3,948 | 2,513 | 28 | 204 |
| Turbidity | 1,252 | 894 | 8 | 1 |

Units: Chla µg/L (equivalent to mg/m³), TSS mg/L (g/m³), CDOM m⁻¹, Secchi m, turbidity NTU (confirm method and units when combining measurements). The earlier audit reported medians of 7.99, 9.73, 0.549, 1.15 and 8.52 respectively among available observations. Uncorrected chlorophyll plus phaeopigments has a separate column; do not silently merge it with corrected Chla.

QC counts: 5,793 unflagged; 1,779 with at least one flag (including 226 suspect spectra). Complete 400–800 nm: 6,208; unflagged and complete: 4,528. At least one negative Rrs in this interval: 637 observations (all spectra in audit). The original flags may be missing where a wavelength range was not measured; unflagged is not synonymous with every test passed. Earlier instrument metadata audit: 6,270 observations with resolution values, median 4.9 nm, range 1–10 nm. Interpolation onto a 1 nm grid does not confer 1 nm instrument resolution.

### 4.3. Completed baseline experiments

The retained `GLORIA_benchmark_results.zip` includes code, predictions, metrics, plots and a manifest. The benchmark used positive targets, unflagged complete spectra; five-fold cross-validation; 81 hyperspectral features at 5 nm intervals (400–800 nm) and six approximate rectangular bandpasses (centres/widths in nm: 490/65, 560/35, 665/30, 705/15, 740/15, 783/20). These are not official Sentinel-2 response functions. Ridge, Extra Trees and training median baselines were included. Metrics are pooled out-of-fold R² on log10 targets; not raw-scale accuracy.

**Extra Trees — results checked against retained metrics.csv:**

| Target | Random HS | Random six-band | Site HS | Site six-band | Dataset HS | Dataset six-band | Dataset ΔR² HS−six-band |
|---|---:|---:|---:|---:|---:|---:|---:|
| Chla | 0.8522 | 0.8217 | 0.7771 | 0.7446 | 0.7375 | 0.6974 | +0.0401 |
| TSS | 0.5684 | 0.5498 | 0.4401 | 0.4517 | 0.3341 | 0.3604 | −0.0263 |
| CDOM | 0.5899 | 0.5573 | 0.3842 | 0.3825 | 0.3714 | 0.3682 | +0.0032 |
| Secchi | 0.7022 | 0.6831 | 0.6099 | 0.6149 | 0.4565 | 0.4816 | −0.0251 |
| Turbidity | 0.8670 | 0.8636 | 0.7489 | 0.7513 | 0.7207 | 0.7323 | −0.0116 |

The major result is that generalisation degrades when whole sites and datasets are held out. Hyperspectral inputs did not universally improve bulk retrieval over six broad bands. Chlorophyll showed the largest positive difference in this particular experiment. Turbidity's good score is not a validation for rivers: the usable cohort has just one river sample. No confidence intervals, hyperparameter optimisation, native SRFs or independent Thai validation were performed. Grouping by country/site label and dataset ID is not a complete geographic or campaign-independence audit.

Prior educational analysis reported these further results on the actual archive:

- Raw covariance PCA (4,528 unflagged complete 400–800 nm spectra, 401 columns): PC1 86.84%, PC2 8.28%, PC3 3.08%; ~98.19% cumulative. Unit-norm PCA: 71.46%, 17.59%, 5.83%; ~94.88% cumulative.
- Correlation between 550 and 551 nm ~0.999986 in the chlorophyll-matched observations. Adjacent features are highly redundant; explained variance does not establish biological relevance.
- 2,840 chlorophyll-matched spectra split into quartiles of 710 each, with approximate ranges 0.051–2.17, 2.17–7.41, 7.41–23.80, and 23.80–13,296.70 µg/L. The median 705 nm feature increases strongly in the highest quartile. This is an association across different waters, not a pure pigment experiment.
- On an identical 2,813-observation positive-ratio cohort, a simple 705/665 reflectance-ratio regression yielded R² 0.679 (random) and 0.661 (dataset-held-out), versus 0.559 and 0.411 for the chosen 81-wavelength ridge model. The two-band index does not outperform every hyperspectral model; it illustrates the value of physically meaningful baselines.

The PCA, quartile and ratio findings were reported in the earlier tutorial analysis and were not recomputed during handoff preparation.

### 4.4. Hyperspectral versus multispectral: proper next benchmark

Use the same field spectrum, paired target and validation fold for each instrument configuration. Convolve with the official sensor spectral response, not simply a wavelength nearest neighbour or arbitrary rectangular window. A common first approximation is R_b = integral(Rrs(λ) S_b(λ) dλ) / integral(S_b(λ) dλ). For exact radiometric band integration, the appropriate irradiance weighting and sensor response should also be considered; see Burggraaff (2020). Compare actual native resolution, noise, wavelength coverage and atmospheric correction separately from spectral compression.

References: [Pahlevan et al., 2021](https://doi.org/10.1016/j.rse.2020.112200), [ESA Sentinel-2 documentation](https://sentiwiki.copernicus.eu/web/s2-documents), [Burggraaff, 2020](https://doi.org/10.1364/OE.391470). Hyperspectral benefits may be much greater for fine pigment structure than bulk Chla or TSS; GLORIA alone cannot test microbial composition.

## 5. What the GLORIA paper teaches beyond machine learning

The detailed reading of Lehmann et al. (2023) revised our priorities. The four figures form a natural curriculum:

| Figure (PDF page) | Content | Reproduction priority |
|---|---|---|
| Fig. 1 (3) | Water and atmospheric optical processes, radiometer geometry | Understand physical measurements |
| Fig. 2 (4) | Geographic, temporal and chemical coverage | Reproduce sampling bias and target distributions |
| Fig. 3 (7) | 13 optical water types (OWTs), type frequencies, CIE chromaticity | P0: reproduce optical classification and water-colour atlas |
| Fig. 4 (9) | Difference between archived Rrs and 3C-modelled Rrs | P1: reproduce measurement uncertainty experiment |

### 5.1. Radiometry and instrument design

Rrs(λ) = Lw(λ) / Es(λ), in sr⁻¹. In a simplified above-water arrangement, Lw ≈ Lt − ρ Lsky, with surface reflection factor ρ depending on observation geometry and conditions. More detailed approaches account for glint and wavelength-dependent contributions. Below-water upwelling radiance Lu is a different measurement and needs conversion across the interface.

The paper describes 17 field configurations (Methods, pp. 3–5), including simultaneously measured water, sky and irradiance channels; a single sensor sequentially directed at the water, sky and calibrated plaque; profiling packages; floating frames away from research vessels; and compact fibre-optic spectrometers on poles or stabilised platforms.

| Instrument | Reason to study |
|---|---|
| TriOS RAMSES, HyperOCR | Established aquatic radiometry; 256 detector channels, 10 nm spectral resolution, 3.3 nm sampling in the described configuration |
| HyperSAS | Multi-sensor above-water measurement setup |
| WISP-3 | Handheld integrated optical inputs |
| ASD FieldSpec | Portable field spectroradiometry |
| Ocean Optics USB2000/USB4000, STS-VIS | Compact spectrometers integrated into custom measurement systems |

These are precedents for future drifter radiometry, not verified recommendations for purchasing hardware. The small radiometric exercise reported in the thread reconstructed Rrs as Lw/Es for an actual GLORIA spectrum with available component measurements, agreeing to floating-point precision. It does not demonstrate that glint correction was independently accurate.

### 5.2. Optical water types, colour and spectral shape

- Spyrakos et al. (2018) OWTs classify optical spectra rather than geography or taxonomic composition. GLORIA Figure 3 shows 13 inland optical types with uneven representation.
- Distinguish waterbody class (river/lake/coast), contributor-assigned constituent dominance (algae/CDOM/sediment), empirical optical water type and unsupervised learned cluster. They are not equivalent labels.
- CIE 1931 colour-matching functions provide XYZ tristimulus values by integration over the visible spectrum. For rendering under a chosen illuminant, use illuminant-weighted Rrs and tabulated colour-matching functions, then convert XYZ to chromaticity or display RGB with explicit normalization, white point and gamut treatment. Reproduce the paper's exact conventions separately from approximate display colour. Different spectra can yield the same perceived colour (metamerism).
- Apparent visible wavelength (AVW) is the reflectance-weighted harmonic mean over 400–700 nm: AVW = ΣRrs / Σ(Rrs/λ). It is an interpretable compression of spectral shape, not simply the location of maximum reflectance. Handle incomplete bands and negative values explicitly.
- QWIP compares an observed normalized difference index from 492 and 665 nm with a fourth-order polynomial of AVW; absolute deviations greater than 0.2 were flagged in GLORIA. Use original published sign conventions and coefficients when implementing it; unusual optical spectra are not automatically invalid.

### 5.3. Quality-control findings (Table 2, p. 8)

| Flag | Cases |
|---|---:|
| Oxygen_signal (~762 nm atmospheric artefact) | 1,311 |
| QWIP_fail | 278 |
| Suspect (expert assessment) | 226 |
| Baseline_shift | 164 |
| Negative_uv_slope | 139 |
| Noisy_red | 40 |
| Noisy_blue | 15 |
| Flagged (unique, at least one issue) | 1,779 |

Flags overlap. A missing flag means the relevant wavelengths may not have been available, not that the spectrum passed. The atmospheric oxygen feature near 762 nm is not dissolved oxygen. PACE's current 719 nm upper limit precludes that particular GLORIA test.

The 3C reconstruction experiment used 1,589 spectra with Lt, Lsky, Es, time and location available, excluding those already calculated with 3C. The reported-minus-modelled median bias was of order 0.0005 sr⁻¹, green relative bias ~6.4%, and relative IQR at 560 nm 5–16%. UV/NIR relative bias was much larger; some contributing datasets showed >100% differences. Differences between datasets were larger than between method categories. This suggests a possible explanation for our held-out-dataset performance loss, but does not establish it.

### 5.4. Potential target circularity and other audit issues

Lake Geneva Thetis profiler Chla observations are a special case: the paper describes a target estimated from optical absorption line height near 676 nm and nighttime fluorescence calibration. A reflectance-to-Chla benchmark should isolate these optically inferred targets from independent lab measurements. Additional issues are different laboratory methods, phaeophytin correction, missing uncertainties, instrument heterogeneity and overlapping SeaBASS/LIMNADES entries. Use `Dataset_ID` plus method names to trace original methodology, and repository identifiers for deduplication.

### 5.5. Key references from GLORIA's own bibliography

| Ref. | Work | Role |
|---|---|---|
| 45 | [Mobley 1999](https://doi.org/10.1364/AO.38.007442) | Above-water reflectance |
| 41, 47 | [Ruddick et al. water-leaving radiance](https://doi.org/10.3390/rs11192198), [irradiance](https://doi.org/10.3390/rs11151742) | Field protocols |
| 51 | [Zolfaghari et al. 2022](https://doi.org/10.1109/TGRS.2021.3114635) | Spectral resolution and cyanobacteria |
| 53 | [Gurlin et al. 2011](https://doi.org/10.1016/j.rse.2011.08.011) | Simple NIR-red Chla retrieval |
| 56 | [Mishra et al. 2013](https://doi.org/10.1016/j.rse.2013.02.004) | Phycocyanin retrieval |
| 68 | [Binding et al. 2019](https://doi.org/10.1016/j.jglr.2018.11.015) | Lake Erie bloom composition and optics |
| 74 | [Bracher et al. 2015](https://doi.org/10.5194/os-11-139-2015) | Principal components and pigment retrieval |
| 85 | [Spyrakos et al. 2018](https://doi.org/10.1002/lno.10674) | Optical water types |
| 87 | [Lehmann et al. 2018](https://doi.org/10.3390/rs10081273) | Lake colour classification |
| 89 | [Dierssen et al. 2022](https://doi.org/10.3389/frsen.2022.869611) | QWIP |
| 90 | [Vandermeulen et al. 2020](https://doi.org/10.1016/j.rse.2020.111900) | AVW and ocean colour |
| 92 | [Groetsch et al. 2017](https://doi.org/10.1364/OE.25.00A742) | 3C spectral glint correction |
| 94 | [Burggraaff 2020](https://doi.org/10.1364/OE.391470) | Reflectance convolution biases |

Original code: [GLORIA QC R code](https://doi.org/10.5281/zenodo.7372445), [QWIP v1.1](https://doi.org/10.5281/zenodo.7373840), [3C implementation](https://gitlab.com/pgroetsch/Rrs_model_3C).

## 6. Learning hyperspectral analysis from GLORIA

The educational guide is Hong et al. (2026), [Hyperspectral imaging](https://doi.org/10.1038/s43586-026-00470-x), *Nature Reviews Methods Primers*. Local PDF: `s43586-026-00470-x.pdf`. The thread used Figure 2 (measurement stages), Figure 4 (restoration, enhancement, dimensionality reduction), Figure 5 (unmixing) and Table 3 (example imaging datasets).

The CPU-only `GLORIA_hyperspectral_tutorial.ipynb` was reported as executed against the actual archive. It teaches:

| Section | Topic | Practical outcome |
|---|---|---|
| 0 | Data structure | Join metadata, spectra and flags by ID |
| 1 | Measurement physics | Reconstruct Rrs using component radiometry |
| 2 | QC | Examine missing ranges, negative values, flags |
| 3 | Spectral interpretation | Median and IQR curves across target quartiles |
| 4 | Preprocessing | Smoothing, unit norm, derivatives |
| 5 | Dimensionality reduction | Correlation, PCA loadings and scores |
| 6 | Quantitative inversion | Compare physically motivated ratio with regressions |
| 7 | Compression/unmixing | Rectangular multispectral simulation; synthetic linear mixture recovery |

Core methods to become comfortable with: Savitzky–Golay smoothing, first/second derivative, unit-norm normalization, standard normal variate, continuum removal, PCA, minimum noise fraction (MNF, once a defensible noise covariance is available), PLS, spectral angle and band selection. Smoothing can erase narrow features; normalization removes magnitude; differentiation amplifies noise. Linear spectral unmixing is a useful mathematical exercise, but water-leaving reflectance is generally nonlinear in constituent concentrations; do not interpret unconstrained NMF components as actual microbial abundances.

GLORIA can be visualized as sample × wavelength heatmaps, CIE colour swatches, and geographic point maps. It cannot reconstruct continuous original scenes or spatial textures. To learn actual image analysis, use PACE alongside GLORIA.

## 7. PACE: the first actual hyperspectral image

### 7.1. Starter scenes

| ID | Region/date | Learning purpose | Status |
|---|---|---|---|
| PACE-01 | Gulf of Mexico, 2024-07-30 | RGB/false colour, pixel spectra, PCA, optical types | Downloaded and analysed |
| PACE-02 | Lake Erie, 2024-08-13 | Cyanobacteria and freshwater pigment features | Candidate; not downloaded |
| PACE-03 | Gulf of Thailand/Andaman Sea, 2025-12-01 | Tropical river plumes and coastal transfer | Candidate; NASA gallery observation found |
| Optional | Mid-Atlantic, 2024-10-25 | MOANA plankton-group comparison | Candidate |

Lake Erie comparison dates 2024-07-19, 2024-08-13, 2024-09-16; use [NOAA monitoring](https://www.glerl.noaa.gov/res/HABs_and_Hypoxia/) for independent reference where matched. [Gulf of Thailand NASA gallery](https://pace.oceansciences.org/gallery_more.htm?id=2331); [Mid-Atlantic NASA visualization](https://pace.oceansciences.org/data_images_more.htm?id=561). Actual granules, clouds, processing versions and available product suites must be checked for these candidates.

### 7.2. PACE-01 dataset details and processing

File: `PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc` (~148 MB decimal). [Direct tutorial download](https://github.com/opengeos/datasets/releases/download/hypercoast/PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc).

| Field | Value |
|---|---|
| Instrument | OCI (Ocean Color Instrument) |
| Acquisition | 30 July 2024, ~18:11–18:16 UTC |
| Product | Level-2 apparent optical properties, version 2.0 near-real-time |
| Geometry | Geolocated swath, not regular latitude/longitude axes |
| Rrs shape | 1,710 × 1,272 × 184 |
| Nominal pixel positions | 2,175,120 |
| Rrs channels | 184, 339–719 nm in this product |
| Metadata spatial resolution | Nominal 1 km; OCI commonly described as ~1.2 km |
| Units | sr⁻¹ |
| Gulf analysis cohort | 44,158 selected quality-screened pixels; 159 channels, 400–719 nm |

Decode packed integers, scale/offset and fill values; read geolocation and flag bit masks. Preserve negative reflectance for diagnostic inspection rather than automatically clipping to zero. This product does not contain conventional land reflectance or every OCI instrument band. Its NRT processing version and illustrative mask make it suitable for learning but not yet publication-grade retrieval.

The `PACE_01_hyperspectral_intro.ipynb` tutorial uses NumPy, h5py, Matplotlib and scikit-learn on CPU. Its operations were tested in the earlier thread. For more interactive work, [HyperCoast](https://github.com/opengeos/HyperCoast) offers tutorials for [PACE](https://hypercoast.org/examples/pace/), [image cubes](https://hypercoast.org/examples/image_cube/), [field data](https://hypercoast.org/examples/field_data/), [cyanobacteria](https://hypercoast.org/examples/pace_cyano/) and [hypoxia](https://hypercoast.org/examples/hypoxia/).

### 7.3. Actual reconstructed images and spectra

The thread produced RGB, individual-band, false-colour, PCA and zoomed images directly from the uploaded file. All dark/masked regions are missing, rejected or unobserved pixels, not interpolated detail. Colour stretches are display choices. Companion figure paths below are relative to the artifact collection; the Markdown file does not embed their binary contents.

- `pace_intro/rgb.png`: approximate visible water colour.
- `pace_intro/bands.png`: 442, 550, 620 and 675 nm maps on common scale.
- `pace_intro/spectra.png`: three actual pixel spectra.
- `pace_recon/composites.png`: visible, false colour and PCA composites.
- `pace_recon/delta_zoom.png`: Mississippi Delta zoom.
- `pace_recon/pca_maps.png`: PC1–PC3 spatial maps.

| Composite | R | G | B |
|---|---|---|---|
| Visible approximation | 665 nm | 550 nm | 442 nm |
| False colour | 704 nm | 620 nm | 550 nm |
| PCA | PC1 | PC2 | PC3 |

Previously reported actual pixel Rrs values (sr⁻¹):

| λ (nm) | Mississippi Delta | Offshore Gulf | Eastern Gulf |
|---|---:|---:|---:|
| 442 | 0.00221 | 0.00734 | 0.00575 |
| 550 | 0.00686 | 0.00144 | 0.00292 |
| 620 | 0.00361 | 0.00006 | 0.00048 |
| 675 | 0.00298 | 0.00009 | 0.00032 |
| 704 | 0.00253 | −0.00023 | 0.00015 |

Offshore blue-dominated water and stronger green/red near the delta are clearly distinguishable, but cannot uniquely establish constituent or species abundances. PCA on the selected 44,158 pixels explained 75.29%, 21.58%, 2.26% in PC1–3 (~99.13% combined). A higher component may still encode biologically important narrow spectral features.

### 7.4. Derived products and next scenes

PACE derived products may include Chla, phytoplankton and dissolved/detrital absorption, particulate organic carbon, productivity and group-level estimates. NASA's MOANA product estimates near-surface abundances of *Prochlorococcus*, *Synechococcus* and autotrophic picoeukaryotes from optical/environmental models, not direct counts. Verify product availability and algorithm/version on the exact granule. Matching derived products are not independent validation of models trained on the same Rrs input.

Resources: [NASA PACE data](https://pace.oceansciences.org/access_pace_data.htm), [NASA Ocean Data notebooks](https://nasa.github.io/oceandata-notebooks/), [NASA Earthdata account](https://urs.earthdata.nasa.gov/), [Harmony subsetting tutorial](https://nasa.github.io/oceandata-notebooks/notebooks/oci/subsetting_with_harmony-py.html). Use `earthaccess` search for `PACE_OCI_L2_AOP` with target bbox/date, inspect returned collections and versions, then download only needed granules. Example bboxes (west, south, east, north): Lake Erie (−83.6, 41.3, −81.5, 42.2); upper Gulf of Thailand (99.5, 12.0, 101.5, 13.7). Product identifiers and subsetting support must be confirmed at execution.

Next image exercises: CIE RGB, AVW, derivative maps, optical water-type map, spectral-angle similarity, spectral clustering, chlorophyll index, phycocyanin absorption-depth exploratory index, NMF maps and GLORIA spectral-neighbour retrieval with applicability diagnostics.

## 8. Forward literature on GLORIA

Earlier citation search found publisher count 167 and OpenAlex snapshot 143; these counts are not rechecked here. The exhaustive API retrieval failed in that search. Both the article DOI (`10.1038/s41597-023-01973-y`) and dataset DOI (`10.1594/PANGAEA.948492`) should be included in a future deduplicated citation audit. The studies below are the targeted selection discussed in the thread, not a comprehensive or newly verified bibliography.

| Priority | Work | Contribution / what to reproduce |
|---|---|---|
| P0 | [Bi & Hieronymi 2024, Holistic optical water type classification](https://doi.org/10.1002/lno.12606) | Physics-informed OWTs across ocean, coastal and inland waters; GLORIA concentrated in greenish types 4a/4b. [pyOWT](https://github.com/bishun945/pyOWT), [supplement](https://zenodo.org/records/12803329) |
| P0 | [Benchmarking Hyperspectral Transfer and Graph Learning with PACE OCI, 2026](https://doi.org/10.1109/JSTARS.2026.3726801) | GLORIA-to-PACE cosine/KNN spectral transfer, reliability by spectral angle/NRMSE; English Channel. Only abstract/bibliographic details accessible in earlier review; full validation unexamined |
| P0 | [Saranathan et al. 2024](https://doi.org/10.3389/frsen.2024.1383147) | GLORIA convolved to MSI, OLCI, HICO, PRISMA; mixture density networks and MC-dropout BNNs; joint retrieval and uncertainty |
| P1 | [Hyperspectral inversion framework, 2023](https://doi.org/10.1016/j.rse.2023.113706) | Extended measurements including phycocyanin and constituent absorption spectra; [NASA manuscript](https://ntrs.nasa.gov/api/citations/20240007762/downloads/Hyperspectral_inversion_framework3.pdf). Obtain actual dataset before assuming access |
| P1 | [Werther et al. 2025](https://doi.org/10.1016/j.rse.2025.114820) | 2,066 samples, 155 waters, 14 countries; prediction of phytoplankton, CDOM and non-algal particle absorption at 443/675 nm; generalisation across optical regimes. [Code](https://github.com/mowerther/iop_nns), [data/models](https://zenodo.org/records/14893798) |
| P1 | [Graffeuille et al. 2024, metadata-driven hypernetworks](https://doi.org/10.24963/ijcai.2024/806) | Local adaptation; distinguish between-waterbody, within-waterbody and unseen-waterbody prediction. [Code](https://github.com/OGraffeuille/Multi-Task-Hypernetworks), [archive](https://zenodo.org/records/13316899), [related preprint](https://doi.org/10.2139/ssrn.4762429) |
| P1 | [Few-shot ResNet transfer learning, 2026](https://www.sciencedirect.com/science/article/pii/S1569843226002104) | GLORIA source and 32 local pairs; motivates local sample-size learning curves |
| P2 | [HyperEst 2025](https://doi.org/10.1016/j.jag.2025.104761) | Self-supervised spectral-spatial representation; [code](https://github.com/cluo-environment/HyperEst/) |
| P1 | [Balasubramanian et al. 2025](https://doi.org/10.3389/frsen.2025.1488565) | Historical ocean-colour MDNs; GLORIA + 2,384 observations = 9,956 in augmented dataset; ten variables, older sensors. Single archive access not established |

Additional leads from the citation survey:

| Work | Direction |
|---|---|
| [OWT chlorophyll retrieval 2024](https://doi.org/10.1109/InGARSS61818.2024.10984300) | Type-specific vs global algorithms |
| [Spectral morphological features and CatBoost 2024](https://doi.org/10.3390/w16243615) | Interpretable features |
| [Combining water-type schemes 2025](https://doi.org/10.1016/j.jag.2025.104909) | Semi-analytical suspended matter |
| [OWT-guided Secchi generalisation 2026](https://doi.org/10.3390/rs18020287) | Held-out optical conditions |
| [Hyperspectral observation from Landsat 2026](https://doi.org/10.1080/22797254.2026.2659082) | Multispectral-to-hyperspectral reconstruction; distinguish inferred from measured spectra |
| [AQUAVERSE-AC 2026](https://doi.org/10.3389/frsen.2026.1839175) | Atmospheric correction |
| [Physics-guided neural network 2026](https://doi.org/10.1016/j.ecoinf.2026.103611) | Hybrid optical physics and ML |
| [Hierarchical spectral ensemble 2026](https://doi.org/10.3389/frsen.2026.1860176) | Engineered features, augmentation, stacking; audit split independence |
| [Estuarine phytoplankton dynamics after hurricanes 2026](https://doi.org/10.1029/2025JC023274) | Ecosystem perturbations, variational autoencoders |

Immediate reproducible bridge: use pyOWT and cosine/KNN matching to classify GLORIA and map PACE. A match in spectral shape does not imply identical constituent composition; retain absolute magnitude, nearest-neighbour distance, uncertainty and out-of-distribution rejection. Evaluate GLORIA held-out observations before transferring to imagery.

## 9. Earth-science AI: frozen current technology portfolio

| Technology | Value | When | Primary purpose |
|---|---|---|---|
| AlphaEarth Foundations | Very high | Now | Learned landscape/environmental context |
| Google Earth Engine | Very high | Now | Geospatial integration and scalable exploration |
| PARDIG | Very high | Now | Historical precipitation and perturbation analysis |
| Granite-Geospatial-Ocean | Very high | Next image-analysis exercise | Pretrained ocean-colour representations |
| NASA PACE derived products | Very high | Now | Optical and model-derived biological observations |

### 9.1. AlphaEarth Foundations and Earth Engine (Google / DeepMind)

[Official overview](https://deepmind.google/blog/alphaearth-foundations-helps-map-our-planet-in-unprecedented-detail/), [paper](https://arxiv.org/abs/2507.22291), [Earth Engine collection](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL), [tutorial](https://developers.google.com/earth-engine/tutorials/community/satellite-embedding-01-introduction), [Colab setup](https://developers.google.com/earth-engine/guides/python_install-colab).

Annual 10 m, 64-dimensional embeddings, previously reported available 2017–2025. Cover terrestrial and some inland/coastal aquatic surfaces; coverage must be checked rather than assumed. Individual dimensions are latent features, not wavelengths or interpretable chemical variables. Useful for environmental analogues, landscape classification, sampling diversity and context surrounding field sites. Use same-year embeddings only for retrospective analysis; for prospective prediction avoid embeddings incorporating observations after the outcome date. GLORIA is largely historical and overlap is unquantified.

```python
import ee
ee.Authenticate()
ee.Initialize(project="YOUR_CLOUD_PROJECT")
embeddings = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
aef_2024 = embeddings.filterDate("2024-01-01", "2025-01-01")
```

An Earth Engine account and enabled Cloud project are required. Earth Engine is the integration infrastructure, not a single prediction model.

### 9.2. PARDIG (Google DeepMind and Google Research)

[Research paper](https://arxiv.org/abs/2611.13941), [documentation](https://developers.google.com/weathernext/guides/pardig). Earlier survey reported a November 2026 preprint, ~10 km / 15 min estimates, near-real-time series starting 2016 and a historical variant 1999–2023, CC BY 4.0. Confirm release, actual access method and units before analysis. Do not assume native Earth Engine availability.

Educational tasks: precipitation snapshots, accumulated rainfall, watershed aggregates, antecedent 1/3/7/14-day rainfall, lagged association with river plumes and Chla. Compare with an independent precipitation product or rain gauges. Precipitation alone does not equal river discharge or establish effects on microbial communities.

### 9.3. Granite-Geospatial-Ocean (IBM and collaborators)

[Model and documentation](https://huggingface.co/ibm-granite/granite-geospatial-ocean), [paper](https://arxiv.org/abs/2509.21273). Earlier review described a masked-autoencoder ViT trained on Sentinel-3 ocean-colour inputs (16 OLCI bands plus SLSTR SST, 42×42 spatial patches) with downstream Chla and primary productivity tasks. Verify exact checkpoint requirements and inference interfaces.

Do not directly feed our 339–719 nm PACE cube into the Sentinel-3 model: required longer wavelengths and SST are missing, and spatial/spectral response conventions differ. Start on a native, properly prepared Sentinel-3 scene. Compare frozen embeddings, PCA and physical indices using independent validation. Test masked reconstruction only if the released decoder/interface allows it; synthetic missing pixels are not equivalent to actual cloudy observations.

### 9.4. NASA PACE derived products

Use same-granule optical products as an educational comparison with RGB, AVW, PCA, optical types and simple indices. Distinguish AOP (reflectance) from derived inherent optical properties, biochemical products and model-based plankton composition. Use latest consistent science processing for formal comparisons; the uploaded 2024 NRT file is a teaching asset.

### 9.5. Secondary technologies (not active P0)

- [WeatherNext](https://deepmind.google/science/weathernext/) / Microsoft [Aurora](https://doi.org/10.1038/s41586-025-09005-y): weather forcing and field campaign planning; Aurora ocean-wave output is not necessarily a current field.
- [Google Flood Hub](https://sites.research.google/gr/floodforecasting/), [Flood API](https://developers.google.com/flood-forecasting), GRRR / Caravan / [MERIT Hydro](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1): river discharge and catchment structure. Global discharge products do not resolve local canal circulation.
- [TerraMind](https://ibm.github.io/terramind/), [Prithvi-EO](https://huggingface.co/ibm-nasa-geospatial): multimodal land/EO representations and surface water segmentation.
- [DOFA](https://arxiv.org/abs/2403.15356), [SpectralGPT](https://doi.org/10.1109/TPAMI.2024.3362475): sensor-flexible and spectral-spatial architecture ideas. Flexible input is not proof of aquatic domain competence.
- [Copernicus Marine](https://data.marine.copernicus.eu/) + [OceanParcels](https://docs.oceanparcels.org/): conventional physical baseline for virtual coastal drifters before AI forecasts.
- Ocean-state AI leads: [XiHe](https://arxiv.org/abs/2402.02995), [WenHai](https://doi.org/10.1038/s41467-025-57389-2), [FuXi-Ocean](https://www.nature.com/articles/s41612-026-01444-2), [LangYa](https://pubmed.ncbi.nlm.nih.gov/42580897/). Global kilometre-scale products cannot replace a local tidal/hydrodynamic model.
- NeuralGCM and [Google Earth AI](https://research.google/research-areas/google-earth-ai/): future climate/agent workflows; experimental agent access not established. Prefer explicit reproducible notebooks.

## 10. Educational mock research questions (full current curriculum)

These are educational investigations, not presumed novel scientific contributions. Each should produce an interpretable visualization, a quantitative result and a clear limitation. No result is predetermined.

### Level 1 — Observation

#### Q01. Why do different bodies of water have different colours?

**Tools:** GLORIA + PACE. **Difficulty:** beginner. **Data:** already available.

Compare representative clear, phytoplankton-rich, sediment-rich and CDOM-rich spectra; compute CIE chromaticity and a water-colour atlas; compare Spyrakos and pyOWT classifications; map optical types onto PACE. Quantify within-type variability and ambiguity. Deliverable: GLORIA colour atlas + PACE optical water-type map. Do not equate an optical class with a taxon or constituent concentration.

#### Q02. Can AI distinguish different landscapes without being told what they are?

**Tools:** AlphaEarth + Earth Engine. **Difficulty:** beginner.

Choose the lower Chao Phraya landscape. Extract 64-dimensional embeddings, make PCA composites, then cluster without labels. Compare clusters to independently identified urban areas, rice fields, mangroves, aquaculture, open water and forest. Deliverable: maps and a cluster–reference contingency table. Classes need not emerge cleanly; report mixed and ambiguous areas.

#### Q03. Can we identify waterways with similar environmental characteristics?

**Tools:** AlphaEarth + Earth Engine. **Difficulty:** beginner–intermediate.

Use cosine similarity or another explicit metric to search for environmental analogues. Compare the Vietnamese Red River GLORIA sites with candidate Thai waters. Evaluate embedding coverage, sample-year compatibility and point versus buffered landscape features. Deliverable: similarity map and ranked candidate sites. Environmental resemblance does not guarantee optical or microbial resemblance.

### Level 2 — Quantification

#### Q04. Can we reconstruct a rainfall event from space?

**Tools:** PARDIG + Earth Engine (or native PARDIG access). **Difficulty:** beginner–intermediate.

Select a historical rainfall event; inspect instantaneous estimates, hourly and daily accumulation, and area-weighted catchment totals. Compare with another rainfall product or gauges. Deliverable: rainfall animation, regional maps, catchment time series and agreement metrics. Learn four-dimensional data (latitude, longitude, time, variable), aggregation and resolution.

#### Q05. What biological information is already available from PACE?

**Tools:** NASA PACE derived products. **Difficulty:** beginner–intermediate.

Acquire compatible product suites for the existing Gulf scene: Chla, phytoplankton absorption, dissolved/detrital absorption, POC and group estimates where available. Compare with RGB, PCA, AVW and simple spectral indices. Map agreement/disagreement; quantify correlations and coverage. Deliverable: comparative product atlas. These are model estimates, not independent biological ground truth.

#### Q06. How much information can be recovered from a partially obscured satellite image?

**Tools:** Granite-Geospatial-Ocean. **Difficulty:** intermediate.

Take a native Sentinel-3 scene, hold out valid pixels and impose random, contiguous-block and stripe masks at 10%, 25%, 50%, 75% where supported. Compare against simple interpolation, PCA/low-rank baselines and the original observed values. Deliverable: masked/reconstructed images and error curves. If decoder unavailable, pivot to frozen embedding or released inference task; do not invent a reconstruction. Cloud missingness is not random, and recovered pixels are predictions.

### Level 3 — Integration

#### Q07. What happens to coastal waters after heavy rainfall?

**Tools:** PARDIG + PACE + Earth Engine. **Difficulty:** intermediate.

Choose an event and compare pre/post optical maps and plume area; examine turbidity or particle proxies, Chla, lag and recovery. Use multiple events, discharge, tides, winds, season and cloud controls for stronger inference. Deliverable: time-series atlas and lagged associations. Rain can stimulate or suppress blooms; correlation is not causation.

#### Q08. Does the surrounding landscape explain differences in water quality?

**Tools:** GLORIA + AlphaEarth + Earth Engine. **Difficulty:** intermediate–advanced.

Build matched cohorts and extract point and multi-scale land/catchment features. Compare location/season baseline (M0), reflectance alone (M1), context alone (M2), reflectance + context (M3) under identical held-out waterbody/study/time splits. Deliverable: enriched GLORIA table and ablation results. Audit years, coverage, temporal leakage, and geographic shortcuts. Do not select a cohort based on observed model performance.

#### Q09. Can a foundation model recognise optical water types?

**Tools:** Granite Ocean + GLORIA + PACE. **Difficulty:** advanced.

Compare physical indices/OWTs, PCA and pretrained embeddings. Start with native Sentinel-3 patches and independently matched labels; GLORIA and PACE are comparison references, not interchangeable model inputs. Evaluate discrimination, transfer and within/between-waterbody effects. Deliverable: embedding plots and held-out metrics. An embedding cluster is not a biological class by itself.

### Level 4 — Thailand-specific applications

#### Q10. How do major rivers influence the upper Gulf of Thailand?

**Tools:** PACE, PARDIG, AlphaEarth, Earth Engine. Compare Chao Phraya, Tha Chin, Bang Pakong and other major discharge zones; plume shape, rainfall, optical types and landscape context. Include circulation/discharge when available. Deliverable: comparative river-plume atlas and event time series.

#### Q11. Is Songkhla Lake one ecosystem or several optically distinct ecosystems?

**Tools:** AlphaEarth, Earth Engine, PACE where geometry permits; supplement with higher-resolution optical data as needed. Map freshwater–marine gradients, optical heterogeneity and seasonal changes. Deliverable: spatially and temporally explicit optical zonation. Validate against salinity and local water-quality observations.

#### Q12. Can we detect the emergence of a phytoplankton bloom?

**Tools:** PACE, higher-resolution satellite observations, PARDIG, Earth Engine. Candidate Ubol Ratana Reservoir or a suitable coastal system. Explore bloom onset, precursor environmental conditions, optical indices and model-derived products. Deliverable: retrospective event detection and false-alarm assessment. Forecast claims require temporally independent validation and independent bloom labels.

#### Q13. Where would a scientific krathong swarm provide the most valuable observations?

**Tools:** all five priority technologies, GLORIA and simulated sampling. Map environmental diversity, optical uncertainty, underrepresented water types and gaps in satellite coverage. Compare random, stratified, uncertainty-driven and diversity-based site selection at equal sample budget. Include safe, recoverable deployment locations. Deliverable: sampling-priority atlas, simulated information-gain curves and pilot protocol; no proposed hardware count should be treated as experimentally justified before these tests.

### First five exercises in execution order

- [ ] Q01 — GLORIA colour atlas + PACE optical water-type map.
- [ ] Q02 — AlphaEarth PCA and clustering of central Thai landscape.
- [ ] Q05 — PACE derived-product comparison atlas.
- [ ] Q04 — PARDIG rainfall reconstruction, animation and time series.
- [ ] Q06 — Granite Ocean masked reconstruction benchmark (interface permitting).

Q03, Q07, Q08 and Q09 follow as integration becomes feasible. Q10–Q13 are longer-term application case studies.

## 11. Experiment registry and crosswalk

The thread generated multiple ID namespaces. Preserve them as historical identifiers rather than silently renumbering experiments. Q01–Q13 are the current educational roadmap; the other IDs are narrower research tasks. All below are proposed unless explicitly marked completed or exploratory.

### GLORIA research tasks

| ID | Task | Status / priority |
|---|---|---|
| GL-R00 | Integrity, coverage and metadata | Completed initial audit |
| GL-R01 | Spectral diversity and PCA | Completed exploratory |
| GL-R02 | Wavelength–water-quality associations | Completed exploratory |
| GL-R03 | Ridge/Extra Trees baselines | Completed exploratory |
| GL-R04 | Site/study held-out evaluation | Completed exploratory |
| GL-R05 | Minimum informative wavelengths | Proposed |
| GL-R06 | Sentinel-2 spectral compression | Approximate benchmark completed |
| GL-R07 | Strong published bio-optical baselines | P0 |
| GL-R08 | Official SRFs | P0 |
| GL-R09 | Held-out tropical and river evaluation | P0 |
| GL-R10 | Raw, normalized and derivative spectra | P0; introductory examples done |
| GL-R11 | Minimal band combinations | P0 |
| GL-R12 | Dataset-level resampling and uncertainty | P1 |
| GL-R13 | QC sensitivity | P1 |
| GL-R14 | Reproduce Kramer pigment analysis | P1 |
| GL-R15 | Find matched hyperspectral–metagenomic datasets | P1 |

### Optical measurement and representation tasks

| ID | Task | Priority |
|---|---|---|
| OPT-01 | Reproduce GLORIA Fig. 3c CIE chromaticity | P0 |
| OPT-02 | Perceived water-colour atlas | P0 |
| OPT-03 | AVW distributions and maps | P0 |
| OPT-04 | Original 13 optical water types | P0 |
| OPT-05 | OWT geographical maps | P0 |
| OPT-06 | QWIP reproduction | P0 |
| OPT-07 | Actual spectral artefacts | P0 |
| OPT-08 | Instrument-family comparisons | P1 |
| OPT-09 | Replicate uncertainty | P1 |
| OPT-10 | Reflectance from component radiometry | P1; simple ratio demonstrated |
| OPT-11 | 3C uncertainty experiment | P1 |
| OPT-12 | Correct cross-instrument convolution | P1 |
| OPT-13 | Pigment concentrations | P2 |
| OPT-14 | Microbial composition | P2; additional data |
| OPT-15 | Classify GLORIA with pyOWT | P0 |
| OPT-16 | pyOWT mapping of PACE | P0 |
| OPT-17 | Match PACE pixels to GLORIA | P0 |
| OPT-18 | Map similarity and OOD pixels | P0 |
| OPT-19 | Global vs OWT-specific retrieval | P0 |
| OPT-20 | Within/between-waterbody performance | P1 |
| OPT-21 | Constituent-specific absorption | P1 |
| OPT-22 | Local calibration sample-size curve (0, 5, 10, 25, 50, 100) | P1 |
| OPT-23 | Phycocyanin retrieval | P1 |
| OPT-24 | PCA vs learned embeddings | P2 |
| OPT-25 | Multispectral-to-hyperspectral reconstruction | P2 |

### Earth-science research tasks (EA-R)

| ID | Task | Priority |
|---|---|---|
| EA-R01 | Extract AlphaEarth for eligible GLORIA sites | P0 |
| EA-R02 | Reconstruct antecedent rainfall | P0 |
| EA-R03 | GLORIA-Context enriched dataset | P0 |
| EA-R04 | Test incremental context beyond reflectance | P0 |
| EA-R05 | Native Sentinel-3 Granite inference | P1 |
| EA-R06 | PCA/OWT/pretrained embedding comparison | P1 |
| EA-R07 | Thai environmental diversity mapping | P1 |
| EA-R08 | Optimize sampling using embedding diversity | P1 |
| EA-R09 | Virtual coastal drifter transport | P1 |
| EA-R10 | DOFA cross-sensor representation | P2 |
| EA-R11 | Ecosystem perturbation dynamics | P2 |
| EA-R12 | Microbial measurements integration | P2 |

Educational tool exercises EA-01–EA-11: Earth Engine setup; AlphaEarth channel/PCA visualization; environment comparison; GLORIA point extraction; PARDIG time series; catchment rainfall maps; PACE Chla/pigment comparison; PACE phytoplankton/carbon products; native Granite inference; ocean embedding visualization; compare spectral, environmental and learned representations. These correspond to Q01–Q09 rather than separate competing priorities.

## 12. Integration hypothesis and scientific rigor

The proposed **GLORIA-Context** dataset includes Rrs, measured water-quality variables, AlphaEarth embeddings, antecedent rainfall, meteorology, hydrology, surrounding land cover, elevation, season and coordinates. Test simple geographical baselines first. Compare on identical complete-case cohorts, with a separate analysis of missingness. Report model improvement with uncertainty intervals rather than a single pooled score. For microbial tasks, distinguish relative abundance, absolute abundance, diversity and community types; handle compositional data properly.

General requirements for subsequent experiments:

1. Predefine target, cohort, grouping, QC and performance metrics before model selection; preserve exclusions and original identifiers.
2. Use waterbody-held-out, study-held-out and temporal validation; avoid duplicates, spatial leakage and optical-derived target circularity. Distinguish within-waterbody change from between-waterbody variation.
3. Keep observation, retrieval, reconstruction and prediction separate. Never describe a satellite algorithm's output as independent field truth.
4. Check spectral response, units, processing version, geolocation, date, masks, spatial resolution and valid wavelength ranges. Missing or incompatible channels should not be fabricated.
5. Report applicability domain, coverage, out-of-distribution rejection, uncertainty and performance against simple physical or statistical baselines.
6. For real scientific campaigns, use matched field optics, laboratory chemistry, molecular sampling, hydrological data, retrieval logs and controls. A single nighttime festival does not validate daytime satellite products or establish causal effects.
7. Preserve exact data manifests, software versions, code, train/test IDs, predictions and figure-generating scripts. Use Colab CPU for introductory GLORIA/PACE analyses; allocate GPU only when justified for model inference/training.

## 13. Artifact inventory and reproducibility

The files below were present locally at handoff assembly. Filenames are references to companion artifacts, not embedded downloads. No repository was created or modified in this handoff.

| Artifact | Role |
|---|---|
| `GLORIA-2022.zip` | Original dataset archive |
| `s41597-023-01973-y.pdf` | GLORIA data descriptor |
| `s43586-026-00470-x.pdf` | Hyperspectral imaging primer |
| `43705_2023_article_308.pdf` | Kaneko paper |
| `kaneko2023_citing_works.csv` | 24 citation-index records |
| `HS-R01-R03.ipynb` | Initial research notebook, incomplete manual mapping |
| `HS_R01_R03.ipynb` | User's first failed Colab attempt |
| `GLORIA_phase1_Colab.ipynb` | Early standalone audit notebook; superseded for benchmark |
| `GLORIA_benchmark_corrected.ipynb` | Corrected benchmark, original archive input |
| `GLORIA_benchmark_results.zip` | Retained benchmark code/results/manifest |
| `GLORIA_hyperspectral_tutorial.ipynb` | Recommended introductory GLORIA notebook |
| `PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc` | Actual Gulf of Mexico PACE input |
| `PACE_01_hyperspectral_intro.ipynb` | Recommended introductory image notebook |
| `pace_intro/` and `pace_recon/` | Actual rendered PACE plots |

SHA-256 fingerprints checked at compilation:

```text
GLORIA-2022.zip
f5ad5106d5fd74f0d874085a23e4189302e7409aed9f82d629ae6cdb47d21f14
PACE_OCI.20240730T181157.L2.OC_AOP.V2_0.NRT.nc
db38c89499f33603de850e1b321e1adbdbcd0609ebc7c532050c8d16d183e98e
```

Retained GLORIA result manifest: Python 3.13.5, scikit-learn 1.8.0, NumPy 2.3.5, pandas 2.2.3; scipy and matplotlib also used. Reproduction command from retained README:

```bash
python3 run_gloria.py GLORIA-2022.zip output_dir
```

The package includes `metrics.csv`, `predictions.csv.gz`, `target_coverage.csv`, `country_waterbody.csv`, `southeast_asia_metadata.csv`, `spectral_associations.csv`, `manifest.json`, `run_gloria.py`, `spectra.png`, `pca.png`, `associations.png`, and `README.md`.

## 14. Open datasets for subsequent learning

| Resource | Intended use |
|---|---|
| [GLORIA](https://doi.org/10.1594/PANGAEA.948492) | Field spectra and reference chemistry |
| [SeaBASS](https://seabass.gsfc.nasa.gov/) | Optical and biological field measurements; deduplicate GLORIA overlap |
| [Tara Oceans](https://www.tara-oceans-science.org/omics/) | Marine metagenomics |
| [EnMAP](https://www.enmap.org/data_access/) | 30 m hyperspectral scenes |
| [PACE](https://pace.oceansciences.org/access_pace_data.htm) | Ocean-colour data and biological products |
| [AquaCorr-Global](https://zenodo.org/records/21927415) | Earlier identified matchup dataset; verify record and access |
| [BMA water quality](https://data.go.th/dataset/waterquality) | Thai monitoring context |
| [pyOWT supplement](https://zenodo.org/records/12803329) | Optical classification |
| [Werther IOP dataset](https://zenodo.org/records/14893798) | Absorption targets and probabilistic inversion |

## 15. Current status and immediate next steps

| Component | Status |
|---|---|
| GLORIA acquisition, audit, initial spectral exercises | Complete, exploratory |
| GLORIA baseline regression | Complete, exploratory |
| GLORIA paper and citation review | Detailed paper review; targeted forward review, incomplete citation graph |
| Kaneko reference and forward review | Initial review; 24-record supplied export, not every citing text inspected |
| PACE first granule and reconstructions | Complete, educational |
| CIE/AVW/OWT/QWIP reproduction | Pending |
| Exact spectral response benchmark | Pending |
| Thai nationwide satellite suitability atlas | Pending |
| PACE derived product matchups | Pending |
| Earth Engine and AlphaEarth | Pending setup and exploration |
| PARDIG | Pending access and exploration |
| Granite Ocean | Pending native inputs and interface verification |
| Integrated environmental and microbial analysis | Pending additional data and validation |
| Recoverable scientific drifter field deployment | Proposed only |

**Next practical session:** Q01 (CIE colour and OWT) on the available GLORIA and PACE data; Q02 (Earth Engine/AlphaEarth) in parallel. Q05 should follow with matched NASA products. Do not begin a large integrated model until each component's measurement meaning, coverage and limitations are understood.

The central eventual test remains whether a measured optical phenotype plus environmental context and transport improves prediction of independently sampled microbial organisation on genuinely unseen sites and times. A negative result would be scientifically useful: it would identify which information cannot be recovered remotely and therefore which measurements a scientific drifter campaign ought to prioritise.

---

### Compilation note

This handoff is a consolidated thread record, not a new systematic review or experimental report. I chose to start at the space-based microbial-dynamics question, preserve the original experiment ID namespaces, and include the drifter motivation briefly rather than reproduce the earlier sentiment-analysis discussion. Existing GLORIA metrics were checked against retained CSVs and the two archive fingerprints were recomputed; the rest of the earlier numerical results and literature claims are retained with their stated scope and limitations. In particular, the current availability of 2026 models/products, the complete GLORIA forward citation list, the full text of the PACE–GLORIA transfer study, and unexecuted methods remain to be verified. The Markdown references companion files by name rather than embedding large binaries or creating a new repository.
