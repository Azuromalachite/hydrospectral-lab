# Pre-registration (Draft): Cross-Repository Aquatic Chromophore & CDOM Polarity Milestone (`CROSS-01`)

- **Date:** 2026-11-26
- **Experiment ID(s):** `CROSS-01` (public-repository bridge spanning [`espmap`](https://github.com/Azuromalachite/espmap), [`arrowfield`](https://github.com/Azuromalachite/arrowfield), and `hydrospectral-lab` `Q01`/`OPT-01`)
- **Author:** Thanakrit Wongsatit
- **Status:** `DRAFT` (potential cross-repository milestone; promote to `PURSUE` only after curating the open-license experimental solvatochromism dataset and pinning immutable upstream bundle SHA-256 digests)

## 1. Scientific & educational question

This milestone explores a clean, decoupled bridge across three MIT-licensed public repositories — keeping strict fact ownership (`docs/decisions.md` `D-008`):

| Fact / Artifact | Owning repository | Pinning & interface contract |
| --- | --- | --- |
| Ground-state DFT electrostatic potential on the $\rho = 0.002$ isosurface, per-site stats, gas vs. PCM-water error budgets, `analysis_key` / `render_key` | [`espmap`](https://github.com/Azuromalachite/espmap) | Pinned immutable release tag (`v0.3.1`, commit `5f6eaade3c0d60af921808cc08e7225288c96e36`; never `master`) |
| `Predict → Reveal → Explain → Control → Limits` pedagogy, uncertainty-first difference cards, hostile-pedagogy contract | [`arrowfield`](https://github.com/Azuromalachite/arrowfield) | Pinned release tag (`v0.1.0`) / schema conventions |
| Aquatic chromophore context, GLORIA natural-water reflectance & CIE 1931 colourimetry, official SRF convolution, leakage-free CV | `hydrospectral-lab` | Consumes frozen `espmap` JSON/NPZ teaching bundle via verified SHA-256 manifest |

It poses two scoped questions strictly within `espmap`'s validated closed-shell organic domain (**metal-free aquatic chromophores and CDOM model compounds only** — e.g., aromatic humic/fulvic acid surrogates such as vanillic, syringic, gallic, ferulic, and cinnamic acids; open-chain phycobilin/biliverdin chromophore fragments; xanthophyll/carotenoid motifs; mycosporine-like amino acid cores):

1. **Educational deliverable (`Q01` molecular appendix):** Can an `arrowfield`-style interactive lesson bundle pair frozen `espmap v0.3.1` gas vs. PCM-water ESP surfaces of metal-free CDOM/pigment model compounds with GLORIA CIE 1931 aquatic reflectance spectra (`Q01`) to teach *why* aqueous hydrogen bonding and chromophore conjugation shape CDOM absorption tails — while explicitly teaching what ground-state ESP **cannot** tell you?
2. **Quantitative pilot (`CROSS-01b`):** On a curated, open-license set of metal-free aquatic/organic chromophores with measured UV-Vis absorption maxima ($\lambda_{\max}$) in both polar protic (water/methanol/ethanol) and non-polar reference solvents, do `espmap v0.3.1` PCM-water vs. gas ESP descriptors (surface `V_min`, `V_max`, area-weighted H-bond site means, dipole shift $\Delta\mu_{\text{water}-\text{gas}}$, and Politzer GIPF $\sigma^2_{\text{tot}}, \nu$) improve **Bemis–Murcko scaffold-held-out** predictions of experimental solvatochromic shift ($\Delta\lambda_{\max}$ or $\Delta E_{\text{solv}}$ in eV) beyond simple 2D RDKit topological baselines (`TPSA`, `MolLogP`, `NumHAcceptors`, `NumHDonors`, aromatic ring count)?

## 2. Seed observation & prior exposure (disclosed)

- `espmap v0.3.1` benchmarks (`bench/solvent_convention.jsonl`, `bench/error_budget.jsonl`, `bench/conformers.jsonl`) have already established that gas-phase → PCM-water shifts are large (comparable to basis-set effects, e.g., several kcal/mol on polar sites) and that small anions require DFT-optimised geometries in PCM water rather than gas-phase MMFF94s.
- `hydrospectral-lab` `results/Q01_water_colour/` (`status: exploratory`) has already summarized GLORIA `CDOM-dominated` (`n = 78`, median AVW `565.0 nm`, hue `48.6°`) vs. `Clear` (`n = 554`, `514.2 nm`, `149.3°`) waters.
- **Not yet seen:** No aquatic chromophore solvatochromism dataset has been downloaded, filtered, or modelled against `espmap` descriptors in `hydrospectral-lab`.

## 3. Cohort, physical domain limits & QC rules (to be frozen before `PURSUE`)

- **Strict physical exclusions (enforced from `espmap` limits):**
  - **No transition metals or Mg-porphyrin complexes** (e.g., chlorophyll *a* / bacteriochlorophyll Mg²⁺ macrocycles are excluded from ground-state `espmap` descriptor claims because metal coordination and excited-state excitonic coupling in pigment-protein complexes are outside `espmap`'s validated scope).
  - **No unvalidated gas-phase anions:** Carboxylate/phenolate aquatic CDOM anions (at pH 7.4) must use DFT-optimised PCM-water geometries (`espmap --optimize --solvent water`), never SMILES + MMFF94s, and all compared records must share identical `analysis_key`.
  - **Stereochemistry gate:** Every candidate molecule must pass `espmap v0.3.1 --require-stereo` (no unspecified stereocentres or E/Z double bonds).
  - **Solvent-pair quality:** Experimental $\lambda_{\max}$ pairs must come from an open-license (CC BY 4.0 / CC0) primary compilation with verified source manifest SHA-256 and exact solvent identity recorded.

## 4. Conditions, ablations & splits (to be frozen before `PURSUE`)

- **Baseline `M0_2D`:** Standardized 2D RDKit descriptors (`TPSA`, `MolLogP`, `NumHAcceptors`, `NumHDonors`, `NumAromaticRings`, molecular weight) + solvent dielectric/Kamlet–Taft polarity difference.
- **Model `M1_ESP`:** `M0_2D` + `espmap v0.3.1` ground-state ESP descriptors (`V_min`, `V_max`, `V_pos_mean`, `V_neg_mean`, $\sigma^2_{\text{tot}}$, $\nu$, $\Delta\mu_{\text{water}-\text{gas}}$), all computed under one pinned `analysis_key` (`B3LYP/def2-TZVP`, `--density-fit`, PCM water & gas).
- **Split:** 5-fold **Bemis–Murcko scaffold-held-out** `GroupKFold` (`hydrospectral.splits.make_group_kfold_splits`), ensuring no chromophore core appears in both train and test.
- **Uncertainty budget:** Print `espmap`'s measured basis-set, conformer, and site-partition uncertainty bounds alongside any reported descriptor delta (`arrowfield` difference-card rule).

## 5. Outcomes & decision rules

- **Interesting:** `M1_ESP` reduces scaffold-held-out MAE on experimental solvatochromic shift ($\Delta E_{\text{solv}}$ in eV) over `M0_2D` by at least 15% with 95% scaffold-cluster bootstrap CI strictly below `0` AND descriptor effect size exceeding `espmap`'s conformer/basis error budget.
- **Boring / null:** No improvement over `M0_2D` under scaffold holdout (expected if excited-state dipole change $\Delta\mu_{S_1 - S_0}$ dominates ground-state ESP). *Why informative:* documents empirically where ground-state ESP suffices (H-bonding/polarity pedagogy) versus where excited-state quantum chemistry is strictly required.
- **Failure / artifact:** Any `analysis_key` / `cohort_key` mismatch, scaffold leakage, unoptimised MMFF anion geometry, or conflation of single-molecule ground-state polarity with bulk natural-water CDOM slope $S_{275-295}$ or microbial taxonomy.

## 6. Forking-paths guard

- Before switching status from `DRAFT` to `PURSUE`, freeze the exact chromophore list (`molecules.yaml` validated with RDKit stereochemistry checks), source manifest SHA-256, `espmap v0.3.1` settings, and fixed Ridge/PLS hyperparameter grid in an append-only promotion commit.
- Never copy `espmap` or `arrowfield` source code into `hydrospectral-lab`; consume frozen records via a versioned schema reader and pinned release metadata.

## 7. Deviations (append-only, dated)

*(Draft protocol created 2026-11-26; awaiting open-license solvatochromism dataset staging and explicit promotion to `PURSUE`.)*
