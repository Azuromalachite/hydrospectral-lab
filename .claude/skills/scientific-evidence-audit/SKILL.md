---
name: scientific-evidence-audit
description: Use when adding, reviewing, or challenging remote-sensing, bio-optical, Earth-science AI, hydrological, or microbial-ecology claims, literature syntheses, dataset descriptions, or interpretation prose in hydrospectral-lab. Audits what evidence actually supports, source reading depth, domain applicability, and rights.
---

# Audit Scientific & Literature Evidence

**Scope:** Assess evidentiary support, physical/ecological inference boundaries, and citation accuracy. When an experiment or code change is also involved, pair this checklist with [`experiment-review`](../experiment-review/SKILL.md). A DOI in the same field does not validate a specific retrieval equation or ecological claim unless the exact passage, domain, and validation split support it.

## 1. Classify the claim before gathering or citing evidence

Identify the exact sentence, table entry, or interpretation and classify its epistemic level:

- **Direct physical measurement:** Calibrated radiometry ($L_t$, $L_{sky}$, $E_s$, $R_{rs}$) or laboratory water/molecular assay with stated method and uncertainty.
- **Bio-optical retrieval / empirical inversion:** Constituent estimate (e.g., Chla, TSS, $a_{\text{CDOM}}(440)$, IOPs) inferred from spectra; subject to optical ambiguity and applicability domain.
- **Model-derived satellite or AI product:** Output of an upstream algorithm or foundation model (e.g., PACE MOANA picoplankton abundances, AlphaEarth 64-D embeddings, PARDIG precipitation, Granite masked reconstructions); never call these "ground truth" or "direct observations".
- **Environmental / statistical proxy:** Prediction driven by covariates (photoperiod, latitude/longitude, SST, watershed land cover) rather than a direct optical absorption/scattering signature.
- **Unresolved hypothesis:** Proposed mechanism (e.g., predicting heterotrophic succession from spaceborne bloom trajectories) requiring time-matched molecular sampling and independent validation.

Never quietly promote a proxy correlation into direct taxonomic detection, an optical water type into a species label, or a proposed experiment into an established result.

## 2. Record provenance and exact reading status

Update [`docs/references-access.md`](../../../docs/references-access.md) when onboarding consequential literature or datasets. Record DOI/accession, authors, year, version/processing level (e.g., PACE V2.0 NRT vs. science reprocessing), exact locator (page, figure, table), and honest reading status:

- `discovered` (e.g., uninspected rows in a citation export)
- `metadata/abstract read`
- `relevant passages read`
- `full work read`
- `independently verified` (recomputed from raw archive/code)

"Found in OpenAlex/CSV" is not "read", and an AI or secondary summary is a list of claims to verify one by one, not primary verification. Separate preprints, theses, and paratext from peer-reviewed articles.

## 3. Test domain match and inference pitfalls

Check every cited result or dataset claim against these recurring aquatic remote-sensing pitfalls:

- **Validation inflation:** Was $R^2$ or accuracy obtained under random K-fold / leave-one-out CV, or under spatially buffered / waterbody-held-out / dataset-held-out (`Dataset_ID`) validation? (Compare Kaneko et al. 2023 lat/lon dropping from 68% LOO to 29% buffered, and Marchese et al. July 2026 eukaryotic $R^2$ dropping from 0.44 K-fold to 0.09 leave-one-dataset-out.)
- **Tropical & riverine transfer:** Global datasets skew heavily toward temperate lakes and coastal oceans (rivers are only 3.3% of GLORIA, with zero Thai spectra). Do not claim riverine or Thai readiness from global pooled metrics (e.g., GLORIA's usable turbidity cohort has only 1 river sample).
- **Sensor & geometric realism:** Check native pixel footprint vs. waterway width, adjacency effects, glint, clouds, atmospheric correction artefacts (such as the ~762 nm oxygen A-band feature), native spectral resolution vs. 1 nm interpolated grids, and daytime satellite overpasses vs. nighttime field events (e.g., Loy Krathong).
- **Biological & compositional nuance:** Gene copy markers (e.g., `psbO`, 16S, 18S) measure relative sequence/cell proxies, whereas optical reflectance responds nonlinearly to pigment packaging, cell size, scattering, CDOM, and mineral suspended sediment.

## 4. Respect dataset and publication rights

- Keep third-party publisher PDFs, restricted chapters, and bulk raw datasets out of Git (`AGENTS.md` rule 4).
- Check dataset licenses and attribution rules individually (e.g., GLORIA CC BY 4.0 via PANGAEA; deduplicate overlapping SeaBASS/LIMNADES records by repository ID when combining archives).
- Deliver concise, durable records in `docs/` with explicit **permitted wording** and stated uncertainties rather than speculative filler.
